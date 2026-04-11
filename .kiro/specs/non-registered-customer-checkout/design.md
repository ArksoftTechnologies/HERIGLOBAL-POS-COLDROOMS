# Design Document

## Overview

This feature extends the existing POS checkout system to support non-registered customer names for faster checkout on non-credit sales. The design maintains the current architecture while adding minimal changes to support this workflow without breaking existing functionality.

## Architecture

The solution leverages the existing Sale model and POS checkout flow with the following key components:

### Frontend Changes
- Add a conditional input field in the POS checkout interface for non-registered customer names
- Implement client-side validation to prevent credit sales with non-registered customers
- Modify the checkout validation logic to accept either a registered customer or a non-registered customer name

### Backend Changes
- Extend the Sale model to include an optional `non_registered_customer_name` field
- Modify the POS checkout endpoint to handle non-registered customer transactions
- Update validation logic to ensure credit sales require registered customers
- Maintain existing customer relationship for registered customers

## Components and Interfaces

### Database Schema Changes

```sql
-- Add new column to sales table
ALTER TABLE sales ADD COLUMN non_registered_customer_name VARCHAR(200) NULL;

-- Add check constraint to ensure either customer_id or non_registered_customer_name is provided
ALTER TABLE sales ADD CONSTRAINT check_customer_or_name 
CHECK (
    (customer_id IS NOT NULL AND non_registered_customer_name IS NULL) OR
    (customer_id IS NULL AND non_registered_customer_name IS NOT NULL)
);
```

### Model Updates

**Sale Model Enhancement:**
- Add `non_registered_customer_name` field (nullable string, max 200 chars)
- Add validation to ensure either `customer_id` or `non_registered_customer_name` is provided
- Add property method to get customer display name (registered or non-registered)

### API Interface Changes

**POS Checkout Endpoint (`/pos/checkout`):**
- Accept new optional parameter: `non_registered_customer_name`
- Modify validation logic:
  - If `customer_id` is provided, use existing validation
  - If `non_registered_customer_name` is provided, validate it's non-credit payment
  - Ensure exactly one of the two is provided

### Frontend Interface Changes

**POS Checkout Template:**
- Add conditional input field for non-registered customer name
- Show input when no customer is selected
- Hide input when a registered customer is selected
- Add client-side validation for credit payment restrictions

**JavaScript Validation:**
- Prevent credit payment selection when only non-registered name is entered
- Ensure either registered customer or non-registered name is provided before checkout
- Clear non-registered name when registered customer is selected

## Data Models

### Updated Sale Model

```python
class Sale(db.Model):
    # ... existing fields ...
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=True)  # Made nullable
    non_registered_customer_name = db.Column(db.String(200), nullable=True)
    
    # Add validation constraint
    __table_args__ = (
        # ... existing constraints ...
        db.CheckConstraint(
            '(customer_id IS NOT NULL AND non_registered_customer_name IS NULL) OR '
            '(customer_id IS NULL AND non_registered_customer_name IS NOT NULL)',
            name='check_customer_or_name'
        ),
    )
    
    @property
    def customer_display_name(self):
        """Get display name for customer (registered or non-registered)"""
        if self.customer:
            return f"{self.customer.first_name} {self.customer.last_name}"
        return self.non_registered_customer_name or "Unknown Customer"
    
    @property
    def is_registered_customer(self):
        """Check if sale is for a registered customer"""
        return self.customer_id is not None
```

## Error Handling

### Validation Errors
- **Credit with non-registered customer**: "Credit sales require registered customers"
- **Missing customer information**: "Please select a customer or enter a customer name"
- **Invalid customer name**: "Customer name must be between 2 and 200 characters"

### Business Logic Validation
- Prevent credit payment modes when only non-registered customer name is provided
- Ensure non-registered customer names are properly sanitized and validated
- Maintain existing outlet scoping and access control logic

## Testing Strategy

### Unit Tests
- Test Sale model validation with various customer/name combinations
- Test POS checkout endpoint with registered and non-registered customers
- Test validation logic for credit payment restrictions

### Integration Tests
- Test complete POS checkout flow with non-registered customers
- Test that existing registered customer flow remains unchanged
- Test error handling for invalid combinations

### Frontend Tests
- Test UI behavior when switching between registered and non-registered customers
- Test validation messages and form state management
- Test that credit payment options are properly disabled/enabled

## Migration Strategy

### Database Migration
1. Add `non_registered_customer_name` column as nullable
2. Add check constraint to ensure data integrity
3. No data migration needed as existing records will have `customer_id` populated

### Deployment Considerations
- Backward compatible - existing functionality unchanged
- No breaking changes to existing API endpoints
- Frontend changes are additive and conditional

## Security Considerations

### Input Validation
- Sanitize non-registered customer names to prevent XSS
- Limit name length to prevent database issues
- Validate that names contain only appropriate characters

### Access Control
- Maintain existing role-based access control
- Ensure outlet scoping is preserved for non-registered customer sales
- No additional permissions required as this uses existing POS access

### Data Privacy
- Non-registered customer names are stored in sales records
- Consider data retention policies for non-registered customer information
- Ensure compliance with any applicable privacy regulations