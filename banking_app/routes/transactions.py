"""
Transaction routes for money transfers, deposits, withdrawals, and history.
"""
from datetime import datetime, date
from flask import Blueprint, render_template, flash, redirect, url_for, request, current_app
from flask_login import login_required, current_user
from sqlalchemy import or_, func
from .. import db
from ..models import Account, Transaction, AccountStatus, TransactionType, TransactionStatus
from decimal import Decimal
import uuid

transactions_bp = Blueprint('transactions', __name__)

DAILY_TRANSFER_LIMIT = Decimal('9999999.00')  # ✅ effectively unlimited


def generate_transaction_id(prefix='TXN'):
    while True:
        tx_id = f'{prefix}-' + str(uuid.uuid4()).upper()[:8]
        if not Transaction.query.filter_by(transaction_id=tx_id).first():
            return tx_id


def get_todays_transfer_total(account_id):
    today_start = datetime.combine(date.today(), datetime.min.time())
    result = db.session.query(func.sum(Transaction.amount)).filter(
        Transaction.from_account_id == account_id,
        Transaction.transaction_type == TransactionType.TRANSFER,
        Transaction.status == TransactionStatus.SUCCESS,
        Transaction.timestamp >= today_start
    ).scalar()
    return Decimal(result or 0)


# ✅ NO @limiter.limit decorator
@transactions_bp.route('/transfer', methods=['GET', 'POST'])
@login_required
def transfer():
    if request.method == 'POST':
        from_account_id   = request.form.get('from_account_id')
        to_account_number = request.form.get('to_account_number', '').strip()
        description       = request.form.get('description', '').strip()

        try:
            amount = Decimal(request.form.get('amount', '0').strip())
        except Exception:
            flash('Invalid amount entered.', 'danger')
            return redirect(url_for('transactions.transfer'))

        if amount <= 0:
            flash('Transfer amount must be greater than 0.', 'danger')
            return redirect(url_for('transactions.transfer'))

        from_account = Account.query.get(from_account_id)
        if not from_account or from_account.user_id != current_user.id:
            flash('Invalid source account.', 'danger')
            return redirect(url_for('transactions.transfer'))

        if from_account.status != AccountStatus.ACTIVE:
            flash('Your account is not active.', 'danger')
            return redirect(url_for('transactions.transfer'))

        to_account = Account.query.filter_by(account_number=to_account_number).first()
        if not to_account or to_account.status != AccountStatus.ACTIVE:
            flash('Destination account not found or inactive.', 'danger')
            return redirect(url_for('transactions.transfer'))

        if from_account.id == to_account.id:
            flash('Cannot transfer to the same account.', 'danger')
            return redirect(url_for('transactions.transfer'))

        if from_account.balance < amount:
            flash('Insufficient funds.', 'danger')
            return redirect(url_for('transactions.transfer'))

        try:
            txn = Transaction(
                transaction_id   = generate_transaction_id('TXN'),
                amount           = amount,
                transaction_type = TransactionType.TRANSFER,
                status           = TransactionStatus.PENDING,
                description      = description or 'Transfer',
                from_account_id  = from_account.id,
                to_account_id    = to_account.id,
                ip_address       = request.remote_addr,
                timestamp        = datetime.utcnow()
            )
            db.session.add(txn)
            from_account.balance -= amount
            to_account.balance   += amount
            txn.status            = TransactionStatus.SUCCESS
            txn.completed_at      = datetime.utcnow()
            db.session.commit()
            flash('Transfer completed successfully!', 'success')
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Transfer failed: {e}")
            flash('Transfer failed. Please try again.', 'danger')

        return redirect(url_for('transactions.history'))

    accounts = Account.query.filter_by(
        user_id=current_user.id, status=AccountStatus.ACTIVE
    ).all()
    return render_template('transactions/transfer.html', accounts=accounts,
                           daily_limit=DAILY_TRANSFER_LIMIT)


@transactions_bp.route('/deposit', methods=['GET', 'POST'])
@login_required
def deposit():
    if current_user.get_role() not in ['admin', 'staff']:
        flash('Access denied.', 'danger')
        return redirect(url_for('main.dashboard'))

    if request.method == 'POST':
        account_number = request.form.get('account_number', '').strip()
        description    = request.form.get('description', '').strip()
        try:
            amount = Decimal(request.form.get('amount', '0').strip())
        except Exception:
            flash('Invalid amount.', 'danger')
            return redirect(url_for('transactions.deposit'))

        if amount <= 0:
            flash('Amount must be greater than 0.', 'danger')
            return redirect(url_for('transactions.deposit'))

        account = Account.query.filter_by(account_number=account_number).first()
        if not account:
            flash('Account not found.', 'danger')
            return redirect(url_for('transactions.deposit'))

        try:
            txn = Transaction(
                transaction_id   = generate_transaction_id('DEP'),
                amount           = amount,
                transaction_type = TransactionType.DEPOSIT,
                status           = TransactionStatus.SUCCESS,
                description      = description or 'Cash deposit',
                to_account_id    = account.id,
                ip_address       = request.remote_addr,
                timestamp        = datetime.utcnow(),
                completed_at     = datetime.utcnow()
            )
            db.session.add(txn)
            account.balance += amount
            db.session.commit()
            flash(f'PKR {amount:,.2f} deposited to {account.account_number}.', 'success')
            return redirect(url_for('main.dashboard'))
        except Exception as e:
            db.session.rollback()
            flash(f'Deposit failed: {str(e)}', 'danger')

    return render_template('transactions/deposit.html')


@transactions_bp.route('/withdraw', methods=['GET', 'POST'])
@login_required
def withdraw():
    if current_user.get_role() not in ['admin', 'staff']:
        flash('Access denied.', 'danger')
        return redirect(url_for('main.dashboard'))

    if request.method == 'POST':
        account_id  = request.form.get('account_id')
        description = request.form.get('description', '').strip()
        try:
            amount = Decimal(request.form.get('amount', '0').strip())
        except Exception:
            flash('Invalid amount.', 'danger')
            return redirect(url_for('transactions.withdraw'))

        if amount <= 0:
            flash('Amount must be greater than 0.', 'danger')
            return redirect(url_for('transactions.withdraw'))

        account = Account.query.get(account_id)
        if not account:
            flash('Account not found.', 'danger')
            return redirect(url_for('transactions.withdraw'))

        if account.balance < amount:
            flash('Insufficient funds.', 'danger')
            return redirect(url_for('transactions.withdraw'))

        try:
            txn = Transaction(
                transaction_id   = generate_transaction_id('WDR'),
                amount           = amount,
                transaction_type = TransactionType.WITHDRAWAL,
                status           = TransactionStatus.SUCCESS,
                description      = description or 'Cash withdrawal',
                from_account_id  = account.id,
                ip_address       = request.remote_addr,
                timestamp        = datetime.utcnow(),
                completed_at     = datetime.utcnow()
            )
            db.session.add(txn)
            account.balance -= amount
            db.session.commit()
            flash(f'PKR {amount:,.2f} withdrawn from {account.account_number}.', 'success')
            return redirect(url_for('main.dashboard'))
        except Exception as e:
            db.session.rollback()
            flash(f'Withdrawal failed: {str(e)}', 'danger')

    accounts = Account.query.filter_by(status=AccountStatus.ACTIVE).all()
    return render_template('transactions/withdraw.html', accounts=accounts)


@transactions_bp.route('/history')
@login_required
def history():
    if current_user.get_role() in ['admin', 'staff']:
        transactions = Transaction.query.order_by(
            Transaction.timestamp.desc()
        ).paginate(page=request.args.get('page', 1, type=int), per_page=20, error_out=False)
    else:
        account_ids = [acc.id for acc in Account.query.filter_by(user_id=current_user.id).all()]
        transactions = Transaction.query.filter(
            or_(
                Transaction.from_account_id.in_(account_ids),
                Transaction.to_account_id.in_(account_ids)
            )
        ).order_by(Transaction.timestamp.desc()).paginate(
            page=request.args.get('page', 1, type=int), per_page=20, error_out=False
        )
    return render_template('transactions/history.html', transactions=transactions)


@transactions_bp.route('/<transaction_id>')
@login_required
def view_transaction(transaction_id):
    transaction = Transaction.query.filter_by(transaction_id=transaction_id).first_or_404()
    if current_user.get_role() not in ['admin', 'staff']:
        user_account_ids = [acc.id for acc in Account.query.filter_by(user_id=current_user.id).all()]
        if (transaction.from_account_id not in user_account_ids and
                transaction.to_account_id not in user_account_ids):
            flash('You do not have permission to view this transaction.', 'danger')
            return redirect(url_for('transactions.history'))
    return render_template('transactions/view.html', transaction=transaction)