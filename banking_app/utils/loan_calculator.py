"""
Loan calculation utilities for EMI and repayment schedule
"""
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import math

def calculate_emi(principal, annual_interest_rate, tenure_months):
    """
    Calculate EMI amount using the formula:
    EMI = P * r * (1+r)^n / ((1+r)^n - 1)
    
    Args:
        principal: Loan amount (P)
        annual_interest_rate: Annual interest rate in percentage
        tenure_months: Loan tenure in months (n)
    
    Returns:
        Decimal: EMI amount rounded to 2 decimal places
    """
    # Convert to Decimal for precise calculation
    P = Decimal(str(principal))
    annual_rate = Decimal(str(annual_interest_rate))
    
    # Monthly interest rate (r = annual_rate / 12 / 100)
    r = annual_rate / Decimal('1200')
    n = Decimal(str(tenure_months))
    
    # Handle zero interest rate case
    if r == 0:
        emi = P / n
    else:
        # Calculate (1+r)^n
        one_plus_r_n = (Decimal('1') + r) ** n
        
        # Apply EMI formula
        emi = (P * r * one_plus_r_n) / (one_plus_r_n - Decimal('1'))
    
    # Round to 2 decimal places
    return emi.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def generate_repayment_schedule(principal, annual_interest_rate, tenure_months, 
                               disbursement_date=None, emi_amount=None):
    """
    Generate month-by-month repayment schedule
    
    Args:
        principal: Loan amount
        annual_interest_rate: Annual interest rate in percentage
        tenure_months: Loan tenure in months
        disbursement_date: Date when loan was disbursed (defaults to current date)
        emi_amount: Pre-calculated EMI (if None, it will be calculated)
    
    Returns:
        list: List of dictionaries containing monthly repayment details
    """
    if disbursement_date is None:
        disbursement_date = datetime.utcnow().date()
    
    # Calculate EMI if not provided
    if emi_amount is None:
        emi_amount = calculate_emi(principal, annual_interest_rate, tenure_months)
    
    # Convert to Decimal for precise calculation
    P = Decimal(str(principal))
    annual_rate = Decimal(str(annual_interest_rate))
    r = annual_rate / Decimal('1200')  # Monthly interest rate
    emi = Decimal(str(emi_amount))
    
    schedule = []
    remaining_balance = P
    current_date = disbursement_date
    
    for month in range(1, tenure_months + 1):
        # Calculate interest for this month
        interest = (remaining_balance * r).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        
        # Calculate principal component of EMI
        principal_component = emi - interest
        
        # Handle last month adjustment for rounding errors
        if month == tenure_months:
            principal_component = remaining_balance
            emi = principal_component + interest
        
        # Update remaining balance
        remaining_balance -= principal_component
        
        # Ensure balance doesn't go negative due to rounding
        if remaining_balance < 0:
            remaining_balance = Decimal('0.00')
        
        # Calculate due date (monthly from disbursement)
        due_date = current_date + relativedelta(months=month)
        
        # Add to schedule
        schedule.append({
            'month': month,
            'due_date': due_date,
            'emi_amount': float(emi),
            'interest_component': float(interest),
            'principal_component': float(principal_component),
            'remaining_balance': float(remaining_balance),
            'status': 'pending'  # pending, paid, overdue
        })
        
        # Break if balance is zero
        if remaining_balance <= 0:
            break
    
    return schedule


def calculate_loan_summary(principal, annual_interest_rate, tenure_months):
    """
    Calculate loan summary including total interest and total payment
    
    Args:
        principal: Loan amount
        annual_interest_rate: Annual interest rate in percentage
        tenure_months: Loan tenure in months
    
    Returns:
        dict: Loan summary
    """
    emi = calculate_emi(principal, annual_interest_rate, tenure_months)
    total_payment = emi * tenure_months
    total_interest = total_payment - Decimal(str(principal))
    
    return {
        'principal': float(principal),
        'annual_interest_rate': float(annual_interest_rate),
        'tenure_months': tenure_months,
        'emi': float(emi),
        'total_interest': float(total_interest),
        'total_payment': float(total_payment),
        'interest_to_principal_ratio': float(total_interest / Decimal(str(principal)) * 100)
    }


def validate_loan_eligibility(user, requested_amount):
    """
    Validate if user is eligible for loan
    
    Args:
        user: User object
        requested_amount: Requested loan amount
    
    Returns:
        tuple: (is_eligible, reason)
    """
    # Check if user has any active account
    active_accounts = user.accounts.filter_by(status='active').count()
    if active_accounts == 0:
        return False, "You need at least one active account to apply for a loan"
    
    # Check for existing active/pending loans
    existing_loans = user.loan_applications.filter(
        Loan.status.in_(['pending', 'approved', 'active'])
    ).count()
    
    if existing_loans > 0:
        return False, "You have an existing loan application or active loan"
    
    # Basic amount validation (can be enhanced with credit score, etc.)
    if requested_amount > 1000000:  # ₹10 lakhs
        return False, "Requested amount exceeds maximum limit"
    
    return True, "Eligible for loan application"