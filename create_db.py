import sqlite3
from datetime import datetime, timedelta
import os

DATABASE_NAME = 'reminders.db'


def create_database():
    """
    Creates the SQLite database and reminders table
    """
    print("Creating TV Reminders Database...")
    print("-" * 50)

    try:
        connection = sqlite3.connect(DATABASE_NAME)
        cursor = connection.cursor()

        print("Creating reminders table...")

        create_table_sql = '''
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            time TEXT,
            title TEXT NOT NULL,
            description TEXT,
            location TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        '''
        cursor.execute(create_table_sql)

        print("Creating database indexes...")
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_date ON reminders(date)')

        print("Database created successfully!")

        connection.commit()
        return connection, cursor

    except sqlite3.Error as error:
        print(f"Error creating database: {error}")
        return None, None


def insert_sample_data(connection, cursor):
    """
    Insert sample data spanning multiple weeks for testing
    """
    print("Adding sample reminder data...")

    # Calculate dates for testing
    today = datetime.now()
    dates = {}

    # Generate dates for comprehensive testing
    for i in range(15):  # 2+ weeks of dates
        date_key = f"day_{i}"
        dates[date_key] = (today + timedelta(days=i)).strftime('%Y-%m-%d')

    print(f"Creating reminders from {dates['day_0']} onwards...")

    # Sample data with variety of reminders
    sample_reminders = [
        # TODAY - 2 reminders
        (dates['day_0'], '09:00:00', 'Server Maintenance', 'Critical server updates', 'Server Room'),
        (dates['day_0'], '14:00:00', 'Team Meeting', 'Weekly progress review', 'Conference Room'),

        # TOMORROW - 2 reminders
        (dates['day_1'], '10:00:00', 'Network Check', 'Weekly network review', 'Network Room'),
        (dates['day_1'], '15:00:00', 'Training Session', 'Security awareness training', 'Training Room'),

        # THIS WEEK - 2 reminders
        (dates['day_2'], '11:00:00', 'Backup Verification', 'Check all system backups', 'Server Room'),
        (dates['day_3'], '13:00:00', 'Equipment Check', 'Monthly hardware inspection', 'IT Storage'),

        # NEXT WEEK - Additional reminders
        (dates['day_7'], '09:30:00', 'Budget Meeting', 'Monthly budget review', 'Executive Room'),
        (dates['day_8'], '14:00:00', 'System Update', 'Deploy software patches', 'All Systems'),
        (dates['day_9'], '16:00:00', 'Vendor Call', 'Quarterly vendor review', 'Conference Room'),

        # LATER - Future reminders
        (dates['day_14'], '10:00:00', 'Annual Review', 'IT annual assessment', 'IT Department'),
    ]

    try:
        insert_sql = """
        INSERT INTO reminders (date, time, title, description, location)
        VALUES (?, ?, ?, ?, ?)
        """
        cursor.executemany(insert_sql, sample_reminders)
        connection.commit()
        print(f"Successfully added {len(sample_reminders)} sample reminders!")

        # Simple count verification
        cursor.execute('SELECT COUNT(*) FROM reminders')
        total_count = cursor.fetchone()[0]
        print(f"Total reminders in database: {total_count}")

    except sqlite3.Error as error:
        print(f"Error inserting sample data: {error}")


def show_upcoming_reminders(cursor):
    """
    Show upcoming reminders as they will appear
    """
    print("\n" + "=" * 80)
    print("UPCOMING REMINDERS (Preview):")
    print("=" * 80)

    try:
        today = datetime.now().strftime('%Y-%m-%d')

        cursor.execute('''
        SELECT date, time, title, description, location
        FROM reminders
        WHERE date >= ?
        ORDER BY date,
            CASE WHEN time IS NULL THEN '23:59:59' ELSE time END
        LIMIT 10
        ''', (today,))

        reminders = cursor.fetchall()

        if reminders:
            for i, (date, time, title, description, location) in enumerate(reminders, 1):
                time_display = time[:5] if time else "All Day"

                print(f"{i}. {time_display:>8} | {title}")
                print(f"   Date: {date}")
                if description:
                    print(f"   Description: {description}")
                if location:
                    print(f"   Location: {location}")
                print("-" * 80)
        else:
            print("No upcoming reminders found")

    except sqlite3.Error as error:
        print(f"Error retrieving reminders: {error}")


def main():
    """
    Main function for database setup
    """
    print("TV Reminders Database Setup")
    print("Creating database for reminder management")
    print("=" * 50)

    # Check if database exists
    if os.path.exists(DATABASE_NAME):
        response = input(f"Database '{DATABASE_NAME}' exists. Recreate with fresh data? (y/n): ").lower()

        if response == 'y':
            os.remove(DATABASE_NAME)
            print("Existing database deleted")
        else:
            print("Using existing database")
            return

    # Create database and add data
    connection, cursor = create_database()

    if connection and cursor:
        insert_sample_data(connection, cursor)
        show_upcoming_reminders(cursor)
        connection.close()

        print("\n" + "=" * 50)
        print("DATABASE SETUP COMPLETED!")
        print("=" * 50)
        print(f"Database file: {DATABASE_NAME}")
        print()
        print("NEXT STEPS:")
        print("1. Run Flask app: python app.py")
        print("2. Visit: http://localhost:5000 (Management Page)")
        print("3. TV Display: http://localhost:5000/display")
        print()

    else:
        print("Database setup failed!")


if __name__ == "__main__":
    main()