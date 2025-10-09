from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
import sqlite3
from datetime import datetime, timedelta
import math
import requests
import logging

app = Flask(__name__)

app.secret_key = 'your-secret-key-change-this-in-production'

DATABASE_NAME = 'reminders.db'
LOANS_API_URL = 'http://172.19.28.7:5006/api/active_loans'

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_active_loans():
    """
    Fetch active loans from the loan system API
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

    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching active loans: {e}")
        return []
    except ValueError as e:
        logger.error(f"Error parsing JSON response from loans API: {e}")
        return []
    except Exception as e:
        logger.error(f"Unexpected error fetching active loans: {e}")
        return []


def parse_loan_string(loan_string):
    """
    Parse loan string to extract student name and item
    Input: "T Student - Card Reader (0d)"
    Output: {"student": "T Student", "item": "Card Reader"}
    """
    try:
        # Remove the duration part (0d), (1d), etc.
        clean_string = loan_string.split(' (')[0]

        # Split by ' - ' to get student and item
        if ' - ' in clean_string:
            student, item = clean_string.split(' - ', 1)
            return {"student": student.strip(), "item": item.strip()}
        else:
            # If format doesn't match, return as is
            return {"student": "Unknown", "item": clean_string.strip()}
    except:
        return {"student": "Unknown", "item": loan_string}


def format_loans_for_display(active_loans):
    """
    Format loan data for TV display
    Converts loan strings to reminder-like objects for consistent display
    """
    formatted_loans = []

    for loan in active_loans:
        # Parse the loan string
        parsed_loan = parse_loan_string(loan)

        # Create a reminder-like object for loans
        loan_item = {
            'id': f'loan_{len(formatted_loans)}',
            'title': f"{parsed_loan['student']} - {parsed_loan['item']}",
            'description': None,
            'location': None,
            'time': None,
            'time_display': 'LOAN',
            'date': datetime.now().strftime('%Y-%m-%d'),
            'date_display': 'Today',
            'is_loan': True,
            'student': parsed_loan['student'],
            'item': parsed_loan['item']
        }
        formatted_loans.append(loan_item)

    return formatted_loans


def get_next_working_day():
    """
    Get the next working day (Monday-Friday)
    If today is Friday, return Monday. Otherwise return tomorrow.
    """
    today = datetime.now()
    if today.weekday() == 4:  # Friday (0=Monday, 4=Friday)
        return today + timedelta(days=3)  # Skip to Monday
    else:
        return today + timedelta(days=1)  # Normal next day


def get_next_working_day_name():
    """
    Get the display name for the next working day
    """
    today = datetime.now()
    if today.weekday() == 4:  # Friday
        return "Monday"
    else:
        return "Tomorrow"


def is_weekend(date_str):
    """
    Check if a given date string is a weekend
    """
    try:
        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
        return date_obj.weekday() >= 5  # Saturday=5, Sunday=6
    except:
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
        return date_obj.weekday() == 0  # Monday=0
    except:
        return False


def get_db_connection():
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
        # Try HH:MM:SS format first
        time_obj = datetime.strptime(time_str, '%H:%M:%S').time()
        return time_obj
    except ValueError:
        try:
            # Try HH:MM format (from HTML input)
            time_obj = datetime.strptime(time_str, '%H:%M').time()
            return time_obj
        except ValueError:
            # If both fail, return None
            return None


def format_time_for_display(time_str):
    """
    Format time string for display
    """
    time_obj = parse_time_safely(time_str)
    if time_obj:
        return time_obj.strftime('%I:%M %p')
    else:
        return 'All Day'


def get_reminders_for_date(date_str):
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

        # Format reminders for display
        reminders = []
        for row in cursor.fetchall():
            reminder = dict(row)

            # Format time for display
            reminder['time_display'] = format_time_for_display(reminder['time'])
            reminder['is_loan'] = False  # Flag to identify reminders vs loans

            reminders.append(reminder)

        return reminders

    except sqlite3.Error as error:
        print(f"Error fetching reminders: {error}")
        return []
    finally:
        connection.close()


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

        # Format reminders for display and categorize
        for row in cursor.fetchall():
            reminder = dict(row)

            # Parse the reminder date
            reminder_date = datetime.strptime(reminder['date'], '%Y-%m-%d').date()

            # Format time for display using the safe function
            reminder['time_display'] = format_time_for_display(reminder['time'])

            # Format date for display
            date_obj = datetime.strptime(reminder['date'], '%Y-%m-%d')
            reminder['date_display'] = date_obj.strftime('%a, %b %d')

            # Add flags for special highlighting
            reminder['is_weekend'] = is_weekend(reminder['date'])
            reminder['is_monday_next_working_day'] = is_monday(reminder['date']) and is_today_friday()
            reminder['is_loan'] = False  # Flag to identify reminders vs loans

            # Categorize reminders
            if reminder_date >= today:
                current_reminders.append(reminder)
            else:
                old_reminders.append(reminder)

        # Sort current reminders by date ASC, then by time
        current_reminders.sort(key=lambda x: (x['date'], x['time'] or '23:59:59'))

        # Sort old reminders by date DESC (most recent first), then by time
        old_reminders.sort(key=lambda x: (x['date'], x['time'] or '23:59:59'), reverse=True)

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
    # Combine today's reminders with active loans
    today_items = today_reminders[:]
    if active_loans:
        today_items.extend(active_loans)

    total_items = len(today_items) + len(tomorrow_reminders)

    if total_items <= max_per_screen:
        # All fit on one screen
        return {
            'needs_pagination': False,
            'total_screens': 1,
            'screens': [{
                'today_reminders': today_items,
                'tomorrow_reminders': tomorrow_reminders
            }]
        }

    # Need pagination
    screens = []
    remaining_today = today_items[:]
    remaining_tomorrow = tomorrow_reminders[:]

    while remaining_today or remaining_tomorrow:
        screen_today = []
        screen_tomorrow = []
        screen_count = 0

        # Fill screen with today's items first (reminders + loans)
        while remaining_today and screen_count < max_per_screen:
            screen_today.append(remaining_today.pop(0))
            screen_count += 1

        # Fill remaining space with tomorrow's reminders
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
    Now includes active loans integration
    """
    # Get current date and calculate next working day
    today = datetime.now()
    next_working_day = get_next_working_day()
    next_day_name = get_next_working_day_name()

    today_str = today.strftime('%Y-%m-%d')
    next_working_day_str = next_working_day.strftime('%Y-%m-%d')

    # Get reminders for both days
    today_reminders = get_reminders_for_date(today_str)
    next_day_reminders = get_reminders_for_date(next_working_day_str)

    # Get active loans and format them for display
    active_loans_raw = get_active_loans()
    active_loans_formatted = format_loans_for_display(active_loans_raw)

    # Calculate pagination info including loans
    pagination_info = calculate_pagination_info(
        today_reminders,
        next_day_reminders,
        active_loans_formatted,
        max_per_screen=7
    )

    # Create time information dictionary
    time_info = {
        'display_date': today.strftime('%A, %B %d, %Y'),
        'current_time': today.strftime('%I:%M %p')
    }

    # Pass pagination info and next day name to template
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
        try:
            # Get action type (add or edit)
            action = request.form.get('action', 'add')

            # Get form data
            reminder_id = request.form.get('reminder_id')  # Only for edit
            date = request.form.get('date')
            time = request.form.get('time')
            title = request.form.get('title')
            description = request.form.get('description')
            location = request.form.get('location')

            # Enhanced validation
            if not date:
                flash('Date is required!', 'error')
                return redirect(url_for('manage_reminders'))

            if not title or not title.strip():
                flash('Title is required!', 'error')
                return redirect(url_for('manage_reminders'))

            # Check if date is a weekend
            if is_weekend(date):
                flash('Cannot schedule reminders on weekends! Please choose a weekday.', 'error')
                return redirect(url_for('manage_reminders'))

            # Check if date is in the past (except for today)
            try:
                reminder_date = datetime.strptime(date, '%Y-%m-%d').date()
                today_date = datetime.now().date()
                if reminder_date < today_date:
                    flash('Cannot schedule reminders in the past!', 'error')
                    return redirect(url_for('manage_reminders'))
            except ValueError:
                flash('Invalid date format!', 'error')
                return redirect(url_for('manage_reminders'))

            # Validate time format if provided
            if time:
                try:
                    time_obj = datetime.strptime(time, '%H:%M').time()
                    time = time_obj.strftime('%H:%M:%S')
                except ValueError:
                    flash('Invalid time format!', 'error')
                    return redirect(url_for('manage_reminders'))

            # Convert empty strings to None for database
            time = time if time else None
            description = description.strip() if description else None
            location = location.strip() if location else None
            title = title.strip()

            # Process based on action
            connection = get_db_connection()
            if not connection:
                flash('Database connection failed!', 'error')
                return redirect(url_for('manage_reminders'))

            try:
                cursor = connection.cursor()

                if action == 'edit' and reminder_id:
                    cursor.execute('''
                        UPDATE reminders 
                        SET date=?, time=?, title=?, description=?, location=?
                        WHERE id=?
                        ''', (date, time, title, description, location, reminder_id))

                    if cursor.rowcount > 0:
                        flash('Reminder updated successfully!', 'success')
                    else:
                        flash('Reminder not found!', 'error')

                else:
                    cursor.execute('''
                        INSERT INTO reminders (date, time, title, description, location)
                        VALUES (?, ?, ?, ?, ?)
                        ''', (date, time, title, description, location))

                    flash('Reminder added successfully!', 'success')

                connection.commit()

            except sqlite3.Error as error:
                flash(f'Database error: {str(error)}', 'error')
            finally:
                connection.close()

        except Exception as error:
            flash(f'An unexpected error occurred: {str(error)}', 'error')

        return redirect(url_for('manage_reminders'))

    # GET request - show management interface with organized reminders and loans
    reminders_data = get_all_reminders_organized()

    # Get active loans for display in manage page
    active_loans_raw = get_active_loans()
    active_loans_formatted = []

    for loan in active_loans_raw:
        parsed = parse_loan_string(loan)
        active_loans_formatted.append({
            'student': parsed['student'],
            'item': parsed['item'],
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
    connection = get_db_connection()
    if not connection:
        return jsonify({'error': 'Database connection failed'}), 500

    try:
        cursor = connection.cursor()
        cursor.execute('SELECT * FROM reminders WHERE id = ?', (reminder_id,))
        reminder = cursor.fetchone()

        if reminder:
            reminder_dict = dict(reminder)

            # Convert time format for HTML input (HH:MM:SS to HH:MM)
            if reminder_dict['time']:
                time_obj = parse_time_safely(reminder_dict['time'])
                if time_obj:
                    reminder_dict['time'] = time_obj.strftime('%H:%M')

            return jsonify(reminder_dict)
        else:
            return jsonify({'error': 'Reminder not found'}), 404

    except sqlite3.Error as error:
        return jsonify({'error': str(error)}), 500
    finally:
        connection.close()


@app.route('/delete/<int:reminder_id>')
def delete_reminder(reminder_id):
    """
    Delete a reminder
    """
    connection = get_db_connection()
    if not connection:
        flash('Database connection failed', 'error')
        return redirect(url_for('manage_reminders'))

    try:
        cursor = connection.cursor()
        cursor.execute('DELETE FROM reminders WHERE id = ?', (reminder_id,))
        connection.commit()

        if cursor.rowcount > 0:
            flash('Reminder deleted successfully!', 'success')
        else:
            flash('Reminder not found!', 'error')

    except sqlite3.Error as error:
        flash(f'Database error: {error}', 'error')
    finally:
        connection.close()

    return redirect(url_for('manage_reminders'))


if __name__ == '__main__':
    print("Starting TV Reminders System with Loans Integration...")
    print("Management (Default): http://localhost:5000")
    print("TV Display: http://localhost:5000/display")
    print("Management: http://localhost:5000/manage")
    print(f"Loans API: {LOANS_API_URL}")
    app.run(debug=True, host='0.0.0.0', port=5000)