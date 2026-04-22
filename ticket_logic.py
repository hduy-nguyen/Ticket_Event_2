
def calculate_ticket_price(num_tickets):
    base_price_per_ticket = 100
    total_price = num_tickets * base_price_per_ticket
    if num_tickets > 5:
        discount = total_price * 0.10
        total_price -= discount
    return total_price

num_tickets_to_buy = 10
final_price = calculate_ticket_price(num_tickets_to_buy)
print(f"Số vé đã mua: {num_tickets_to_buy}")
print(f"Tổng giá vé sau khi áp dụng giảm giá: {final_price}")
