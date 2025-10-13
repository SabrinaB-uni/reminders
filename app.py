from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
import sqlite3
from datetime import datetime, timedelta
import requests
import logging

app = Flask(__name__)

app.secret_key = 'your-secret-key-change-this-in-production'

DATABASE_NAME = 'reminders.db'
LOANS_API_URL = 'http://172.19.28.7:5006/api/active_loans'
SCHEDULE_API_URL = 'http://yavweb02:3001/api/schedule'

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_active_loans():
    """
    Fetch active loans from API
    Returns list of loan strings or empty list if API fails
    """
    try:
        logger.info(f"Fetching active loans from {LOANS_API_URL}")
        response = requests.get(LOANS_API_URL, timeout=5)
        response.raise_for_status()

        data = response.json()
        active_loans = data.get('active_loans', [])

        logger.info(f"Successfully fetched {len(active_loans)} active loans")
        return active_loans

    except (requests.exceptions.RequestException, ValueError) as error:
        logger.error(f"Error fetching active loans: {error}")
        return []


def get_schedule_info():
    """
    Fetch current schedule info from API
    Returns dict with period and week info or None if API fails
    """
    try:
        logger.info(f"Fetching schedule info from {SCHEDULE_API_URL}")
        response = requests.get(SCHEDULE_API_URL, timeout=5)
        response.raise_for_status()

        data = response.json()

        logger.info(
            f"Successfully fetched schedule info: Period {data.get('current_period')} Week {data.get('week_type')}")
        return data

    except (requests.exceptions.RequestException, ValueError) as error:
        logger.error(f"Error fetching schedule info: {error}")
        return None


def parse_loan_string(loan_string):
    """
    Parse loan string to extract student name and item
    """
    try:
        last_paren_index = loan_string.rfind('(')

        if last_paren_index != -1 and ')' in loan_string[last_paren_index:]:
            closing_paren = loan_string.rfind(')')
            days = loan_string[last_paren_index + 1:closing_paren]
            clean_string = loan_string[:last_paren_index].strip()
        else:
            days = ""
            clean_string = loan_string.strip()

        if ' - ' in clean_string:
            parts = clean_string.split(' - ', 1)
            student = parts[0].strip()
            item = parts[1].strip()

            return {
                "student": student,
                "item": item,
                "days": days
            }

        return {
            "student": clean_string if clean_string else "Unknown",
            "item": "Unknown",
            "days": days
        }

    except Exception as error:
        logger.error(f"Error parsing loan string '{loan_string}': {error}")
        return {
            "student": loan_string,
            "item": "Unknown",
            "days": ""
        }


def format_loans_for_display(active_loans):
    """
    Format loan data for TV display
    """
    formatted_loans = []

    for loan in active_loans:
        parsed_loan = parse_loan_string(loan)

        loan_item = {
            'id': f'loan_{len(formatted_loans)}',
            'title': loan,
            'description': None,
            'location': None,
            'time': None,
            'time_display': 'LOAN',
            'date': datetime.now().strftime('%Y-%m-%d'),
            'date_display': 'Today',
            'is_loan': True,
            'student': parsed_loan['student'],
            'item': parsed_loan['item'],
            'days': parsed_loan['days'],
            'original': loan
        }
        formatted_loans.append(loan_item)

    return formatted_loans


def get_next_working_day():
    """
    Get next working day
    If today is Friday, return Monday or return tomorrow.
    """
    today = datetime.now()
    if today.weekday() == 4:
        return today + timedelta(days=3)
    return today + timedelta(days=1)


def get_next_working_day_name():
    """
    Get the display name for the next working day
    """
    today = datetime.now()
    if today.weekday() == 4:
        return "Monday"
    return "Tomorrow"


def is_weekend(date_str):
    """
    Check if a given date string is a weekend
    """
    try:
        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
        return date_obj.weekday() >= 5
    except ValueError:
        return False


def is_today_friday():
    """
    Check if today is Friday
    """
    return datetime.now().weekday() == 4


def is_monday(date_str):
    """
    Check if a given date string is a Monday
    """
    try:
        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
        return date_obj.weekday() == 0
    except ValueError:
        return False


def get_db_connection():
    """Get database connection"""
    try:
        connection = sqlite3.connect(DATABASE_NAME)
        connection.row_factory = sqlite3.Row
        return connection
    except sqlite3.Error as error:
        print(f"Database connection error: {error}")
        return None


def parse_time_safely(time_str):
    """
    Safely parse time string in various formats
    """
    if not time_str:
        return None

    try:
        time_obj = datetime.strptime(time_str, '%H:%M:%S').time()
        return time_obj
    except ValueError:
        try:
            time_obj = datetime.strptime(time_str, '%H:%M').time()
            return time_obj
        except ValueError:
            return None


def format_time_for_display(time_str):
    """
    Format time string for display
    """
    time_obj = parse_time_safely(time_str)
    if time_obj:
        return time_obj.strftime('%I:%M %p')
    return 'All Day'


def get_reminders_for_date(date_str):
    """Get reminders for a specific date"""
    connection = get_db_connection()
    if not connection:
        return []

    try:
        cursor = connection.cursor()
        cursor.execute('''
        SELECT * FROM reminders 
        WHERE date = ? 
        ORDER BY 
            CASE WHEN time IS NULL THEN '23:59:59' ELSE time END
        ''', (date_str,))

        reminders = []
        for row in cursor.fetchall():
            reminder = dict(row)
            reminder['time_display'] = format_time_for_display(reminder['time'])
            reminder['is_loan'] = False
            reminders.append(reminder)

        return reminders

    except sqlite3.Error as error:
        print(f"Error fetching reminders: {error}")
        return []
    finally:
        connection.close()


def get_sort_key(reminder):
    """Helper function to get sort key for reminders"""
    time_value = reminder.get('time')
    if time_value is None:
        time_value = '23:59:59'
    return reminder['date'], time_value


def get_all_reminders_organized():
    """
    Gets all reminders from database organized into current and old sections
    """
    connection = get_db_connection()
    if not connection:
        return {'current_reminders': [], 'old_reminders': []}

    try:
        cursor = connection.cursor()
        cursor.execute('''
        SELECT * FROM reminders 
        ORDER BY date DESC, 
            CASE WHEN time IS NULL THEN '23:59:59' ELSE time END
        ''')

        today = datetime.now().date()
        current_reminders = []
        old_reminders = []

        for row in cursor.fetchall():
            reminder = dict(row)
            reminder_date = datetime.strptime(reminder['date'], '%Y-%m-%d').date()
            reminder['time_display'] = format_time_for_display(reminder['time'])

            date_obj = datetime.strptime(reminder['date'], '%Y-%m-%d')
            reminder['date_display'] = date_obj.strftime('%a, %b %d')

            reminder['is_weekend'] = is_weekend(reminder['date'])
            reminder['is_monday_next_working_day'] = is_monday(reminder['date']) and is_today_friday()
            reminder['is_loan'] = False

            if reminder_date >= today:
                current_reminders.append(reminder)
            else:
                old_reminders.append(reminder)

        current_reminders.sort(key=get_sort_key)
        old_reminders.sort(key=get_sort_key, reverse=True)

        return {
            'current_reminders': current_reminders,
            'old_reminders': old_reminders
        }

    except sqlite3.Error as error:
        print(f"Error fetching all reminders: {error}")
        return {'current_reminders': [], 'old_reminders': []}
    finally:
        connection.close()


def calculate_pagination_info(today_reminders, tomorrow_reminders, active_loans=None, max_per_screen=7):
    """
    Calculate how many screens are needed and organize reminders accordingly
    Now includes active loans in today's items
    """
    today_items = today_reminders[:]
    if active_loans:
        today_items.extend(active_loans)

    total_items = len(today_items) + len(tomorrow_reminders)

    if total_items <= max_per_screen:
        return {
            'needs_pagination': False,
            'total_screens': 1,
            'screens': [{
                'today_reminders': today_items,
                'tomorrow_reminders': tomorrow_reminders
            }]
        }

    screens = []
    remaining_today = today_items[:]
    remaining_tomorrow = tomorrow_reminders[:]

    while remaining_today or remaining_tomorrow:
        screen_today = []
        screen_tomorrow = []
        screen_count = 0

        while remaining_today and screen_count < max_per_screen:
            screen_today.append(remaining_today.pop(0))
            screen_count += 1

        while remaining_tomorrow and screen_count < max_per_screen:
            screen_tomorrow.append(remaining_tomorrow.pop(0))
            screen_count += 1

        screens.append({
            'today_reminders': screen_today,
            'tomorrow_reminders': screen_tomorrow
        })

    return {
        'needs_pagination': True,
        'total_screens': len(screens),
        'screens': screens
    }


@app.route('/')
def manage_reminders_root():
    """
    Root route now goes to manage page
    """
    return redirect(url_for('manage_reminders'))


@app.route('/display')
def tv_display():
    """
    TV display moved to /display route
    Now includes active loans integration with days preserved and schedule API
    """
    today = datetime.now()
    next_working_day = get_next_working_day()
    next_day_name = get_next_working_day_name()

    today_str = today.strftime('%Y-%m-%d')
    next_working_day_str = next_working_day.strftime('%Y-%m-%d')

    today_reminders = get_reminders_for_date(today_str)
    next_day_reminders = get_reminders_for_date(next_working_day_str)

    active_loans_raw = get_active_loans()
    active_loans_formatted = format_loans_for_display(active_loans_raw)

    pagination_info = calculate_pagination_info(
        today_reminders,
        next_day_reminders,
        active_loans_formatted,
        max_per_screen=7
    )

    schedule_info = get_schedule_info()

    time_info = {
        'display_date': today.strftime('%a %d %b'),
        'current_time': today.strftime('%H:%M'),
        'current_period': schedule_info.get('current_period') if schedule_info else None,
        'week_type': schedule_info.get('week_type') if schedule_info else None,
        'has_schedule': schedule_info is not None
    }

    return render_template('index.html',
                           time_info=time_info,
                           pagination_info=pagination_info,
                           next_day_name=next_day_name,
                           loans_count=len(active_loans_raw))


@app.route('/manage', methods=['GET', 'POST'])
def manage_reminders():
    """
    Management page with organized reminders (current vs old) and loan viewing
    """
    if request.method == 'POST':
        action = request.form.get('action', 'add')
        form_reminder_id = request.form.get('reminder_id')
        date = request.form.get('date')
        time = request.form.get('time')
        title = request.form.get('title')
        description = request.form.get('description')
        location = request.form.get('location')

        if not date:
            flash('Date is required!', 'error')
            return redirect(url_for('manage_reminders'))

        if not title or not title.strip():
            flash('Title is required!', 'error')
            return redirect(url_for('manage_reminders'))

        if is_weekend(date):
            flash('Cannot schedule reminders on weekends! Please choose a weekday.', 'error')
            return redirect(url_for('manage_reminders'))

        try:
            reminder_date = datetime.strptime(date, '%Y-%m-%d').date()
            today_date = datetime.now().date()
            if reminder_date < today_date:
                flash('Cannot schedule reminders in the past!', 'error')
                return redirect(url_for('manage_reminders'))
        except ValueError:
            flash('Invalid date format!', 'error')
            return redirect(url_for('manage_reminders'))

        if time:
            try:
                time_obj = datetime.strptime(time, '%H:%M').time()
                time = time_obj.strftime('%H:%M:%S')
            except ValueError:
                flash('Invalid time format!', 'error')
                return redirect(url_for('manage_reminders'))

        time = time if time else None
        description = description.strip() if description else None
        location = location.strip() if location else None
        title = title.strip()

        conn = get_db_connection()
        if not conn:
            flash('Database connection failed!', 'error')
            return redirect(url_for('manage_reminders'))

        try:
            cur = conn.cursor()

            if action == 'edit' and form_reminder_id:
                cur.execute('''
                UPDATE reminders 
                SET date=?, time=?, title=?, description=?, location=?
                WHERE id=?
                ''', (date, time, title, description, location, form_reminder_id))

                if cur.rowcount > 0:
                    flash('Reminder updated successfully!', 'success')
                else:
                    flash('Reminder not found!', 'error')
            else:
                cur.execute('''
                INSERT INTO reminders (date, time, title, description, location)
                VALUES (?, ?, ?, ?, ?)
                ''', (date, time, title, description, location))
                flash('Reminder added successfully!', 'success')

            conn.commit()

        except sqlite3.Error as error:
            flash(f'Database error: {str(error)}', 'error')
        finally:
            conn.close()

        return redirect(url_for('manage_reminders'))

    reminders_data = get_all_reminders_organized()
    active_loans_raw = get_active_loans()
    active_loans_formatted = []

    for loan in active_loans_raw:
        parsed = parse_loan_string(loan)
        active_loans_formatted.append({
            'student': parsed['student'],
            'item': parsed['item'],
            'days': parsed['days'],
            'original': loan
        })

    context = {
        'current_reminders': reminders_data['current_reminders'],
        'old_reminders': reminders_data['old_reminders'],
        'is_friday': is_today_friday(),
        'active_loans': active_loans_formatted,
        'loans_count': len(active_loans_raw)
    }

    return render_template('manage.html', **context)


@app.route('/get_reminder/<int:reminder_id>')
def get_reminder(reminder_id):
    """
    API endpoint to get reminder data for editing
    """
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500

    try:
        cur = conn.cursor()
        cur.execute('SELECT * FROM reminders WHERE id = ?', (reminder_id,))
        reminder_row = cur.fetchone()

        if reminder_row:
            reminder_dict = dict(reminder_row)
            if reminder_dict['time']:
                time_obj = parse_time_safely(reminder_dict['time'])
                if time_obj:
                    reminder_dict['time'] = time_obj.strftime('%H:%M')
            return jsonify(reminder_dict)

        return jsonify({'error': 'Reminder not found'}), 404

    except sqlite3.Error as error:
        return jsonify({'error': str(error)}), 500
    finally:
        conn.close()


@app.route('/delete/<int:reminder_id>')
def delete_reminder(reminder_id):
    """
    Delete a reminder
    """
    conn = get_db_connection()
    if not conn:
        flash('Database connection failed', 'error')
        return redirect(url_for('manage_reminders'))

    try:
        cur = conn.cursor()
        cur.execute('DELETE FROM reminders WHERE id = ?', (reminder_id,))
        conn.commit()

        if cur.rowcount > 0:
            flash('Reminder deleted successfully!', 'success')
        else:
            flash('Reminder not found!', 'error')

    except sqlite3.Error as error:
        flash(f'Database error: {error}', 'error')
    finally:
        conn.close()

    return redirect(url_for('manage_reminders'))


if __name__ == '__main__':
    print("Starting TV Reminders System with Loans and Schedule Integration...")
    print("Management (Default): http://localhost:5005")
    print("TV Display: http://localhost:5005/display")
    print("Management: http://localhost:5005/manage")
    print(f"Loans API: {LOANS_API_URL}")
    print(f"Schedule API: {SCHEDULE_API_URL}")
    app.run(debug=True, host='0.0.0.0', port=5005)