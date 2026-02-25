"""
PDF Generation Service for Heriglobal POS
Generates professional PDFs for receipts, reports, and documents using frontend rendering.
"""

from flask import render_template
from datetime import datetime

class PDFGenerator:
    """Prepare professional HTML templates for frontend PDF generation"""
    
    @staticmethod
    def generate_sale_receipt(sale, outlet):
        """Generate HTML receipt for a sale"""
        # Prepare data
        data = {
            'sale': sale,
            'outlet': outlet,
            'items': sale.items,
            'customer': sale.customer,
            'sales_rep': sale.sales_rep,
            'payment_mode': sale.payment_mode,
            'generated_at': datetime.now(),
            'company_name': current_app.config.get('APP_NAME', 'Heriglobal POS').upper(),
            'company_tagline': 'Your Trusted POS Solution'
        }
        
        # Render HTML template
        return render_template('pdf/sale_receipt.html', **data)
    
    @staticmethod
    def generate_repayment_receipt(repayment, customer, outlet):
        """Generate HTML receipt for a repayment"""
        data = {
            'repayment': repayment,
            'customer': customer,
            'outlet': outlet,
            'received_by': repayment.receiver,
            'generated_at': datetime.now(),
            'company_name': current_app.config.get('APP_NAME', 'Heriglobal POS').upper()
        }
        
        return render_template('pdf/repayment_receipt.html', **data)
    
    @staticmethod
    def generate_return_receipt(return_record, outlet):
        """Generate HTML receipt for a return"""
        data = {
            'return': return_record,
            'outlet': outlet,
            'items': return_record.items,
            'customer': return_record.customer,
            'processed_by': return_record.processed_by_user,
            'original_sale': return_record.sale,
            'generated_at': datetime.now(),
            'company_name': current_app.config.get('APP_NAME', 'Heriglobal POS').upper()
        }
        
        return render_template('pdf/return_receipt.html', **data)
    
    @staticmethod
    def generate_expense_record(expense, outlet):
        """Generate HTML for expense record"""
        data = {
            'expense': expense,
            'outlet': outlet,
            'recorded_by': expense.recorded_by_user,
            'category': expense.category,
            'generated_at': datetime.now(),
            'company_name': current_app.config.get('APP_NAME', 'Heriglobal POS').upper()
        }
        
        return render_template('pdf/expense_record.html', **data)
    
    @staticmethod
    def generate_collection_receipt(collection, outlet):
        """Generate HTML for cash collection"""
        data = {
            'collection': collection,
            'outlet': outlet,
            'sales_rep': collection.sales_rep,
            'generated_at': datetime.now(),
            'company_name': current_app.config.get('APP_NAME', 'Heriglobal POS').upper()
        }
        
        return render_template('pdf/collection_receipt.html', **data)
    
    @staticmethod
    def generate_remittance_receipt_pdf(remittance, outlet):
        """Generate HTML for remittance"""
        data = {
            'remittance': remittance,
            'outlet': outlet,
            'sales_rep': remittance.sales_rep,
            'generated_at': datetime.now(),
            'company_name': current_app.config.get('APP_NAME', 'Heriglobal POS').upper()
        }
        
        return render_template('pdf/remittance_record.html', **data)

    @staticmethod
    def generate_transfer_history_pdf(transfers, filters, generated_by):
        """Generate a beautifully formatted HTML for stock transfer history report."""
        data = {
            'transfers': transfers,
            'filters': filters,
            'generated_by': generated_by,
            'generated_at': datetime.now(),
            'company_name': current_app.config.get('APP_NAME', 'Heriglobal POS').upper(),
            'company_tagline': 'Stock Transfer History Report',
            'total_qty': sum(t.quantity for t in transfers),
            'total_count': len(transfers),
        }
        return render_template('pdf/transfer_history.html', **data)

