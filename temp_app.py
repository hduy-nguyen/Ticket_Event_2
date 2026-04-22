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

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        confirm_password = request.form['confirm_password']

        if password != confirm_password:
            flash("Mật khẩu xác nhận không khớp.", "warning")
            return redirect(url_for('register'))

        conn = get_db_connection()
        if conn is None:
            flash("Database connection failed!", "danger")
            return redirect(url_for('register'))
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT id FROM users WHERE username = %s OR email = %s", (username, email))
            existing_user = cursor.fetchone()
            if existing_user:
                flash("Tên đăng nhập hoặc Email đã tồn tại.", "warning")
                return redirect(url_for('register'))
            
            cursor.execute("INSERT INTO users (username, email, password) VALUES (%s, %s, %s)", (username, email, password))
            conn.commit()
            flash("Registration successful! Please login.", "success")
            return redirect(url_for('login'))
        except Error as e:
            print(f"Error during registration: {e}")
            flash("An error occurred during registration.", "danger")
            conn.rollback()
        finally:
            cursor.close()
            conn.close()
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = get_db_connection()
        if conn is None:
            flash("Database connection failed!", "danger")
            return redirect(url_for('login'))
            
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("SELECT *, id, username, password FROM users WHERE username = %s", (username,))
            user = cursor.fetchone()

            if user and user['password'] == password:
                session['username'] = user['username']
                session['user_id'] = user['id']
                is_admin_val = str(user.get('is_admin', '0'))
                session['is_admin'] = is_admin_val
                flash("Login successful!", "success")
                
                if is_admin_val == '1':
                    return redirect(url_for('admin_dashboard'))
                return redirect(url_for('index'))
            else:
                flash("Invalid username or password.", "danger")
        except Error as e:
            print(f"Error during login: {e}")
            flash("An error occurred during login.", "danger")
        finally:
            cursor.close()
            conn.close()
            
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('username', None)
    session.pop('user_id', None) # Clear user_id from session
    flash("You have been logged out.", "info")
    return redirect(url_for('index'))

@app.route('/buy_ticket/<int:event_id>', methods=['GET', 'POST'])
def buy_ticket(event_id):
    user_id = get_user_id_from_session()
    if not user_id:
        flash("You need to be logged in to buy tickets.", "warning")
        return redirect(url_for('login'))

    conn = get_db_connection()
    if conn is None:
        flash("Database connection failed!", "danger")
        return redirect(url_for('index'))

    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM events WHERE id = %s", (event_id,))
        event = cursor.fetchone()
        if not event:
            flash("Sự kiện không tồn tại!", "danger")
            return redirect(url_for('index'))

        if request.method == 'POST':
            ticket_class = request.form.get('ticket_class', 'Standard')
            # Tính toán giá vé theo hạng
            base_price = event['price']
            if ticket_class == 'VIP':
                price = base_price * 1.5
            elif ticket_class == 'VVIP':
                price = base_price * 2.5
            else:
                price = base_price

            ticket_code = str(uuid.uuid4()).upper()[:8]
            
            cursor.execute("UPDATE events SET remaining_slots = remaining_slots - 1 WHERE id = %s AND remaining_slots > 0", (event_id,))
            if cursor.rowcount == 0:
                flash("Xin lỗi, sự kiện này đã hết vé!", "danger")
                return redirect(url_for('index'))

            cursor.execute("""
                INSERT INTO tickets (user_id, event_id, ticket_code, ticket_class, price) 
                VALUES (%s, %s, %s, %s, %s)
            """, (user_id, event_id, ticket_code, ticket_class, price))
            
            # QR Code và lưu file
            qr_data = f"Ticket: {ticket_code} | Class: {ticket_class} | Price: {price:.0f} VND"
            qr = qrcode.QRCode(version=1, box_size=10, border=5)
            qr.add_data(qr_data)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            qr_folder = os.path.join(os.path.dirname(__file__), 'static', 'qrcodes')
            os.makedirs(qr_folder, exist_ok=True)
            qr_file_path = os.path.join(qr_folder, f'ticket_{ticket_code}.png')
            img.save(qr_file_path)
            
            conn.commit()
            flash(f"Đặt vé {ticket_class} thành công! Mã vé: {ticket_code} - Giá: {price:.0f} VND", "success")
            return redirect(url_for('my_tickets'))
        
        return render_template('buy_ticket.html', event=event)
    except Error as e:
        print(f"Error: {e}")
        flash("Có lỗi xảy ra.", "danger")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()
    return redirect(url_for('index'))

@app.route('/my-tickets')
def my_tickets():
    user_id = get_user_id_from_session()
    if not user_id:
        flash("You need to be logged in to view your tickets.", "warning")
        return redirect(url_for('login'))

    conn = get_db_connection()
    if conn is None:
        return render_template('error.html', message='Database connection failed!'), 500

    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT t.id, e.name, e.location, e.event_date, e.guest_list, e.price, t.ticket_code, t.ticket_class, t.price as ticket_price
            from tickets t
            JOIN events e ON t.event_id = e.id
            WHERE t.user_id = %s
        """,(user_id,))
        my_tickets_list = cursor.fetchall()
    finally:
        cursor.close()
        conn.close()
        
    logged_in_user = get_username_from_session()
    return render_template('my_tickets.html', tickets=my_tickets_list, logged_in_user=logged_in_user)

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
        
        total_revenue = sum(ticket['ticket_price'] for ticket in tickets)

    except Error as e:
        print(f"Error: {e}")
        return "Internal Error", 500
    finally:
        cursor.close()
        conn.close()
        
    return render_template('admin_new.html', events=events, tickets=tickets, 
                           total_revenue=total_revenue, logged_in_user=get_username_from_session(), search_query=search_query)

@app.route('/admin/event/<int:event_id>')
def admin_event_detail(event_id):
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
        cursor.execute("SELECT * FROM events WHERE id = %s", (event_id,))
        event = cursor.fetchone()
        if not event:
            flash("Sự kiện không tồn tại!", "danger")
            return redirect(url_for('admin_dashboard'))
        
        cursor.execute("""
            SELECT t.id, u.username, t.ticket_code, t.ticket_class, t.price as ticket_price
            FROM tickets t
            JOIN users u ON t.user_id = u.id
            WHERE t.event_id = %s
        """, (event_id,))
        event_tickets = cursor.fetchall()
        
    except Error as e:
        print(f"Error: {e}")
        flash("Có lỗi xảy ra.", "danger")
        return redirect(url_for('admin_dashboard'))
    finally:
        cursor.close()
        conn.close()
        
    return render_template('admin_event_detail.html', event=event, event_tickets=event_tickets, logged_in_user=get_username_from_session())

@app.route('/admin/event/<int:event_id>/delete', methods=['POST'])
def admin_delete_event(event_id):
    user_id = get_user_id_from_session()
    is_admin = session.get('is_admin')
    
    if not user_id or str(is_admin) != '1': 
        flash("Quyền truy cập bị từ chối.", "warning")
        return redirect(url_for('login'))

    conn = get_db_connection()
    if conn is None:
        flash("Database connection failed!", "danger")
        return redirect(url_for('admin_dashboard'))

    cursor = conn.cursor()
    try:
        # First delete related tickets
        cursor.execute("DELETE FROM tickets WHERE event_id = %s", (event_id,))
        # Then delete the event
        cursor.execute("DELETE FROM events WHERE id = %s", (event_id,))
        
        if cursor.rowcount == 0:
            flash("Sự kiện không tồn tại.", "warning")
        else:
            flash("Sự kiện đã được xóa thành công.", "success")
        
        conn.commit()
    except Error as e:
        print(f"Error deleting event: {e}")
        flash("Có lỗi xảy ra khi xóa sự kiện.", "danger")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()
        
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/event/<int:event_id>/update', methods=['POST'])
def admin_update_event(event_id):
    user_id = get_user_id_from_session()
    is_admin = session.get('is_admin')
    
    if not user_id or str(is_admin) != '1': 
        flash("Quyền truy cập bị từ chối.", "warning")
        return redirect(url_for('login'))

    conn = get_db_connection()
    if conn is None:
        flash("Database connection failed!", "danger")
        return redirect(url_for('admin_dashboard'))

    cursor = conn.cursor()
    try:
        # Get form data
        new_date = request.form.get('event_date')
        new_price = request.form.get('price')
        
        # Build dynamic query
        updates = []
        params = []
        
        if new_date:
            updates.append("event_date = %s")
            params.append(new_date)
        
        if new_price:
            updates.append("price = %s")
            params.append(float(new_price))
        
        if updates:
            query = "UPDATE events SET " + ", ".join(updates) + " WHERE id = %s"
            params.append(event_id)
            
            cursor.execute(query, params)
            
            if cursor.rowcount > 0:
                flash("Thông tin sự kiện đã được cập nhật.", "success")
            else:
                flash("Không có thay đổi nào được thực hiện.", "warning")
        else:
            flash("Vui lòng cung cấp ít nhất một thông tin để cập nhật.", "warning")
        
        conn.commit()
    except Error as e:
        print(f"Error updating event: {e}")
        flash("Có lỗi xảy ra khi cập nhật sự kiện.", "danger")
        conn.rollback()
    except ValueError:
        flash("Giá vé không hợp lệ.", "danger")
    finally:
        cursor.close()
        conn.close()
        
    return redirect(url_for('admin_event_detail', event_id=event_id))

@app.route('/add_event', methods=['POST'])
def add_event():
    user_id = get_user_id_from_session()
    is_admin = session.get('is_admin', False)
    if not user_id or not is_admin: 
        flash("You must be logged in as an administrator to add events.", "warning")
        return redirect(url_for('login'))

    conn = get_db_connection()
    if conn is None:
        flash("Database connection failed! Cannot add event.", "danger")
        return redirect(url_for('admin_dashboard'))

    cursor = conn.cursor()
    try:
        event_name = request.form['name']
        event_location = request.form['location']
        event_price = request.form['price']
        event_category = request.form.get('category', 'General')
        event_slots = request.form.get('total_slots', 100)

        cursor.execute("""
            INSERT INTO events (name, location, price, category, total_slots, remaining_slots) 
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (event_name, event_location, event_price, event_category, event_slots, event_slots))
        
        conn.commit()
        flash("Event added successfully!", "success")
    except Error as e:
        print(f"Error adding event: {e}")
        flash("An error occurred while adding the event.", "danger")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()
        
    return redirect(url_for('admin_dashboard'))


# --- Admin User Creation ---
# This is a helper function to create the admin user. 
# In a production environment, you would not typically hardcode user creation like this.
# Consider using a dedicated script or initial setup process.
def create_admin_user():
    conn = get_db_connection()
    if conn is None:
        print("Failed to connect to the database. Cannot create admin user.")
        return False
    
    cursor = conn.cursor()
    username = 'admin1'
    password = '123' # WARNING: Store passwords securely hashed in production!
    
    try:
        # Check if admin user already exists
        cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
        existing_user = cursor.fetchone()

        if existing_user:
            print(f"User '{username}' already exists.")
            return True # User already exists, consider it a success for this purpose
        
        # Insert new admin user
        cursor.execute("INSERT INTO users (username, password) VALUES (%s, %s)", (username, password))
        conn.commit()
        print(f"Admin user '{username}' created successfully.")
        return True
    except Error as e:
        print(f"Error creating admin user: {e}")
        conn.rollback()
        return False
    finally:
        cursor.close()
        conn.close()

if __name__ == '__main__':
    # Create the admin user when the script is run directly
    create_admin_user()
    app.run(debug=True, host='0.0.0.0', port=5000)