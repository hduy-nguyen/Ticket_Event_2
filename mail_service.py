from flask_mail import Mail, Message
from flask import render_template

# Tạo đối tượng mail nhưng chưa gắn vào app vội
mail = Mail()

def send_ticket_email(buyer_info, tickets, sender_email):
    """
    Hàm xử lý việc gửi vé điện tử
    """
    try:
        # 1. Tạo tiêu đề và người nhận
        msg = Message(
            subject=f"🎟️ Vé điện tử của bạn - {tickets[0].tier.event.title}",
            sender=sender_email,
            recipients=[buyer_info['email']]
        )
        
        # 2. Tạo nội dung Email từ file HTML
        msg.html = render_template('email_ticket_template.html', 
                                   buyer=buyer_info, 
                                   tickets=tickets)
        
        # 3. Thực hiện gửi
        mail.send(msg)
        print(f"Đã gửi email thành công tới {buyer_info['email']}")
        return True
        
    except Exception as e:
        print(f"Lỗi hệ thống khi gửi mail: {e}")
        return False