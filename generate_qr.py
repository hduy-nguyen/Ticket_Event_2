#!/usr/bin/env python3
"""
Script để tạo QR Code cho các vé đã mua.
Script này cần được chạy thủ công sau khi có vé.
"""
import qrcode
from PIL import Image
import os
import mysql.connector
from mysql.connector import Error

# Cấu hình database
db_config = {
    'host': 'localhost',
    'user': 'root',
    'password': '123456',
    'database': 'ticket_system'
}

def generate_qr_for_all_tickets():
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor(dictionary=True)
        
        # Lấy tất cả các vé chưa có QR Code
        cursor.execute("""
            SELECT t.ticket_code, e.name as event_name, e.location, e.price
            FROM tickets t
            JOIN events e ON t.event_id = e.id
            WHERE t.ticket_code IS NOT NULL
        """)
        tickets = cursor.fetchall()
        
        # Tạo thư mục để lưu QR Code
        qr_folder = os.path.join(os.path.dirname(__file__), 'static', 'qrcodes')
        os.makedirs(qr_folder, exist_ok=True)
        
        for ticket in tickets:
            ticket_code = ticket['ticket_code']
            qr_data = f"Ticket Code: {ticket_code}\nEvent: {ticket['event_name']}\nLocation: {ticket['location']}\nPrice: {ticket['price']} VND"
            
            # Tạo QR Code
            qr = qrcode.QRCode(version=1, box_size=10, border=5)
            qr.add_data(qr_data)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            
            # Lưu QR Code
            qr_file_path = os.path.join(qr_folder, f'ticket_{ticket_code}.png')
            img.save(qr_file_path)
            print(f"Generated QR for ticket {ticket_code}")
            
    except Error as e:
        print(f"Error: {e}")
    finally:
        if 'conn' in locals() and conn.is_connected():
            cursor.close()
            conn.close()

if __name__ == "__main__":
    generate_qr_for_all_tickets()
    print("QR Code generation completed.")
