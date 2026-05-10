# models.py
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

# Khởi tạo db
db = SQLAlchemy()

class User(db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    full_name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(20), default='customer') # 'admin', 'organizer', 'customer'
    
    preferences = db.Column(db.JSON, nullable=True) 
    face_encoding = db.Column(db.Text, nullable=True) 
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    organized_events = db.relationship('Event', backref='organizer', lazy=True, cascade="all, delete-orphan")
    purchased_tickets = db.relationship('Ticket', backref='owner', lazy=True, cascade="all, delete-orphan")


event_guests = db.Table('event_guests',
    db.Column('event_id', db.Integer, db.ForeignKey('events.id', ondelete='CASCADE'), primary_key=True),
    db.Column('guest_id', db.Integer, db.ForeignKey('guests.id', ondelete='CASCADE'), primary_key=True)
) 

class Event(db.Model):
    __tablename__ = 'events'
    
    id = db.Column(db.Integer, primary_key=True)
    organizer_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    category = db.Column(db.String(50), nullable=False) 
    location = db.Column(db.String(255), nullable=False)
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(20), default='published') 
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationship với TicketTier
    ticket_tiers = db.relationship('TicketTier', backref='event', lazy=True, cascade="all, delete-orphan")
    guests = db.relationship('Guest', secondary=event_guests, lazy='subquery', backref=db.backref('events', lazy=True))

    @property
    def price_min(self):
        """Tự động tìm giá vé thấp nhất của sự kiện này"""
        if self.ticket_tiers:
            # Duyệt qua tất cả hạng vé và lấy giá trị current_price nhỏ nhất
            return min([tier.current_price for tier in self.ticket_tiers])
        return 0 # Nếu sự kiện chưa cấu hình hạng vé, trả về 0

class Guest(db.Model):
    __tablename__ = 'guests'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(50), default="Khách mời")

class TicketTier(db.Model):
    __tablename__ = 'ticket_tiers'
    
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('events.id'), nullable=False)
    tier_name = db.Column(db.String(50), nullable=False) 
    base_price = db.Column(db.Numeric(12, 2), nullable=False)
    current_price = db.Column(db.Numeric(12, 2), nullable=False) 
    total_capacity = db.Column(db.Integer, nullable=False)
    sold_quantity = db.Column(db.Integer, default=0)

    # --- 3 CỘT MỚI CHO TÍNH NĂNG GIÁ ĐỘNG ---
    is_dynamic = db.Column(db.Boolean, default=False)                # Bật/tắt giá động
    min_price = db.Column(db.Numeric(12, 2), nullable=True)          # Giá sàn
    max_price = db.Column(db.Numeric(12, 2), nullable=True)          # Giá trần

    # Relationship với Ticket
    tickets = db.relationship('Ticket', backref='tier', lazy=True, cascade="all, delete-orphan")

    def update_current_price(self):
        """
        Hàm logic AI: Tự động cập nhật giá dựa trên số lượng vé đã bán.
        Gọi hàm này mỗi khi một giao dịch thanh toán thành công.
        """
        if not self.is_dynamic:
            return # Nếu không bật giá động thì không làm gì cả

        # 1. Tính toán tỷ lệ lấp đầy (Số vé đã bán / Tổng số vé)
        # Ép kiểu float để tránh lỗi chia số nguyên hoặc lỗi Decimal
        fill_rate = float(self.sold_quantity) / float(self.total_capacity)

        # 2. Logic tăng giá (Ví dụ đơn giản cho đồ án):
        # Bán dưới 30%: Giữ giá gốc
        # Bán từ 30% - 60%: Tăng 10%
        # Bán từ 60% - 90%: Tăng 30%
        # Bán trên 90%: Tăng 50%
        
        factor = 1.0
        if fill_rate > 0.9:
            factor = 1.5
        elif fill_rate > 0.6:
            factor = 1.3
        elif fill_rate > 0.3:
            factor = 1.1

        # 3. Tính giá mới và ép kiểu float để tránh lỗi Decimal * float
        new_price = float(self.base_price) * factor

        # 4. Kiểm tra giới hạn Giá sàn (min_price) và Giá trần (max_price)
        # Phải ép kiểu float() cho các cột Numeric khi so sánh
        if self.min_price and new_price < float(self.min_price):
            new_price = float(self.min_price)
            
        if self.max_price and new_price > float(self.max_price):
            new_price = float(self.max_price)

        # 5. Cập nhật lại giá hiện tại
        self.current_price = new_price

class Ticket(db.Model):
    __tablename__ = 'tickets'
    
    id = db.Column(db.String(50), primary_key=True) 
    ticket_tier_id = db.Column(db.Integer, db.ForeignKey('ticket_tiers.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    purchase_price = db.Column(db.Numeric(12, 2), nullable=False) 
    purchase_time = db.Column(db.DateTime, default=datetime.utcnow)
    scan_status = db.Column(db.String(20), default='valid') 
    scanned_at = db.Column(db.DateTime, nullable=True)


class Cart(db.Model):
    __tablename__ = 'cart'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False) # Quan trọng: phải có db.ForeignKey
    tier_id = db.Column(db.Integer, db.ForeignKey('ticket_tiers.id'), nullable=False) # Quan trọng: trỏ đúng tên bảng users/ticket_tiers
    quantity = db.Column(db.Integer, default=1)
    
    tier = db.relationship('TicketTier')

class Wishlist(db.Model):
    __tablename__ = 'wishlist'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    event_id = db.Column(db.Integer, db.ForeignKey('events.id'), nullable=False)
    
    event = db.relationship('Event')