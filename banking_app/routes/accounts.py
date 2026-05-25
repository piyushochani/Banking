"""
Account management routes
"""
from datetime import datetime
from flask import Blueprint, render_template, flash, redirect, url_for, request
from flask_login import login_required, current_user
from sqlalchemy import or_
from .. import db, limiter
from ..models import Account, Transaction, AccountStatus, AccountType
from decimal import Decimal
import random
import string
import uuid

accounts_bp = Blueprint('accounts', __name__)


def generate_account_number():
    while True:
        account_number = ''.join(random.choices(string.digits, k=10))
        if not Account.query.filter_by(account_number=account_number).first():
            return account_number


def generate_deposit_transaction_id():
    while True:
        tx_id = 'DEP-' + str(uuid.uuid4()).upper()[:8]
        if not Transaction.query.filter_by(transaction_id=tx_id).first():
            return tx_id


@accounts_bp.route('/')
@login_required
def list():
    accounts = Account.query.filter_by(
        user_id=current_user.id,
        status=AccountStatus.ACTIVE
    ).all()
    return render_template('accounts/list.html', accounts=accounts)


@accounts_bp.route('/<int:account_id>')
@login_required
def view(account_id):
    account = Account.query.get_or_404(account_id)
    if account.user_id != current_user.id and current_user.get_role() not in ['admin', 'staff']:
        flash('You do not have permission to view this account.', 'danger')
        return redirect(url_for('accounts.list'))

    transactions = Transaction.query.filter(
        or_(
            Transaction.from_account_id == account.id,
            Transaction.to_account_id == account.id
        )
    ).order_by(Transaction.timestamp.desc()).all()

    return render_template('accounts/view.html', account=account, transactions=transactions)


@accounts_bp.route('/create', methods=['GET', 'POST'])  # ✅ NO rate limit decorator
@login_required
def create():
    ALLOWED_ACCOUNT_TYPES = ['savings', 'current', 'fixed']

    if request.method == 'POST':
        account_type = request.form.get('account_type', '').strip().lower()
        raw_deposit  = request.form.get('initial_deposit', '0').strip() or '0'

        if account_type not in ALLOWED_ACCOUNT_TYPES:
            flash('Invalid account type selected.', 'danger')
            return redirect(url_for('accounts.create'))

        try:
            initial_deposit = Decimal(raw_deposit)
        except Exception:
            flash('Invalid deposit amount entered.', 'danger')
            return redirect(url_for('accounts.create'))

        if initial_deposit < 0:
            flash('Initial deposit cannot be negative.', 'danger')
            return redirect(url_for('accounts.create'))

        min_balance = Decimal('500') if account_type == 'savings' else Decimal('1000')
        if 0 < initial_deposit < min_balance:
            flash(f'Minimum initial deposit for {account_type} account is PKR {min_balance}.', 'danger')
            return redirect(url_for('accounts.create'))

        try:
            account = Account(
                account_number = generate_account_number(),
                account_type   = AccountType(account_type),
                balance        = initial_deposit,
                user_id        = current_user.id,
                status         = AccountStatus.ACTIVE
            )
            db.session.add(account)
            db.session.flush()

            if initial_deposit > 0:
                from ..models import TransactionType, TransactionStatus
                transaction = Transaction(
                    transaction_id   = generate_deposit_transaction_id(),
                    amount           = initial_deposit,
                    transaction_type = TransactionType.DEPOSIT,
                    status           = TransactionStatus.SUCCESS,
                    description      = 'Initial deposit on account creation',
                    to_account_id    = account.id,
                    timestamp        = datetime.utcnow(),
                    completed_at     = datetime.utcnow()
                )
                db.session.add(transaction)

            db.session.commit()
            flash(f'Account created! Your account number is: {account.account_number}', 'success')
            return redirect(url_for('accounts.view', account_id=account.id))

        except Exception as e:
            db.session.rollback()
            flash(f'Something went wrong: {str(e)}', 'danger')
            return redirect(url_for('accounts.create'))

    return render_template('accounts/create.html', allowed_types=ALLOWED_ACCOUNT_TYPES)