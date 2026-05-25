"""Main routes — role-based dashboard routing"""
from flask import Blueprint, render_template, redirect, url_for
from flask_login import login_required, current_user
from sqlalchemy import or_
from .. import db
from ..models import Transaction, Account, Loan, User, AccountStatus, LoanStatus, UserRole

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    return render_template('main/index.html')

@main_bp.route('/dashboard')
@login_required
def dashboard():
    role = current_user.get_role()
    if role == 'admin':
        return redirect(url_for('admin.dashboard'))
    elif role == 'staff':
        return redirect(url_for('staff.dashboard'))
    else:
        # CLIENT
        accounts = current_user.accounts.filter_by(status=AccountStatus.ACTIVE).all()
        account_ids = [a.id for a in accounts]
        recent_transactions = Transaction.query.filter(
            or_(Transaction.from_account_id.in_(account_ids),
                Transaction.to_account_id.in_(account_ids))
        ).order_by(Transaction.timestamp.desc()).limit(10).all() if account_ids else []
        loans = Loan.query.filter_by(user_id=current_user.id)\
            .order_by(Loan.applied_at.desc()).limit(3).all()
        return render_template('main/client_dashboard.html',
                               accounts=accounts,
                               recent_transactions=recent_transactions,
                               loans=loans)