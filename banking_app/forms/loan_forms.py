"""
Loan application forms
"""
from flask_wtf import FlaskForm
from wtforms import SelectField, DecimalField, TextAreaField
from wtforms.validators import DataRequired, NumberRange, Length, ValidationError
from wtforms.widgets import NumberInput
from decimal import Decimal

# Loan purpose choices
LOAN_PURPOSES = [
    ('home', 'Home Loan'),
    ('car', 'Car Loan'),
    ('education', 'Education Loan'),
    ('personal', 'Personal Loan'),
    ('business', 'Business Loan')
]

# Tenure choices in months
TENURE_CHOICES = [
    (6, '6 Months'),
    (12, '12 Months'),
    (24, '24 Months'),
    (36, '36 Months'),
    (48, '48 Months'),
    (60, '60 Months')
]

class LoanApplicationForm(FlaskForm):
    """Form for applying for a loan"""
    amount = DecimalField(
        'Loan Amount (₹)',
        validators=[
            DataRequired(message='Please enter loan amount'),
            NumberRange(
                min=10000,
                max=1000000,
                message='Amount must be between ₹10,000 and ₹10,00,000'
            )
        ],
        widget=NumberInput(step='1000', min='10000', max='1000000'),
        render_kw={'placeholder': 'Enter loan amount (₹10,000 - ₹10,00,000)'}
    )
    
    tenure_months = SelectField(
        'Loan Tenure',
        choices=TENURE_CHOICES,
        validators=[DataRequired(message='Please select loan tenure')],
        coerce=int
    )
    
    purpose = SelectField(
        'Loan Purpose',
        choices=LOAN_PURPOSES,
        validators=[DataRequired(message='Please select loan purpose')]
    )
    
    description = TextAreaField(
        'Additional Details',
        validators=[Length(max=500, message='Description cannot exceed 500 characters')],
        render_kw={'placeholder': 'Provide any additional details about your loan requirement...', 'rows': 4}
    )
    
    def validate_amount(form, field):
        """Additional validation for amount"""
        if field.data < Decimal('10000'):
            raise ValidationError('Minimum loan amount is ₹10,000')
        if field.data > Decimal('1000000'):
            raise ValidationError('Maximum loan amount is ₹10,00,000')


class LoanApprovalForm(FlaskForm):
    """Form for approving a loan (staff/admin only)"""
    approved_amount = DecimalField(
        'Approved Amount (₹)',
        validators=[
            DataRequired(message='Please enter approved amount'),
            NumberRange(
                min=10000,
                max=1000000,
                message='Approved amount must be between ₹10,000 and ₹10,00,000'
            )
        ],
        widget=NumberInput(step='1000', min='10000', max='1000000'),
        render_kw={'placeholder': 'Enter approved amount'}
    )
    
    interest_rate = DecimalField(
        'Interest Rate (%)',
        validators=[
            DataRequired(message='Please enter interest rate'),
            NumberRange(
                min=0.1,
                max=20.0,
                message='Interest rate must be between 0.1% and 20%'
            )
        ],
        widget=NumberInput(step='0.1', min='0.1', max='20.0'),
        render_kw={'placeholder': 'Enter interest rate (e.g., 10.5)'}
    )
    
    tenure_months = SelectField(
        'Loan Tenure (Months)',
        choices=TENURE_CHOICES,
        validators=[DataRequired(message='Please select loan tenure')],
        coerce=int
    )
    
    def validate_approved_amount(form, field):
        """Validate approved amount"""
        if field.data <= 0:
            raise ValidationError('Approved amount must be greater than 0')


class LoanRejectionForm(FlaskForm):
    """Form for rejecting a loan with reason"""
    rejection_reason = TextAreaField(
        'Rejection Reason',
        validators=[
            DataRequired(message='Please provide a reason for rejection'),
            Length(min=10, max=500, message='Reason must be between 10 and 500 characters')
        ],
        render_kw={'placeholder': 'Provide detailed reason for rejection...', 'rows': 4}
    )