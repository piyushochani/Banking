"""Admin routes — full system control"""
from datetime import datetime
from functools import wraps
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from sqlalchemy import or_
from .. import db
from ..models import (User, Account, Transaction, Loan,
                      UserRole, AccountStatus, AccountType,
                      LoanStatus, TransactionType, TransactionStatus)
from decimal import Decimal
import uuid, random, string

admin_bp = Blueprint('admin', __name__)

def admin_required(f):
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if current_user.get_role() != 'admin':
            flash('Admin access required.', 'danger')
            return redirect(url_for('main.dashboard'))
        return f(*args, **kwargs)
    return decorated

def gen_txn_id(prefix='TXN'):
    while True:
        t = f"{prefix}-{str(uuid.uuid4()).upper()[:8]}"
        if not Transaction.query.filter_by(transaction_id=t).first():
            return t

def gen_account_number():
    while True:
        n = str(random.randint(1,9)) + ''.join(random.choices(string.digits, k=9))
        if not Account.query.filter_by(account_number=n).first():
            return n

@admin_bp.route('/dashboard')
@admin_required
def dashboard():
    stats = {
        'total_users':        User.query.count(),
        'total_clients':      User.query.filter_by(role=UserRole.CLIENT).count(),
        'total_staff':        User.query.filter_by(role=UserRole.STAFF).count(),
        'total_accounts':     Account.query.count(),
        'active_accounts':    Account.query.filter_by(status=AccountStatus.ACTIVE).count(),
        'pending_loans':      Loan.query.filter_by(status=LoanStatus.PENDING).count(),
        'total_transactions': Transaction.query.count(),
    }
    recent_loans = Loan.query.order_by(Loan.applied_at.desc()).limit(6).all()
    recent_txns  = Transaction.query.order_by(Transaction.timestamp.desc()).limit(6).all()
    return render_template('admin/dashboard.html', stats=stats,
                           recent_loans=recent_loans, recent_txns=recent_txns)

@admin_bp.route('/users')
@admin_required
def users():
    role_filter = request.args.get('role', '').strip().lower()
    q = request.args.get('q', '').strip()
    query = User.query
    if role_filter in ['client', 'staff', 'admin']:
        query = query.filter_by(role=UserRole(role_filter))
    if q:
        query = query.filter(or_(User.full_name.ilike(f'%{q}%'),
                                 User.email.ilike(f'%{q}%'),
                                 User.phone.ilike(f'%{q}%')))
    all_users = query.order_by(User.created_at.desc()).all()
    return render_template('admin/users.html', users=all_users, role_filter=role_filter, q=q)

@admin_bp.route('/users/create', methods=['GET', 'POST'])
@admin_required
def create_user():
    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        email     = request.form.get('email', '').strip().lower()
        phone     = request.form.get('phone', '').strip()
        role      = request.form.get('role', 'client').strip().lower()
        password  = request.form.get('password', '')
        if not all([full_name, email, phone, password]):
            flash('All fields are required.', 'danger')
            return render_template('admin/create_user.html')
        if User.query.filter_by(email=email).first():
            flash('Email already registered.', 'danger')
            return render_template('admin/create_user.html')
        if role not in ['client', 'staff', 'admin']:
            flash('Invalid role.', 'danger')
            return render_template('admin/create_user.html')
        try:
            user = User(full_name=full_name, email=email, phone=phone, role=UserRole(role))
            user.password = password
            db.session.add(user)
            db.session.commit()
            flash(f'{role.title()} account created for {full_name}.', 'success')
            return redirect(url_for('admin.view_user', user_id=user.id))
        except Exception as e:
            db.session.rollback()
            flash(f'Error: {str(e)}', 'danger')
    return render_template('admin/create_user.html')

@admin_bp.route('/users/<int:user_id>')
@admin_required
def view_user(user_id):
    user     = User.query.get_or_404(user_id)
    accounts = Account.query.filter_by(user_id=user_id).all()
    loans    = Loan.query.filter_by(user_id=user_id).order_by(Loan.applied_at.desc()).all()
    return render_template('admin/view_user.html', user=user, accounts=accounts, loans=loans)

@admin_bp.route('/users/<int:user_id>/update', methods=['POST'])
@admin_required
def update_user(user_id):
    user = User.query.get_or_404(user_id)
    user.full_name = request.form.get('full_name', user.full_name).strip()
    user.phone     = request.form.get('phone', user.phone).strip()
    new_role       = request.form.get('role', '').strip().lower()
    if new_role in ['client', 'staff', 'admin']:
        user.role = UserRole(new_role)
    try:
        db.session.commit()
        flash('User updated.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Update failed: {str(e)}', 'danger')
    return redirect(url_for('admin.view_user', user_id=user_id))

@admin_bp.route('/users/<int:user_id>/toggle-freeze', methods=['POST'])
@admin_required
def toggle_freeze_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash('Cannot freeze your own account.', 'danger')
        return redirect(url_for('admin.view_user', user_id=user_id))
    user.is_active = not user.is_active
    db.session.commit()
    flash(f"Account {'activated' if user.is_active else 'frozen'}.", 'success')
    return redirect(url_for('admin.view_user', user_id=user_id))

@admin_bp.route('/users/<int:user_id>/delete', methods=['POST'])
@admin_required
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash('Cannot delete your own account.', 'danger')
        return redirect(url_for('admin.users'))
    try:
        db.session.delete(user)
        db.session.commit()
        flash(f'User {user.full_name} deleted.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Delete failed: {str(e)}', 'danger')
    return redirect(url_for('admin.users'))

@admin_bp.route('/accounts')
@admin_required
def accounts():
    q = request.args.get('q', '').strip()
    query = Account.query.join(User)
    if q:
        query = query.filter(or_(Account.account_number.ilike(f'%{q}%'),
                                 User.full_name.ilike(f'%{q}%'),
                                 User.email.ilike(f'%{q}%')))
    accs = query.order_by(Account.created_at.desc()).all()
    return render_template('admin/accounts.html', accounts=accs, q=q)

@admin_bp.route('/accounts/create', methods=['GET', 'POST'])
@admin_required
def create_account():
    if request.method == 'POST':
        email        = request.form.get('email', '').strip().lower()
        account_type = request.form.get('account_type', 'savings').strip().lower()
        deposit_str  = request.form.get('initial_deposit', '0').strip() or '0'
        user = User.query.filter_by(email=email).first()
        if not user:
            flash('No user found with that email.', 'danger')
            return render_template('admin/create_account.html')
        try:
            initial = Decimal(deposit_str)
        except:
            initial = Decimal('0')
        try:
            acc = Account(account_number=gen_account_number(),
                          account_type=AccountType(account_type),
                          balance=initial, user_id=user.id, status=AccountStatus.ACTIVE)
            db.session.add(acc)
            db.session.flush()
            if initial > 0:
                db.session.add(Transaction(
                    transaction_id=gen_txn_id('DEP'), amount=initial,
                    transaction_type=TransactionType.DEPOSIT,
                    status=TransactionStatus.SUCCESS,
                    description='Initial deposit by admin',
                    to_account_id=acc.id, timestamp=datetime.utcnow(),
                    completed_at=datetime.utcnow()))
            db.session.commit()
            flash(f'Account {acc.account_number} created for {user.full_name}.', 'success')
            return redirect(url_for('admin.view_account', account_id=acc.id))
        except Exception as e:
            db.session.rollback()
            flash(f'Error: {str(e)}', 'danger')
    return render_template('admin/create_account.html')

@admin_bp.route('/accounts/<int:account_id>')
@admin_required
def view_account(account_id):
    account = Account.query.get_or_404(account_id)
    page = request.args.get('page', 1, type=int)
    txns = Transaction.query.filter(
        or_(Transaction.from_account_id == account_id,
            Transaction.to_account_id   == account_id)
    ).order_by(Transaction.timestamp.desc()).paginate(page=page, per_page=20, error_out=False)
    return render_template('admin/view_account.html', account=account, txns=txns)

@admin_bp.route('/accounts/<int:account_id>/deposit', methods=['POST'])
@admin_required
def deposit(account_id):
    account = Account.query.get_or_404(account_id)
    if account.status != AccountStatus.ACTIVE:
        flash('Cannot deposit to a frozen/closed account.', 'danger')
        return redirect(url_for('admin.view_account', account_id=account_id))
    try:
        amount = Decimal(request.form.get('amount', '0').strip())
    except:
        flash('Invalid amount.', 'danger')
        return redirect(url_for('admin.view_account', account_id=account_id))
    if amount <= 0:
        flash('Amount must be positive.', 'danger')
        return redirect(url_for('admin.view_account', account_id=account_id))
    try:
        db.session.add(Transaction(
            transaction_id=gen_txn_id('DEP'), amount=amount,
            transaction_type=TransactionType.DEPOSIT,
            status=TransactionStatus.SUCCESS,
            description=request.form.get('description', 'Admin deposit').strip(),
            to_account_id=account.id, timestamp=datetime.utcnow(),
            completed_at=datetime.utcnow(), ip_address=request.remote_addr))
        account.balance += amount
        db.session.commit()
        flash(f'PKR {amount:,.2f} deposited to {account.account_number}.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Deposit failed: {str(e)}', 'danger')
    return redirect(url_for('admin.view_account', account_id=account_id))

@admin_bp.route('/accounts/<int:account_id>/toggle-freeze', methods=['POST'])
@admin_required
def toggle_freeze_account(account_id):
    acc = Account.query.get_or_404(account_id)
    acc.status = AccountStatus.FROZEN if acc.status == AccountStatus.ACTIVE else AccountStatus.ACTIVE
    db.session.commit()
    flash(f'Account is now {acc.status.value}.', 'success')
    return redirect(url_for('admin.view_account', account_id=account_id))

@admin_bp.route('/loans')
@admin_required
def loans():
    status_filter = request.args.get('status', '').strip()
    query = Loan.query
    if status_filter:
        try:
            query = query.filter_by(status=LoanStatus(status_filter))
        except:
            pass
    all_loans = query.order_by(Loan.applied_at.desc()).all()
    return render_template('admin/loans.html', loans=all_loans, status_filter=status_filter)

@admin_bp.route('/loans/<int:loan_id>/approve', methods=['GET', 'POST'])
@admin_required
def approve_loan(loan_id):
    loan = Loan.query.get_or_404(loan_id)
    if loan.status != LoanStatus.PENDING:
        flash('Only pending loans can be approved.', 'warning')
        return redirect(url_for('admin.loans'))
    if request.method == 'POST':
        try:
            approved_amount = Decimal(request.form.get('approved_amount', str(loan.amount_requested)))
            interest_rate   = Decimal(request.form.get('interest_rate', '12'))
            tenure_months   = int(request.form.get('tenure_months', str(loan.tenure_months)))
            loan.amount_approved = approved_amount
            loan.interest_rate   = interest_rate
            loan.tenure_months   = tenure_months
            loan.status          = LoanStatus.APPROVED
            loan.approved_by     = current_user.id
            loan.approved_at     = datetime.utcnow()
            P = float(approved_amount)
            R = float(interest_rate) / (12 * 100)
            N = tenure_months
            loan.emi_amount = round(P / N, 2) if R == 0 else round((P*R*(1+R)**N)/((1+R)**N-1), 2)
            db.session.commit()
            flash(f'Loan approved. EMI: PKR {loan.emi_amount:,.2f}/month.', 'success')
            return redirect(url_for('admin.loans'))
        except Exception as e:
            db.session.rollback()
            flash(f'Approval failed: {str(e)}', 'danger')
    return render_template('admin/approve_loan.html', loan=loan)

@admin_bp.route('/loans/<int:loan_id>/reject', methods=['POST'])
@admin_required
def reject_loan(loan_id):
    loan = Loan.query.get_or_404(loan_id)
    if loan.status != LoanStatus.PENDING:
        flash('Only pending loans can be rejected.', 'warning')
        return redirect(url_for('admin.loans'))
    reason = request.form.get('rejection_reason', '').strip()
    loan.status      = LoanStatus.REJECTED
    loan.approved_by = current_user.id
    if reason:
        loan.description = f"REJECTED: {reason}"
    db.session.commit()
    flash(f'Loan #{loan_id} rejected.', 'success')
    return redirect(url_for('admin.loans'))

@admin_bp.route('/transactions')
@admin_required
def transactions():
    page = request.args.get('page', 1, type=int)
    txns = Transaction.query.order_by(Transaction.timestamp.desc())\
        .paginate(page=page, per_page=25, error_out=False)
    return render_template('admin/transactions.html', txns=txns)