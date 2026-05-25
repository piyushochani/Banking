"""Staff routes — client management panel"""
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

staff_bp = Blueprint('staff', __name__)

def staff_required(f):
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        role = current_user.get_role()
        if role not in ['staff', 'admin']:
            flash('Staff access required.', 'danger')
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

@staff_bp.route('/dashboard')
@staff_required
def dashboard():
    total_clients  = User.query.filter_by(role=UserRole.CLIENT).count()
    total_accounts = Account.query.count()
    pending_loans  = Loan.query.filter_by(status=LoanStatus.PENDING).count()
    recent_clients = User.query.filter_by(role=UserRole.CLIENT)\
        .order_by(User.created_at.desc()).limit(8).all()
    return render_template('staff/dashboard.html',
                           total_clients=total_clients,
                           total_accounts=total_accounts,
                           pending_loans=pending_loans,
                           recent_clients=recent_clients)

# ── CLIENT MANAGEMENT ─────────────────────────────────────────────────
@staff_bp.route('/clients')
@staff_required
def clients():
    q = request.args.get('q', '').strip()
    query = User.query.filter_by(role=UserRole.CLIENT)
    if q:
        query = query.filter(or_(User.full_name.ilike(f'%{q}%'),
                                 User.email.ilike(f'%{q}%'),
                                 User.phone.ilike(f'%{q}%')))
    all_clients = query.order_by(User.created_at.desc()).all()
    return render_template('staff/clients.html', clients=all_clients, q=q)

@staff_bp.route('/clients/create', methods=['GET', 'POST'])
@staff_required
def create_client():
    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        email     = request.form.get('email', '').strip().lower()
        phone     = request.form.get('phone', '').strip()
        password  = request.form.get('password', '')
        if not all([full_name, email, phone, password]):
            flash('All fields are required.', 'danger')
            return render_template('staff/create_client.html')
        if User.query.filter_by(email=email).first():
            flash('Email already registered.', 'danger')
            return render_template('staff/create_client.html')
        try:
            user = User(full_name=full_name, email=email, phone=phone, role=UserRole.CLIENT)
            user.password = password
            db.session.add(user)
            db.session.commit()
            flash(f'Client account created for {full_name}.', 'success')
            return redirect(url_for('staff.view_client', user_id=user.id))
        except Exception as e:
            db.session.rollback()
            flash(f'Error: {str(e)}', 'danger')
    return render_template('staff/create_client.html')

@staff_bp.route('/clients/<int:user_id>')
@staff_required
def view_client(user_id):
    user = User.query.filter_by(id=user_id, role=UserRole.CLIENT).first_or_404()
    accounts = Account.query.filter_by(user_id=user_id).all()
    loans    = Loan.query.filter_by(user_id=user_id).order_by(Loan.applied_at.desc()).all()
    return render_template('staff/view_client.html', user=user, accounts=accounts, loans=loans)

@staff_bp.route('/clients/<int:user_id>/update', methods=['POST'])
@staff_required
def update_client(user_id):
    user = User.query.filter_by(id=user_id, role=UserRole.CLIENT).first_or_404()
    user.full_name = request.form.get('full_name', user.full_name).strip()
    user.phone     = request.form.get('phone', user.phone).strip()
    try:
        db.session.commit()
        flash('Client updated.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Update failed: {str(e)}', 'danger')
    return redirect(url_for('staff.view_client', user_id=user_id))

@staff_bp.route('/clients/<int:user_id>/toggle-freeze', methods=['POST'])
@staff_required
def toggle_freeze_client(user_id):
    user = User.query.filter_by(id=user_id, role=UserRole.CLIENT).first_or_404()
    user.is_active = not user.is_active
    db.session.commit()
    flash(f"Client {'activated' if user.is_active else 'frozen'}.", 'success')
    return redirect(url_for('staff.view_client', user_id=user_id))

@staff_bp.route('/clients/<int:user_id>/delete', methods=['POST'])
@staff_required
def delete_client(user_id):
    user = User.query.filter_by(id=user_id, role=UserRole.CLIENT).first_or_404()
    try:
        db.session.delete(user)
        db.session.commit()
        flash(f'Client {user.full_name} deleted.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Delete failed: {str(e)}', 'danger')
    return redirect(url_for('staff.clients'))

# ── ACCOUNT MANAGEMENT ────────────────────────────────────────────────
@staff_bp.route('/accounts/create', methods=['GET', 'POST'])
@staff_required
def create_account():
    if request.method == 'POST':
        email        = request.form.get('email', '').strip().lower()
        account_type = request.form.get('account_type', 'savings').strip().lower()
        deposit_str  = request.form.get('initial_deposit', '0').strip() or '0'
        user = User.query.filter_by(email=email, role=UserRole.CLIENT).first()
        if not user:
            flash('No client found with that email.', 'danger')
            return render_template('staff/create_account.html')
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
                    description='Initial deposit by staff',
                    to_account_id=acc.id, timestamp=datetime.utcnow(),
                    completed_at=datetime.utcnow()))
            db.session.commit()
            flash(f'Account {acc.account_number} created for {user.full_name}.', 'success')
            return redirect(url_for('staff.view_account', account_id=acc.id))
        except Exception as e:
            db.session.rollback()
            flash(f'Error: {str(e)}', 'danger')
    return render_template('staff/create_account.html')

@staff_bp.route('/accounts/<int:account_id>')
@staff_required
def view_account(account_id):
    account = Account.query.get_or_404(account_id)
    page = request.args.get('page', 1, type=int)
    txns = Transaction.query.filter(
        or_(Transaction.from_account_id == account_id,
            Transaction.to_account_id   == account_id)
    ).order_by(Transaction.timestamp.desc()).paginate(page=page, per_page=20, error_out=False)
    return render_template('staff/view_account.html', account=account, txns=txns)

@staff_bp.route('/accounts/<int:account_id>/deposit', methods=['POST'])
@staff_required
def deposit(account_id):
    account = Account.query.get_or_404(account_id)
    if account.status != AccountStatus.ACTIVE:
        flash('Cannot deposit to a frozen/closed account.', 'danger')
        return redirect(url_for('staff.view_account', account_id=account_id))
    try:
        amount = Decimal(request.form.get('amount', '0').strip())
    except:
        flash('Invalid amount.', 'danger')
        return redirect(url_for('staff.view_account', account_id=account_id))
    if amount <= 0:
        flash('Amount must be positive.', 'danger')
        return redirect(url_for('staff.view_account', account_id=account_id))
    try:
        db.session.add(Transaction(
            transaction_id=gen_txn_id('DEP'), amount=amount,
            transaction_type=TransactionType.DEPOSIT,
            status=TransactionStatus.SUCCESS,
            description=request.form.get('description', 'Staff deposit').strip(),
            to_account_id=account.id, timestamp=datetime.utcnow(),
            completed_at=datetime.utcnow(), ip_address=request.remote_addr))
        account.balance += amount
        db.session.commit()
        flash(f'PKR {amount:,.2f} deposited to {account.account_number}.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Deposit failed: {str(e)}', 'danger')
    return redirect(url_for('staff.view_account', account_id=account_id))

@staff_bp.route('/accounts/<int:account_id>/toggle-freeze', methods=['POST'])
@staff_required
def toggle_freeze_account(account_id):
    acc = Account.query.get_or_404(account_id)
    acc.status = AccountStatus.FROZEN if acc.status == AccountStatus.ACTIVE else AccountStatus.ACTIVE
    db.session.commit()
    flash(f'Account is now {acc.status.value}.', 'success')
    return redirect(url_for('staff.view_account', account_id=account_id))