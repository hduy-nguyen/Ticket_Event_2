import uuid
from datetime import datetime
from flask import Flask, render_template, jsonify, request, redirect, url_for, session, flash
from models import db, User, Event, Ticket, TicketTier, Cart, Wishlist, Guest
from sqlalchemy import or_
from sqlalchemy import func
from mail_service import mail, send_ticket_email

app = Flask(__name__)
app.secret_key = 'super_secret_key'

# Cấu hình MySQL
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:123456@localhost/event_ticketing_db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

# 1. CẤU HÌNH THÔNG TIN GMAIL
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'nguyenhoangduy18092004@gmail.com' # Thay bằng mail của bạn
app.config['MAIL_PASSWORD'] = 'mmzlgkyojxmodowy' 

# 2. KẾT NỐI MAIL VÀO APP
mail.init_app(app)

# Tự động tạo bảng nếu chưa có
with app.app_context():
    db.create_all()

# Filter format tiền tệ
@app.template_filter('format')
def format_currency(value):
    if value is None or str(value) == 'Undefined':
        return "0"
    try:
        return "{:,.0f}".format(float(value)).replace(",", ".")
    except (ValueError, TypeError):
        return "0"

# ==========================================
# HỆ THỐNG XÁC THỰC (AUTH)
# ==========================================
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        
        if user and user.password_hash == password:
            session['user_id'] = user.id
            session['username'] = user.username
            session['role'] = user.role
            
            if user.role == 'admin':
                return redirect(url_for('admin_dashboard'))
            elif user.role == 'organizer':
                return redirect(url_for('organizer_dashboard'))
            return redirect(url_for('home'))
            
        return "Sai tên đăng nhập hoặc mật khẩu!"
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        
        if password != confirm_password:
            return "Mật khẩu xác nhận không khớp!"
            
        if User.query.filter_by(username=username).first() or User.query.filter_by(email=email).first():
            return "Tên đăng nhập hoặc Email đã tồn tại!"
            
        new_user = User(
            username=username, 
            password_hash=password, 
            email=email, 
            full_name=username, 
            role="customer"
        )
        db.session.add(new_user)
        db.session.commit()
        
        session['user_id'] = new_user.id
        session['username'] = new_user.username
        session['role'] = new_user.role
        return redirect(url_for('home'))
        
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ==========================================
# DÀNH CHO KHÁCH HÀNG (CUSTOMER)
# ==========================================
@app.route('/')
def home():
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    user = db.session.get(User, session['user_id'])
    search_query = request.args.get('q', '')
    
    query = Event.query.filter_by(status='published')
    
    if search_query:
        query = query.filter(or_(
            Event.title.ilike(f'%{search_query}%'),
            Event.category.ilike(f'%{search_query}%'),
            Event.location.ilike(f'%{search_query}%')
        ))
        
    all_events = query.order_by(Event.start_time.asc()).all()
    
    recommended_events = []
    if user.preferences and not search_query:
        recommended_events = Event.query.filter(
            Event.status == 'published',
            Event.category.in_(user.preferences)
        ).order_by(Event.start_time.asc()).limit(5).all()

    return render_template('home.html', 
                           all_events=all_events, 
                           recommended_events=recommended_events, 
                           user=user, 
                           search_query=search_query)

@app.route('/profile', methods=['GET', 'POST'])
def profile():
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    user = db.session.get(User, session['user_id'])
    available_categories = ['Âm nhạc', 'Công nghệ', 'Hội thảo', 'Thể thao', 'Nghệ thuật', 'Giải trí']

    if request.method == 'POST':
        user.preferences = request.form.getlist('preferences')
        db.session.commit()
        return redirect(url_for('home'))

    return render_template('profile.html', user=user, categories=available_categories)

# ==========================================
# CHI TIẾT & MUA VÉ 
# ==========================================

# Cap nhat gia tu dong
def update_ticket_price(tier, event):
    """Hàm tính toán và cập nhật giá vé động"""
    if not tier.is_dynamic or tier.base_price <= 0:
        return tier.current_price

    # 1. Lấy giá gốc làm chuẩn
    new_price = tier.base_price
    
    # 2. Logic theo số lượng (Ví dụ: còn ít hơn 10% vé thì tăng giá)
    occupancy = tier.sold_quantity / tier.total_capacity
    if occupancy > 0.9:
        new_price = float(new_price) * 1.5  # Tăng 50% giá
    elif occupancy > 0.7:
        new_price = float(new_price) * 1.2  # Tăng 20% giá

    # 3. Logic theo thời gian (Ví dụ: còn dưới 3 ngày thì tăng giá FOMO)
    days_to_event = (event.start_time - datetime.now()).days
    if 0 < days_to_event <= 3:
        new_price = float(new_price) * 1.2

    # 4. Kiểm tra giới hạn trần/sàn
    if tier.min_price and new_price < tier.min_price:
        new_price = tier.min_price
    if tier.max_price and new_price > tier.max_price:
        new_price = tier.max_price

    return round(new_price, -3) 


@app.route('/event/<int:event_id>')
def event_detail(event_id):
    event = db.session.get(Event, event_id)
    if not event:
        return "Không tìm thấy sự kiện", 404

    # === BẮT ĐẦU: CẬP NHẬT GIÁ REAL-TIME TRƯỚC KHI HIỂN THỊ ===
    if event.ticket_tiers:
        tier = event.ticket_tiers[0]
        # Chỉ cập nhật nếu sự kiện đang bật Giá động
        if tier.is_dynamic:
            # Gọi hàm bộ não AI để lấy giá mới nhất
            real_time_price = update_ticket_price(tier, event)
            
            # Nếu có sự sai lệch do nhu cầu tăng/giảm, lưu lại ngay
            if tier.current_price != real_time_price:
                tier.current_price = real_time_price
                db.session.commit()
    # === KẾT THÚC ===

    return render_template('event_detail.html', event=event)


@app.route('/api/book', methods=['POST'])
def book_ticket():
    if 'user_id' not in session:
        return jsonify({"success": False, "message": "Vui lòng đăng nhập!"}), 401

    data = request.json
    tier_id = data.get('tier_id')
    tier = db.session.get(TicketTier, tier_id) 
    
    if not tier or tier.sold_quantity >= tier.total_capacity:
        return jsonify({"success": False, "message": "Hết vé hoặc hạng vé không tồn tại!"}), 400
        
    try:
        tier.sold_quantity += 1
        occupancy_rate = (tier.sold_quantity / tier.total_capacity)
        
        if occupancy_rate >= 0.8:
            tier.current_price = float(tier.base_price) * 1.1
        
        ticket_id = str(uuid.uuid4())[:8].upper()
        new_ticket = Ticket(
            id=ticket_id, ticket_tier_id=tier.id, user_id=session['user_id'],
            purchase_price=tier.current_price, scan_status='valid'
        )
        db.session.add(new_ticket)
        db.session.commit()
        return jsonify({"success": True, "ticket_id": ticket_id, "message": "Mua vé thành công!"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/ticket/<ticket_id>')
def ticket_page(ticket_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    ticket = db.get_or_404(Ticket, ticket_id)
    if ticket.user_id != session['user_id']:
        return "Quyền truy cập bị từ chối", 403
    return render_template('ticket.html', ticket=ticket)

@app.route('/my-tickets') # Hoặc /profile
def my_tickets():
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    # Lấy toàn bộ vé của user đang đăng nhập
    tickets = Ticket.query.filter_by(user_id=session['user_id']).all()
    
    return render_template('my_tickets.html', my_tickets=tickets)

# ==========================================
# QUẢN TRỊ (ADMIN & ORGANIZER)
# ==========================================
@app.route('/admin')
def admin_dashboard():
    if session.get('role') != 'admin':
        return redirect(url_for('login'))
    
    search_query = request.args.get('q', '')
    total_revenue = db.session.query(db.func.sum(Ticket.purchase_price)).scalar() or 0
    total_tickets = Ticket.query.count()
    total_users = User.query.count()
    
    event_query = Event.query
    user_query = User.query
    
    if search_query:
        event_query = event_query.filter(Event.title.ilike(f'%{search_query}%'))
        user_query = user_query.filter(or_(User.username.ilike(f'%{search_query}%'), User.email.ilike(f'%{search_query}%')))
        
    return render_template('admin_dashboard.html', total_revenue=total_revenue, total_tickets=total_tickets, total_users=total_users, events=event_query.all(), users=user_query.all(), search_query=search_query)

@app.route('/admin/approve_event/<int:event_id>', methods=['POST'])
def admin_approve_event(event_id):
    # 1. Kiểm tra phải đúng là Admin không
    if session.get('role') != 'admin':
        return "Không có quyền truy cập", 403
        
    # 2. Tìm sự kiện và đổi trạng thái
    event = db.session.get(Event, event_id)
    if event:
        event.status = 'published' # Đổi thành đã duyệt / mở bán
        db.session.commit() # Lưu vào Database
        
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/reject_event/<int:event_id>', methods=['POST'])
def admin_reject_event(event_id):
    if session.get('role') != 'admin':
        return "Không có quyền truy cập", 403
        
    event = db.session.get(Event, event_id)
    if event:
        event.status = 'cancelled' # Đổi trạng thái thành Đã hủy
        db.session.commit()
        
    return redirect(url_for('admin_dashboard'))

@app.route('/organizer')
def organizer_dashboard():
    if session.get('role') != 'organizer':
        return redirect(url_for('login'))
    
    user_id = session['user_id']

    search_query = request.args.get('q', '')
    
    query = Event.query.filter_by(organizer_id=user_id)
    if search_query:
        query = query.filter(Event.title.ilike(f'%{search_query}%'))
        
    my_events = query.all()
    
    revenue_data = db.session.query(
        Event.title,
        func.sum(Ticket.purchase_price).label('event_revenue')
    ).join(TicketTier, TicketTier.event_id == Event.id)\
     .join(Ticket, Ticket.ticket_tier_id == TicketTier.id)\
     .filter(Event.organizer_id == user_id)\
     .group_by(Event.id).all()

    chart_labels = [row[0] for row in revenue_data]
    chart_values = [float(row[1]) for row in revenue_data]

    tickets_sold = db.session.query(Ticket).join(TicketTier).join(Event).filter(Event.organizer_id == user_id).all()
    total_revenue = sum(float(t.purchase_price) for t in tickets_sold)

    return render_template('organizer_dashboard.html', 
                           events=my_events, 
                           total_revenue=total_revenue, 
                           total_tickets_sold=len(tickets_sold),
                           chart_labels=chart_labels,
                           chart_values=chart_values,
                           search_query=search_query)

@app.route('/organizer/create_event', methods=['POST'])
def create_event():
    if session.get('role') != 'organizer': 
        return redirect(url_for('login'))
    
    try:
        # Lấy dữ liệu thời gian
        start_time = datetime.strptime(request.form['start_time'], '%Y-%m-%dT%H:%M')
        end_time = datetime.strptime(request.form['end_time'], '%Y-%m-%dT%H:%M')
        
        # Tạo Event mới
        new_event = Event(
            organizer_id=session['user_id'], 
            title=request.form['title'], 
            category=request.form['category'],
            location=request.form['location'], 
            start_time=start_time, 
            end_time=end_time, 
            status='draft'
        )
        db.session.add(new_event)
        db.session.flush() # Lấy ID để nạp vào TicketTier bên dưới
        
        # Lấy dữ liệu Giá động
        is_dynamic = request.form.get('is_dynamic') == '1'
        min_price = request.form.get('min_price')
        max_price = request.form.get('max_price')

        # Tạo Hạng vé kèm theo cấu hình AI
        base_price = float(request.form['base_price'])
        default_tier = TicketTier(
            event_id=new_event.id, 
            tier_name="Vé Phổ thông", 
            base_price=base_price,
            current_price=base_price, 
            total_capacity=int(request.form['capacity']),
            sold_quantity=0,
            is_dynamic=is_dynamic,
            min_price=float(min_price) if min_price and min_price.strip() else None,
            max_price=float(max_price) if max_price and max_price.strip() else None
        )
        db.session.add(default_tier)
        db.session.commit()
        flash("🎉 Tạo sự kiện và cấu hình giá thành công!", "success")

    except Exception as e:
        db.session.rollback()
        flash(f"Lỗi: {str(e)}", "danger")

    return redirect(url_for('organizer_dashboard'))

@app.route('/organizer/edit_event/<int:event_id>', methods=['GET', 'POST'])
def edit_event(event_id):
    if session.get('role') != 'organizer':
        return redirect(url_for('login'))
        
    event = db.session.get(Event, event_id)
    if not event or event.organizer_id != session['user_id']:
        return "Bạn không có quyền chỉnh sửa sự kiện này!", 403

    if request.method == 'POST':
        try:
            event.title = request.form['title']
            event.category = request.form['category']
            event.location = request.form['location']
            event.description = request.form.get('description', '')
            event.start_time = datetime.strptime(request.form['start_time'], '%Y-%m-%dT%H:%M')
            event.end_time = datetime.strptime(request.form['end_time'], '%Y-%m-%dT%H:%M')

            base_price = request.form.get('base_price', 0)
            capacity = request.form.get('capacity', 0)

            # --- 1. BẮT DỮ LIỆU GIÁ ĐỘNG TỪ FORM ---
            is_dynamic = request.form.get('is_dynamic') == '1'
            
            # Xử lý giá sàn, giá trần (nếu bỏ trống thì gán là None)
            min_price_raw = request.form.get('min_price')
            min_price = float(min_price_raw) if min_price_raw and min_price_raw.strip() else None
            
            max_price_raw = request.form.get('max_price')
            max_price = float(max_price_raw) if max_price_raw and max_price_raw.strip() else None
            
            if event.ticket_tiers:
                tier = event.ticket_tiers[0]
                tier.base_price = base_price
                tier.total_capacity = capacity
                
                # --- 2. CẬP NHẬT CẤU HÌNH VÀO TIER ĐÃ CÓ ---
                tier.is_dynamic = is_dynamic
                tier.min_price = min_price
                tier.max_price = max_price
                
                # Nếu tắt giá động, ép giá hiện tại về lại giá gốc. 
                # Nếu đang bật, giữ nguyên để hàm update_ticket_price tự lo ở trang chi tiết
                if not is_dynamic:
                    tier.current_price = base_price
                
            else:
                # --- 3. ÁP DỤNG CẤU HÌNH CHO TIER MỚI TẠO ---
                new_tier = TicketTier(
                    event_id=event.id,
                    tier_name="Vé Phổ thông",
                    base_price=base_price,
                    current_price=base_price,
                    total_capacity=capacity,
                    is_dynamic=is_dynamic,
                    min_price=min_price,
                    max_price=max_price
                )
                db.session.add(new_tier)

            event.guests = [] 
            guest_names_raw = request.form.get('guests', '')
            if guest_names_raw:
                guest_names = [name.strip() for name in guest_names_raw.split(',') if name.strip()]
                for name in guest_names:
                    guest = Guest.query.filter_by(name=name).first()
                    if not guest:
                        guest = Guest(name=name, role="Khách mời")
                        db.session.add(guest)
                    event.guests.append(guest)

            db.session.commit()
            return redirect(url_for('organizer_dashboard'))
            
        except Exception as e:
            db.session.rollback()
            return f"Lỗi khi cập nhật: {str(e)}", 500

    current_guests = ", ".join([g.name for g in event.guests])
    return render_template('edit_event.html', event=event, current_guests=current_guests)

@app.route('/organizer/bat-gia-dong-all', methods=['POST'])
def organizer_enable_dynamic_all():
    if session.get('role') != 'organizer': 
        return redirect(url_for('login'))

    user_id = session['user_id']
    count = 0
    
    try:
        # Lấy tất cả sự kiện do Nhà tổ chức này tạo
        # (Lưu ý: Đảm bảo cột user_id khớp với cột lưu chủ sự kiện trong bảng Event của bạn)
        my_events = Event.query.filter_by(organizer_id=user_id).all()
        
        for event in my_events:
            # Duyệt qua các hạng vé của từng sự kiện
            if event.ticket_tiers:
                for tier in event.ticket_tiers:
                    if not tier.is_dynamic:
                        tier.is_dynamic = True
                    
                    # Tự động set giá sàn và trần nếu họ chưa từng set
                    if not tier.min_price:
                        tier.min_price = tier.base_price
                    if not tier.max_price:
                            # Nếu bạn muốn giá trần mặc định cao hơn 50%
                        tier.max_price = float(tier.base_price) * 1.5
                            
                    count += 1
                    
        db.session.commit()
        # Gửi thông báo màu xanh lá ra ngoài giao diện
        flash(f'⚡ Tuyệt vời! Đã bật Giá linh hoạt tự động cho {count} hạng vé của bạn.', 'success')
        
    except Exception as e:
        db.session.rollback()
        # Gửi thông báo lỗi màu đỏ
        flash(f'Đã xảy ra lỗi: {str(e)}', 'danger')
        
    # Chuyển hướng lại trang Dashboard (Thay bằng tên router render dashboard của bạn nếu khác)
    return redirect(url_for('organizer_dashboard'))

@app.route('/organizer/tat-gia-dong-all', methods=['POST'])
def organizer_disable_dynamic_all():
    if session.get('role') != 'organizer': 
        return redirect(url_for('login'))
        
    user_id = session['user_id']
    count = 0
    try:
        # Lấy tất cả sự kiện của Organizer này
        my_events = Event.query.filter_by(organizer_id=user_id).all() 
        
        for event in my_events:
            for tier in event.ticket_tiers:
                if tier.is_dynamic:
                    # Tắt trạng thái giá động
                    tier.is_dynamic = False
                    # (Tùy chọn) Reset giá hiện tại về giá gốc khi tắt
                    tier.current_price = tier.base_price
                    count += 1
        
        db.session.commit()
        flash(f'Successfully disabled AI pricing for {count} ticket tiers.', 'info')
    except Exception as e:
        db.session.rollback()
        flash(f'Lỗi khi tắt: {str(e)}', 'danger')
        
    return redirect(url_for('organizer_dashboard'))

@app.route('/organizer/publish_event/<int:event_id>', methods=['POST'])
def publish_event(event_id):
    if session.get('role') != 'organizer':
        return redirect(url_for('login'))
        
    event = db.session.get(Event, event_id)
    # Kiểm tra xem sự kiện có đúng là của người này tạo không
    if event and event.organizer_id == session['user_id']:
        event.status = 'published' # Đổi sang trạng thái mở bán
        db.session.commit()
        
    return redirect(url_for('organizer_dashboard'))

@app.route('/api/verify/<ticket_id>', methods=['POST'])
def verify_ticket(ticket_id):
    if session.get('role') not in ['admin', 'organizer']:
        return jsonify({"success": False, "message": "Không có quyền!"}), 403

    ticket = db.session.get(Ticket, ticket_id)
    
    if not ticket:
        return jsonify({"success": False, "message": "Mã vé không tồn tại!"}), 404
        
    if ticket.scan_status == "used":
        return jsonify({"success": False, "message": f"CẢNH BÁO: Vé đã được sử dụng lúc {ticket.scanned_at.strftime('%H:%M - %d/%m/%Y')}!"}), 400
        
    if ticket.scan_status == "valid":
        ticket.scan_status = "used"
        ticket.scanned_at = datetime.utcnow()
        db.session.commit()
        
        user_name = ticket.owner.full_name
        event_name = ticket.tier.event.title
        tier_name = ticket.tier.tier_name
        
        return jsonify({
            "success": True, 
            "message": f"HỢP LỆ! Khách hàng: {user_name} | Sự kiện: {event_name} | Hạng vé: {tier_name}"
        })
        
    return jsonify({"success": False, "message": "Trạng thái vé không xác định!"}), 400

# ==========================================
# GIỎ HÀNG VÀ THANH TOÁN (CẬP NHẬT MỚI)
# ==========================================
@app.route('/api/cart/add', methods=['POST'])
def add_to_cart():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Vui lòng đăng nhập để mua vé'})

    data = request.json
    tier_id = data.get('tier_id')
    
    # Lấy số lượng khách muốn mua, mặc định là 1 nếu khách không truyền lên
    requested_qty = int(data.get('quantity', 1))

    tier = db.session.get(TicketTier, tier_id)
    if not tier:
        return jsonify({'success': False, 'message': 'Không tìm thấy hạng vé'})

    # 1. KIỂM TRA BẢO MẬT: Chống mua lố số lượng vé còn lại trong kho
    available_tickets = tier.total_capacity - tier.sold_quantity
    if requested_qty <= 0:
        return jsonify({'success': False, 'message': 'Số lượng vé không hợp lệ'})
    if requested_qty > available_tickets:
        return jsonify({'success': False, 'message': f'Rất tiếc, chỉ còn {available_tickets} vé cho hạng này.'})

    # 2. XỬ LÝ GIỎ HÀNG
    cart_item = Cart.query.filter_by(user_id=session['user_id'], tier_id=tier_id).first()
    
    if cart_item:
        # Nếu vé đã có trong giỏ, cộng dồn số lượng. 
        # Cần kiểm tra xem tổng (trong giỏ + mới thêm) có lố kho không
        if cart_item.quantity + requested_qty > available_tickets:
            return jsonify({'success': False, 'message': 'Tổng số vé trong giỏ và vé mua thêm vượt quá số lượng cho phép!'})
            
        cart_item.quantity += requested_qty
    else:
        # Nếu vé chưa có trong giỏ, tạo mới
        cart_item = Cart(user_id=session['user_id'], tier_id=tier_id, quantity=requested_qty)
        db.session.add(cart_item)

    try:
        db.session.commit()
        return jsonify({'success': True, 'message': 'Thêm vào giỏ thành công'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Đã xảy ra lỗi hệ thống'})


@app.route('/api/cart/remove/<int:item_id>', methods=['POST'])
def remove_from_cart(item_id):
    if 'user_id' not in session: 
        return redirect(url_for('login'))
    
    # Tìm món hàng trong giỏ bằng ID
    item = db.session.get(Cart, item_id)
    
    # Bảo mật: Kiểm tra xem món hàng này có thuộc về người dùng hiện tại không
    if item and item.user_id == session['user_id']:
        db.session.delete(item)
        db.session.commit()
        
    return redirect(url_for('view_cart'))

@app.route('/cart')
def view_cart():
    if 'user_id' not in session: 
        return redirect(url_for('login'))
        
    cart_items = Cart.query.filter_by(user_id=session['user_id']).all()
    
    # === BẮT ĐẦU: LOGIC CHỐT CHẶN GIÁ ĐỘNG ===
    price_changed = False
    
    for item in cart_items:
        tier = item.tier
        # Lấy thông tin sự kiện để đưa vào hàm tính giá
        event = db.session.get(Event, tier.event_id) 
        
        if event:
            # Gọi "bộ não" tính giá thời gian thực
            real_time_price = update_ticket_price(tier, event)
            
            # Nếu giá thực tế bị chênh lệch so với giá đang lưu trong DB
            if tier.current_price != real_time_price:
                tier.current_price = real_time_price
                price_changed = True
                
    # Lưu thay đổi và Báo động cho người dùng biết
    if price_changed:
        db.session.commit()

        flash("⚠️ Giá của một số vé trong giỏ hàng đã thay đổi do cập nhật theo nhu cầu thực tế. Vui lòng kiểm tra lại tổng tiền trước khi thanh toán!", "warning")


    # Tính tổng tiền (lúc này tier.current_price đã là giá mới nhất)
    total_price = sum(item.tier.current_price * item.quantity for item in cart_items)
    
    return render_template('cart.html', items=cart_items, total=total_price)

# ĐIỀN THÔNG TIN KHÁCH HÀNG
@app.route('/checkout_info', methods=['GET'])
def checkout_info():
    if 'user_id' not in session: return redirect(url_for('login'))
    
    cart_items = Cart.query.filter_by(user_id=session['user_id']).all()
    if not cart_items:
        return redirect(url_for('view_cart'))
        
    total_amount = sum(item.tier.current_price * item.quantity for item in cart_items)
    user = db.session.get(User, session['user_id'])
    
    return render_template('checkout_info.html', cart_items=cart_items, total=total_amount, user=user)

# HIỂN THỊ MÃ QR THANH TOÁN
@app.route('/payment', methods=['POST'])
def payment():
    if 'user_id' not in session: return redirect(url_for('login'))
    
    # Lấy thông tin từ Form do khách hàng vừa nhập
    buyer_info = {
        'fullname': request.form.get('fullname'),
        'dob': request.form.get('dob'),
        'phone': request.form.get('phone'),
        'email': request.form.get('email'),
        'gender': request.form.get('gender')
    }
    
    # Lưu vào session để dùng ở bước xác nhận
    session['buyer_info'] = buyer_info
    
    cart_items = Cart.query.filter_by(user_id=session['user_id']).all()
    total_amount = sum(item.tier.current_price * item.quantity for item in cart_items)
    
    qr_url = f"https://api.vietqr.io/image/970415-123456789-f5z5p5.jpg?amount={total_amount}&addInfo=ThanhToanVe_{session['username']}"
    
    return render_template('payment.html', qr_url=qr_url, amount=total_amount, buyer_info=buyer_info)

# XÁC NHẬN THANH TOÁN VÀ GỬI MAIL
@app.route('/api/confirm_payment', methods=['POST'])
def confirm_payment():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user_id = session['user_id']
    cart_items = Cart.query.filter_by(user_id=user_id).all()
    
    if not cart_items:
        return "Giỏ hàng trống!", 400

    try:
        new_tickets_list = []
        
        for item in cart_items:
            # 1. Cập nhật số lượng đã bán cho Hạng vé (tăng theo số lượng trong giỏ)
            # Chúng ta thực hiện việc này TRƯỚC khi tính lại giá
            item.tier.sold_quantity += item.quantity
            
            # 2. Kích hoạt AI tính toán lại giá mới dựa trên số lượng vừa bán
            if item.tier.is_dynamic:
                item.tier.update_current_price() 
                # Lưu ý: Hàm update_current_price() đã có float() trong models.py nên sẽ không lỗi

            # 3. Tạo từng vé lẻ dựa trên số lượng khách mua
            for _ in range(item.quantity):
                ticket_id = str(uuid.uuid4())[:8].upper()
                
                new_ticket = Ticket(
                    id=ticket_id,
                    ticket_tier_id=item.tier_id,
                    user_id=user_id,
                    # Lưu giá tại thời điểm mua (đã được AI cập nhật ở bước 2)
                    purchase_price=item.tier.current_price, 
                    scan_status='valid'
                )
                db.session.add(new_ticket)
                new_tickets_list.append(new_ticket)

        # 4. Xóa sạch giỏ hàng của người dùng sau khi đã tạo vé xong
        Cart.query.filter_by(user_id=user_id).delete()
        
        # 5. Chốt hạ giao dịch Database
        db.session.commit()
        
        # 6. Xử lý gửi Email thông báo vé
        buyer_info = session.get('buyer_info')
        if buyer_info and new_tickets_list:
            try:
                send_ticket_email(buyer_info, new_tickets_list, app.config['MAIL_USERNAME'])
                session.pop('buyer_info', None) 
            except Exception as email_err:
                # Log lỗi email nhưng vẫn cho khách tiếp tục (vì vé đã tạo xong trong DB)
                print(f"Lỗi gửi email: {email_err}")
            
        return redirect(url_for('my_tickets'))
        
    except Exception as e:
        db.session.rollback()
        # Log lỗi chi tiết ra console để bạn dễ debug
        print(f"CRITICAL ERROR: {str(e)}")
        return f"Lỗi hệ thống: {str(e)}", 500

@app.route('/api/wishlist/toggle', methods=['POST'])
def toggle_wishlist():
    if 'user_id' not in session: return jsonify({"success": False}), 401
    event_id = request.json.get('event_id')
    item = Wishlist.query.filter_by(user_id=session['user_id'], event_id=event_id).first()
    
    if item:
        db.session.delete(item)
        msg = "Đã bỏ quan tâm"
    else:
        db.session.add(Wishlist(user_id=session['user_id'], event_id=event_id))
        msg = "Đã thêm vào danh sách quan tâm"
    
    db.session.commit()
    return jsonify({"success": True, "message": msg})

if __name__ == '__main__':
    app.run(debug=True)