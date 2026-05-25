"""
Loan management routes — client applications + staff/admin approvals
"""
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from functools import wraps
import json
import uuid

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from wtforms import SelectField, DecimalField, TextAreaField
from wtforms.validators import DataRequired, NumberRange, Length

from .. import db
from ..models import Account, Loan, Transaction, AuditLog, LoanStatus, AccountStatus, TransactionType, TransactionStatus

loans_bp = Blueprint('loans', __name__)

TENURE_CHOICES = [
    (6,  '6 Months'), (12, '12 Months'), (24, '24 Months'),
    (36, '36 Months'), (60, '60 Months'),
]
LOAN_PURPOSES = [
    ('home', 'Home Loan'), ('car', 'Car Loan'), ('education', 'Education Loan'),
    ('personal', 'Personal Loan'), ('business', 'Business Loan'),
]

class LoanApplicationForm(FlaskForm):
    amount = DecimalField('Loan Amount', validators=[
        DataRequired(), NumberRange(min=10000, max=1000000)
    ])
    tenure_months = SelectField('Tenure', choices=TENURE_CHOICES, coerce=int, validators=[DataRequired()])
    purpose = SelectField('Purpose', choices=LOAN_PURPOSES, validators=[DataRequired()])
    description = TextAreaField('Additional Details', validators=[Length(max=500)])

class LoanApprovalForm(FlaskForm):
    approved_amount = DecimalField('Approved Amount', validators=[
        DataRequired(), NumberRange(min=10000, max=1000000)
    ])
    interest_rate = DecimalField('Interest Rate (%)', validators=[
        DataRequired(), NumberRange(min=0.1, max=20.0)
    ])
    tenure_months = SelectField('Tenure', choices=TENURE_CHOICES, coerce=int, validators=[DataRequired()])

class LoanRejectionForm(FlaskForm):
    rejection_reason = TextAreaField('Rejection Reason', validators=[
        DataRequired(), Length(min=10, max=500)
    ])


def calculate_emi(principal, annual_rate, tenure_months):
    P = Decimal(str(principal))
    r = Decimal(str(annual_rate)) / Decimal('1200')
    n = tenure_months
    if r == 0:
        return (P / n).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    one_plus_r_n = (Decimal('1') + r) ** n
    emi = (P * r * one_plus_r_n) / (one_plus_r_n - Decimal('1'))
    return emi.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def generate_repayment_schedule(principal, annual_rate, tenure_months):
    emi = calculate_emi(principal, annual_rate, tenure_months)
    r = Decimal(str(annual_rate)) / Decimal('1200')
    balance = Decimal(str(principal))
    schedule = []
    for month in range(1, tenure_months + 1):
        interest = (balance * r).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        principal_part = emi - interest
        if month == tenure_months:
            principal_part = balance
            emi = principal_part + interest
        balance -= principal_part
        if balance < 0:
            balance = Decimal('0.00')
        schedule.append({
            'month': month, 'emi': float(emi),
            'principal': float(principal_part), 'interest': float(interest),
            'remaining_balance': float(balance),
        })
    return schedule


def generate_transaction_id():
    while True:
        tx_id = 'TXN-' + str(uuid.uuid4()).upper()[:8]
        if not Transaction.query.filter_by(transaction_id=tx_id).first():
            return tx_id


def staff_or_admin_required(f):
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if current_user.get_role() not in ['admin', 'staff']:
            flash('Access denied. Staff or Admin only.', 'danger')
            return redirect(url_for('main.dashboard'))
        return f(*args, **kwargs)
    return decorated_function


# ✅ NO @limiter.limit decorator
@loans_bp.route('/apply', methods=['GET', 'POST'])
@login_required
def apply_loan():
    if current_user.get_role() != 'client':
        flash('Only clients can apply for loans.', 'danger')
        return redirect(url_for('main.dashboard'))

    form = LoanApplicationForm()

    if form.validate_on_submit():
        # ✅ Fixed: use AccountStatus enum not string
        active_account = Account.query.filter_by(
            user_id=current_user.id, status=AccountStatus.ACTIVE
        ).first()
        if not active_account:
            flash('You need an active bank account to apply for a loan.', 'danger')
            return render_template('loans/apply.html', form=form)

        existing = Loan.query.filter(
            Loan.user_id == current_user.id,
            Loan.status.in_([LoanStatus.PENDING, LoanStatus.APPROVED, LoanStatus.ACTIVE])
        ).first()
        if existing:
            flash('You already have an active or pending loan application.', 'danger')
            return render_template('loans/apply.html', form=form)

        try:
            loan = Loan(
                amount_requested = form.amount.data,
                interest_rate    = Decimal('0.00'),
                tenure_months    = form.tenure_months.data,
                purpose          = form.purpose.data,
                description      = form.description.data,
                user_id          = current_user.id,
                status           = LoanStatus.PENDING
            )
            db.session.add(loan)
            audit = AuditLog(
                user_id=current_user.id, action='LOAN_APPLICATION',
                ip_address=request.remote_addr,
                details=json.dumps({
                    'amount': float(form.amount.data),
                    'tenure': form.tenure_months.data,
                    'purpose': form.purpose.data
                })
            )
            db.session.add(audit)
            db.session.commit()
            flash('Loan application submitted! Our team will review it shortly.', 'success')
            return redirect(url_for('loans.my_loans'))
        except Exception as e:
            db.session.rollback()
            flash(f'Something went wrong: {str(e)}', 'danger')

    return render_template('loans/apply.html', form=form)


@loans_bp.route('/my-loans')
@login_required
def my_loans():
    loans = Loan.query.filter_by(user_id=current_user.id)\
        .order_by(Loan.applied_at.desc()).all()
    return render_template('loans/my_loans.html', loans=loans)


@loans_bp.route('/<int:loan_id>/details')
@login_required
def loan_details(loan_id):
    loan = Loan.query.get_or_404(loan_id)
    if current_user.get_role() == 'client' and loan.user_id != current_user.id:
        flash('Access denied.', 'danger')
        return redirect(url_for('loans.my_loans'))

    schedule = summary = None
    if loan.status in [LoanStatus.APPROVED, LoanStatus.ACTIVE] and loan.amount_approved:
        schedule = generate_repayment_schedule(
            loan.amount_approved, loan.interest_rate, loan.tenure_months)
        emi = calculate_emi(loan.amount_approved, loan.interest_rate, loan.tenure_months)
        total_pay = float(emi) * loan.tenure_months
        summary = {
            'emi': float(emi),
            'total_payment': total_pay,
            'total_interest': total_pay - float(loan.amount_approved),
        }
    return render_template('loans/details.html', loan=loan, schedule=schedule, summary=summary)


@loans_bp.route('/pending')
@staff_or_admin_required
def pending_loans():
    loans = Loan.query.filter_by(status=LoanStatus.PENDING)\
        .order_by(Loan.applied_at.asc())\
        .paginate(page=request.args.get('page', 1, type=int), per_page=20, error_out=False)
    return render_template('loans/pending.html', loans=loans, now=datetime.utcnow())


@loans_bp.route('/<int:loan_id>/approve', methods=['GET', 'POST'])
@staff_or_admin_required
def approve_loan(loan_id):
    loan = Loan.query.get_or_404(loan_id)
    if loan.status != LoanStatus.PENDING:
        flash('This loan is no longer pending.', 'warning')
        return redirect(url_for('loans.pending_loans'))

    form = LoanApprovalForm()
    if request.method == 'GET':
        form.approved_amount.data = loan.amount_requested
        form.tenure_months.data   = loan.tenure_months

    if form.validate_on_submit():
        # ✅ Fixed: use AccountStatus enum
        active_account = Account.query.filter_by(
            user_id=loan.user_id, status=AccountStatus.ACTIVE
        ).first()
        if not active_account:
            flash('Borrower has no active account to receive funds.', 'danger')
            return redirect(url_for('loans.pending_loans'))

        try:
            loan.amount_approved = form.approved_amount.data
            loan.interest_rate   = form.interest_rate.data
            loan.tenure_months   = form.tenure_months.data
            loan.status          = LoanStatus.APPROVED
            loan.approved_by     = current_user.id
            loan.approved_at     = datetime.utcnow()
            loan.emi_amount      = calculate_emi(
                loan.amount_approved, loan.interest_rate, loan.tenure_months)

            txn = Transaction(
                transaction_id   = generate_transaction_id(),
                amount           = loan.amount_approved,
                transaction_type = TransactionType.DEPOSIT,
                status           = TransactionStatus.SUCCESS,
                description      = f'Loan disbursement — Loan #{loan.id}',
                to_account_id    = active_account.id,
                ip_address       = request.remote_addr,
                timestamp        = datetime.utcnow(),
                completed_at     = datetime.utcnow()
            )
            db.session.add(txn)
            active_account.balance += loan.amount_approved

            audit = AuditLog(
                user_id=current_user.id, action='LOAN_APPROVED',
                ip_address=request.remote_addr,
                details=json.dumps({
                    'loan_id': loan.id, 'amount': float(loan.amount_approved),
                    'rate': float(loan.interest_rate), 'tenure': loan.tenure_months,
                    'account': active_account.account_number
                })
            )
            db.session.add(audit)
            db.session.commit()
            flash(f'Loan #{loan.id} approved and funds disbursed!', 'success')
            return redirect(url_for('loans.pending_loans'))
        except Exception as e:
            db.session.rollback()
            flash(f'Approval failed: {str(e)}', 'danger')

    return render_template('loans/approve.html', form=form, loan=loan)


@loans_bp.route('/<int:loan_id>/reject', methods=['GET', 'POST'])
@staff_or_admin_required
def reject_loan(loan_id):
    loan = Loan.query.get_or_404(loan_id)
    if loan.status != LoanStatus.PENDING:
        flash('This loan is no longer pending.', 'warning')
        return redirect(url_for('loans.pending_loans'))

    form = LoanRejectionForm()
    if form.validate_on_submit():
        try:
            loan.status = LoanStatus.REJECTED
            audit = AuditLog(
                user_id=current_user.id, action='LOAN_REJECTED',
                ip_address=request.remote_addr,
                details=json.dumps({
                    'loan_id': loan.id,
                    'reason': form.rejection_reason.data,
                    'amount': float(loan.amount_requested)
                })
            )
            db.session.add(audit)
            db.session.commit()
            flash(f'Loan #{loan.id} rejected.', 'success')
            return redirect(url_for('loans.pending_loans'))
        except Exception as e:
            db.session.rollback()
            flash(f'Rejection failed: {str(e)}', 'danger')

    return render_template('loans/reject.html', form=form, loan=loan)


@loans_bp.route('/active-list')
@staff_or_admin_required
def active_loans():
    loans = Loan.query.filter_by(status=LoanStatus.ACTIVE)\
        .order_by(Loan.approved_at.desc())\
        .paginate(page=request.args.get('page', 1, type=int), per_page=20, error_out=False)
    return render_template('loans/active.html', loans=loans)