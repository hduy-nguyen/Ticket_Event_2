import time
import uuid
from flask import Flask, render_template, jsonify, request, redirect, url_for, session

app = Flask(__name__)
app.secret_key = 'super_secret_key' # Cần thay bằng key phức tạp trong thực tế

# DATA MÔ PHỎNG
users = {
    "admin": {"password": "adminpass", "role": "admin"},
    "user1": {"password": "userpass", "role": "user"},
}

events = {
    "1": {"id": "1", "name": "Đại nhạc hội EDM 2026", "date": "2026-05-20", "location": "Sân vận động Mỹ Đình", "price_min": 300000, "category": "Âm nhạc"},
    "2": {"id": "2", "name": "Hội thảo AI & Future", "date": "2026-06-15", "location": "Trung tâm Hội nghị Quốc gia", "price_min": 200000, "category": "Hội thảo"},
}

# Dữ liệu ghế cho từng sự kiện
event_seats = {
    "1": {f"{r}-{c}": {"status": 0, "price": 500000 if r < 3 else 300000} for r in range(1, 6) for c in range(1, 9)},
    "2": {f"{r}-{c}": {"status": 0, "price": 200000} for r in range(1, 10) for c in range(1, 10)}
}

tickets = {} # Lưu vé đã mua: { ticket_id: {event_id, seat_id, owner} }
revenue = {"total": 0, "sold_count": 0}

# Filter cho Jinja để format tiền tệ
@app.template_filter('format')
def format_currency(value):
    return "{:,.0f}".format(value).replace(",", ".")

# TRANG CHỦ VÀ ĐĂNG NHẬP/ĐĂNG KÝ
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if username in users and users[username]['password'] == password:
            session['username'] = username
            session['role'] = users[username]['role']
            if session['role'] == 'admin':
                return redirect(url_for('admin_dashboard'))
            return redirect(url_for('home'))
        return "Sai tên đăng nhập hoặc mật khẩu!"
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('username', None)
    session.pop('role', None)
    return redirect(url_for('home'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if username in users:
            return "Tên đăng nhập đã tồn tại!"
        users[username] = {"password": password, "role": "user"}
        session['username'] = username
        session['role'] = "user"
        return redirect(url_for('home'))
    return render_template('register.html')

@app.route('/')
def home():
    """Yêu cầu 1: Duyệt và tìm kiếm sự kiện"""
    if 'username' not in session:
        return redirect(url_for('login'))
    return render_template('home.html', events=events.values(), username=session['username'])

# CHỨC NĂNG SỰ KIỆN
@app.route('/event/<event_id>')
def event_detail(event_id):
    """Yêu cầu 2: Xem chi tiết sự kiện và chọn loại vé/ghế"""
    if 'username' not in session:
        return redirect(url_for('login'))
        
    event = events.get(event_id)
    if not event: return "Sự kiện không tồn tại", 404

    # Dữ liệu ghế cho sự kiện này
    seats_data = event_seats.get(event_id, {})
    
    # Cần tạo một bản sao để thêm row/col vào từng ghế
    seats_for_template = {}
    for seat_key, seat_info in seats_data.items():
        r, c = map(int, seat_key.split('-'))
        seats_for_template[seat_key] = {"row": r, "col": c, **seat_info}

    return render_template('event_detail.html', event=event, seats=seats_for_template)

@app.route('/api/seats/<event_id>')
def get_seats_api(event_id):
    """API trả về trạng thái ghế cho frontend"""
    # Kiểm tra và nhả ghế thủ công nếu hết hạn giữ chỗ
    now = time.time()
    for s_id, s_info in event_seats[event_id].items():
        if s_info['status'] == 2 and s_info.get('hold_until') and now > s_info['hold_until']:
            s_info['status'] = 0
            s_info['hold_until'] = None
    return jsonify(event_seats.get(event_id, {}))

@app.route('/api/hold', methods=['POST'])
def hold_seat():
    """Giữ ghế trong 5 phút để thanh toán"""
    data = request.json
    e_id = data.get('event_id')
    s_id = data.get('seat_id')
    
    if e_id not in event_seats or s_id not in event_seats[e_id]:
        return jsonify({"success": False, "message": "Ghế không tồn tại!"}), 404

    seat_info = event_seats[e_id][s_id]

    if seat_info['status'] == 0: # Chỉ giữ ghế trống
        seat_info['status'] = 2 # Đang giữ chỗ
        seat_info['hold_until'] = time.time() + 300 # Giữ trong 5 phút (300 giây)
        
        # Lên lịch tự động nhả ghế sau 5 phút
        # Cần một cơ chế xử lý Timer bền vững hơn trong thực tế (Celery, Redis Queue)
        # Hiện tại dùng Timer của threading, nó sẽ chạy trong process của Flask
        def release_seat_timed(event_id, seat_id):
            with app.app_context():
                s_info = event_seats[event_id][seat_id]
                if s_info['status'] == 2 and s_info.get('hold_until') and time.time() > s_info['hold_until']:
                    s_info['status'] = 0
                    s_info['hold_until'] = None
                    print(f"Hệ thống: Ghế {seat_id} của sự kiện {event_id} đã được giải phóng.")

        from threading import Timer # Import ở đây để tránh circular import
        Timer(300, release_seat_timed, [e_id, s_id]).start()

        return jsonify({"success": True, "message": f"Đang giữ ghế {s_id} trong 5 phút để bạn thanh toán!"})
    elif seat_info['status'] == 2:
        return jsonify({"success": False, "message": "Ghế này đang được giữ bởi người khác!"}), 400
    else: # status == 1
        return jsonify({"success": False, "message": "Ghế đã có người mua!"}), 400

@app.route('/api/book', methods=['POST'])
def book_ticket():
    """Yêu cầu 3: Thanh toán và nhận vé điện tử"""
    data = request.json
    e_id = data.get('event_id')
    s_id = data.get('seat_id')
    
    if e_id not in event_seats or s_id not in event_seats[e_id]:
        return jsonify({"success": False, "message": "Ghế không tồn tại!"}), 404

    seat_info = event_seats[e_id][s_id]

    if seat_info['status'] == 2: # Phải đang ở trạng thái giữ chỗ mới được thanh toán
        seat_info['status'] = 1 # Đã bán
        seat_info['hold_until'] = None # Hủy thời gian giữ chỗ

        ticket_id = str(uuid.uuid4())[:8].upper()
        tickets[ticket_id] = {
            "event_id": e_id,
            "event_name": events[e_id]['name'], 
            "seat_id": s_id,
            "owner": session['username'], # Lưu người mua
            "status": "Valid"
        }
        
        # Cập nhật doanh thu (Yêu cầu 5)
        revenue["total"] += seat_info['price']
        revenue["sold_count"] += 1
        
        return jsonify({"success": True, "ticket_id": ticket_id, "message": f"Thanh toán thành công ghế {s_id}!"})
    
    return jsonify({"success": False, "message": "Ghế chưa được giữ hoặc đã bán!"}), 400

@app.route('/ticket/<ticket_id>')
def ticket_page(ticket_id):
    """Trang hiển thị vé điện tử"""
    if 'username' not in session:
        return redirect(url_for('login'))

    ticket = tickets.get(ticket_id)
    if not ticket or ticket['owner'] != session['username']:
        return "Vé không tồn tại hoặc bạn không phải chủ sở hữu", 404
    
    return render_template('ticket.html', ticket=ticket)

# ADMIN
@app.route('/admin')
def admin_dashboard():
    """Yêu cầu 4 & 5: Quản lý và Theo dõi doanh thu"""
    if 'username' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))

    return render_template('admin.html', revenue=revenue, events=events.values())

@app.route('/scan')
def scan_page():
    """Yêu cầu 5: Quét vé tại cổng (phiên bản đơn giản) và Nhận diện khuôn mặt (giao diện) """
    if 'username' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    return render_template('scan.html')

@app.route('/api/verify/<ticket_id>')
def verify_ticket(ticket_id):
    """API xác thực vé"""
    if 'username' not in session or session['role'] != 'admin':
        return jsonify({"success": False, "message": "Không có quyền truy cập!"}), 403

    ticket = tickets.get(ticket_id)
    if ticket and ticket['status'] == "Valid":
        ticket['status'] = "Used" # Đánh dấu đã sử dụng
        return jsonify({"success": True, "message": f"VÉ HỢP LỆ - Ghế {ticket['seat_id']} - Mời vào cổng!"})
    elif ticket and ticket['status'] == "Used":
        return jsonify({"success": False, "message": "VÉ ĐÃ ĐƯỢC SỬ DỤNG!"})
    return jsonify({"success": False, "message": "VÉ KHÔNG HỢP LỆ!"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
