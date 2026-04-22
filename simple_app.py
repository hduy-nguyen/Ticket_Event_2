from flask import Flask, render_template, request, redirect, url_for, session, flash
import mysql.connector
from mysql.connector import Error
import secrets
import uuid
import qrcode
from PIL import Image
import os

# Database configuration
db_config = {
    'host': 'localhost',
    'user': 'root',
    'password': '123456',
    'database': 'ticket_system'
}

app = Flask(__name__)
app.secret_key = secrets.token_hex(16) # Generate a random secret key
app.config['TEMPLATES_AUTO_RELOAD'] = True

def get_db_connection():
    try:
        conn = mysql.connector.connect(**db_config)
        return conn
    except Error as e:
        print(f"Error connecting to MySQL: {e}")
        return None

def get_user_id_from_session():
    return session.get('user_id')

def get_username_from_session():
    return session.get('username')

# Routes remain the same but with better error handling
@app.route('/')
def index():
    search_query = request.args.get('search', '')
    conn = get_db_connection()
    if conn is None:
        return render_template('error.html', message='Database connection failed! Please try again later.'), 500
    
    cursor = conn.cursor(dictionary=True) 
    try:
        if search_query:
            query = "SELECT id, name, location, event_date, price, guest_list FROM events WHERE name LIKE %s OR location LIKE %s"
            cursor.execute(query, (f"%{search_query}%", f"%{search_query}%"))
        else:
            cursor.execute("SELECT id, name, location, event_date, price, guest_list FROM events")
        events = cursor.fetchall()
    except Error as e:
        print(f"Error fetching events: {e}")
        events = []
    finally:
        cursor.close()
        conn.close()
        
    logged_in_user = get_username_from_session()
    return render_template('index.html', events=events, logged_in_user=logged_in_user, search_query=search_query)

@app.route('/admin')
def admin_dashboard():
    search_query = request.args.get('search', '')
    user_id = get_user_id_from_session()
    is_admin = session.get('is_admin')
    
    if not user_id or str(is_admin) != '1': 
        flash("Quyền truy cập bị từ chối.", "warning")
        return redirect(url_for('login'))

    conn = get_db_connection()
    if conn is None:
        return "Database Error", 500

    cursor = conn.cursor(dictionary=True)
    try:
        if search_query:
            query = "SELECT id, name, location, event_date, price, guest_list, category, total_slots, remaining_slots FROM events WHERE name LIKE %s OR location LIKE %s"
            cursor.execute(query, (f"%{search_query}%", f"%{search_query}%"))
        else:
            cursor.execute("SELECT id, name, location, event_date, price, guest_list, category, total_slots, remaining_slots FROM events")
        events = cursor.fetchall()

        cursor.execute("""
            SELECT t.id, e.name AS event_name, u.username, t.ticket_code, t.ticket_class, t.price as ticket_price
            FROM tickets t
            JOIN events e ON t.event_id = e.id
            JOIN users u ON t.user_id = u.id
        """)
        tickets = cursor.fetchall()
        
        total_revenue = sum(ticket['ticket_price'] for ticket in tickets if ticket['ticket_price'] is not None)

    except Error as e:
        print(f"Error: {e}")
        return "Internal Error", 500
    finally:
        cursor.close()
        conn.close()
        
    return render_template('admin_new.html', events=events, tickets=tickets, 
                           total_revenue=total_revenue, logged_in_user=get_username_from_session(), search_query=search_query)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)