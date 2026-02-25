from models import Customer

def generate_customer_number():
    """Generate unique customer number in format CUST-NNNN"""
    # Find the last customer number that matches the pattern CUST-%
    # We exclude the system-defined walk-in customer just in case, though its pattern is CUST-WALKIN
    last_customer = Customer.query.filter(
        Customer.customer_number.like('CUST-%'),
        Customer.customer_number != 'CUST-WALKIN'
    ).order_by(Customer.id.desc()).first()
    
    if last_customer:
        try:
            # Extract number part
            last_num_str = last_customer.customer_number.split('-')[-1]
            last_num = int(last_num_str)
            new_num = last_num + 1
        except ValueError:
            # Fallback if parsing fails
            new_num = 1
    else:
        new_num = 1
    
    return f'CUST-{new_num:04d}'
