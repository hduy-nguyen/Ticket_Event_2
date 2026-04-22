
import mysql.connector
from mysql.connector import Error

def create_database(connection, db_name):
    cursor = connection.cursor()
    try:
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS {db_name}")
        print(f"Database \'{db_name}\' created successfully or already exists.")
    except Error as e:
        print(f"Error creating database: {e}")
    finally:
        cursor.close()

def create_tables(connection):
    cursor = connection.cursor()
    try:
        cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(255) NOT NULL,
            password VARCHAR(255) NOT NULL
        )
        """)
        print("Table \'users\' created successfully or already exists.")

        cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS events (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            location VARCHAR(255),
            price DECIMAL(10, 2) NOT NULL
        )
        """)
        print("Table \'events\' created successfully or already exists.")

        cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS tickets (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT,
            event_id INT,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (event_id) REFERENCES events(id)
        )
        """)
        print("Table \'tickets\' created successfully or already exists.")
    except Error as e:
        print(f"Error creating tables: {e}")
    finally:
        cursor.close()

def insert_sample_events(connection):
    cursor = connection.cursor()
    events_to_insert = [
        ("Concert Anh Trai Say Hi", "Hanoi", 500000.00),
        ("Show Đen Vâu", "Ho Chi Minh City", 750000.00),
        ("Nhạc kịch", "Da Nang", 300000.00)
    ]
    try:
        # Check if events already exist to avoid duplicates
        cursor.execute("SELECT COUNT(*) FROM events")
        count = cursor.fetchone()[0]

        if count == 0:
            sql = "INSERT INTO events (name, location, price) VALUES (%s, %s, %s)"
            cursor.executemany(sql, events_to_insert)
            connection.commit()
            print(f"{cursor.rowcount} events inserted successfully.")
        else:
            print("Events already exist. Skipping insertion.")
    except Error as e:
        print(f"Error inserting sample events: {e}")
    finally:
        cursor.close()

def get_and_print_events(connection):
    cursor = connection.cursor()
    try:
        cursor.execute("SELECT id, name, location, price FROM events")
        events = cursor.fetchall()
        if events:
            print("\nDanh sách các sự kiện trong Database:")
            for event in events:
                print(f"ID: {event[0]}, Tên: {event[1]}, Địa điểm: {event[2]}, Giá: {event[3]:.2f}")
        else:
            print("Không có sự kiện nào trong Database.")
    except Error as e:
        print(f"Error fetching events: {e}")
    finally:
        cursor.close()

if __name__ == "__main__":
    db_connection = None
    try:
        # First, try to connect to the specific database
        db_connection = mysql.connector.connect(
            host='localhost',
            user='root',
            password='123456',
            database='ticket_system'
        )
        if db_connection.is_connected():
            print("Connected to MySQL database 'ticket_system'")
            create_tables(db_connection)
            insert_sample_events(db_connection)
            get_and_print_events(db_connection)

    except Error as e:
        # If connection fails (e.g., database doesn't exist or access denied)
        if e.errno == mysql.connector.errorcode.ER_BAD_DB_ERROR or "Access denied" in str(e):
            print(f"Connection failed: {e}. Attempting to create database and tables.")
            try:
                # Connect without specifying a database to create it
                db_connection_server = mysql.connector.connect(
                    host='localhost',
                    user='root',
                    password='123456'
                )
                if db_connection_server.is_connected():
                    print("Connected to MySQL server to set up database and tables.")
                    create_database(db_connection_server, 'ticket_system')
                    
                    # Now, reconnect to the specific database to create tables and insert data
                    db_connection_server.database = 'ticket_system' # Switch to the new database
                    create_tables(db_connection_server)
                    insert_sample_events(db_connection_server)
                    get_and_print_events(db_connection_server)
                    db_connection_server.close()
                    print("MySQL server connection closed after setup.")
                else:
                    print("Failed to connect to MySQL server even without database specified.")
            except Error as e_inner:
                print(f"Error during initial database/table creation or setup: {e_inner}")
        else:
            print(f"An unexpected MySQL error occurred: {e}")
    finally:
        if db_connection and db_connection.is_connected():
            db_connection.close()
            print("MySQL connection is closed")
