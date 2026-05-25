"""
Banking System Database Models
All models in one file: User, Account, Transaction, Loan, AuditLog
"""
from datetime import datetime
import random
import string
from enum import Enum

from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import Index, event
from . import db, login_manager


# ===================================================================
# ENUMS — Used for role, status, type columns
# ===================================================================

class UserRole(str, Enum):
    ADMIN  = 'admin'
    STAFF  = 'staff'
    CLIENT = 'client'

class AccountType(str, Enum):
    SAVINGS = 'savings'
    CURRENT = 'current'
    FIXED   = 'fixed'

class AccountStatus(str, Enum):
    ACTIVE = 'active'
    FROZEN = 'frozen'
    CLOSED = 'closed'

class TransactionType(str, Enum):
    DEPOSIT    = 'deposit'
    WITHDRAWAL = 'withdrawal'
    TRANSFER   = 'transfer'

class TransactionStatus(str, Enum):
    SUCCESS = 'success'
    FAILED  = 'failed'
    PENDING = 'pending'

class LoanStatus(str, Enum):
    PENDING  = 'pending'
    APPROVED = 'approved'
    REJECTED = 'rejected'
    ACTIVE   = 'active'
    CLOSED   = 'closed'


# ===================================================================
# USER MODEL
# ===================================================================

class User(UserMixin, db.Model):
    """
    All system users: admin, staff, and client.
    UserMixin gives Flask-Login: is_authenticated, is_active, get_id()
    """
    __tablename__ = 'users'

    id            = db.Column(db.Integer, primary_key=True)
    full_name     = db.Column(db.String(100), nullable=False)
    email         = db.Column(db.String(120), unique=True, nullable=False, index=True)
    phone         = db.Column(db.String(20),  unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role          = db.Column(db.Enum(UserRole),  nullable=False, default=UserRole.CLIENT, index=True)
    is_active     = db.Column(db.Boolean, default=True, nullable=False)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    last_login    = db.Column(db.DateTime, nullable=True)

    # ---------------------------------------------------------------
    # Relationships
    # ---------------------------------------------------------------
    accounts = db.relationship(
        'Account', back_populates='user',
        lazy='dynamic', cascade='all, delete-orphan'
    )
    loans = db.relationship(
        'Loan', foreign_keys='Loan.user_id',
        back_populates='borrower', lazy='dynamic'
    )
    approved_loans = db.relationship(
        'Loan', foreign_keys='Loan.approved_by',
        back_populates='approver', lazy='dynamic'
    )
    audit_logs = db.relationship(
        'AuditLog', back_populates='user', lazy='dynamic'
    )

    # ---------------------------------------------------------------
    # Composite index
    # ---------------------------------------------------------------
    __table_args__ = (
        Index('idx_user_active_role', 'is_active', 'role'),
    )

    # ---------------------------------------------------------------
    # Password handling — never store plain text
    # ---------------------------------------------------------------
    @property
    def password(self):
        raise AttributeError('Password is not a readable attribute.')

    @password.setter
    def password(self, plain_text):
        """Automatically hash password when setting"""
        self.password_hash = generate_password_hash(plain_text)

    def verify_password(self, plain_text):
        """Compare plain text against stored hash — returns True/False"""
        return check_password_hash(self.password_hash, plain_text)

    # ---------------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------------
    def get_role(self):
        """Return role as plain string e.g. 'admin' """
        return self.role.value if hasattr(self.role, 'value') else str(self.role)

    def __repr__(self):
        return f'<User {self.id}: {self.full_name} | {self.get_role()}>'

    def to_dict(self):
        """Safe dict — no password_hash included"""
        return {
            'id':         self.id,
            'full_name':  self.full_name,
            'email':      self.email,
            'phone':      self.phone,
            'role':       self.get_role(),
            'is_active':  self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_login': self.last_login.isoformat() if self.last_login else None
        }


# ---------------------------------------------------------------
# Flask-Login: reload user object from session on every request
# ---------------------------------------------------------------
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ===================================================================
# ACCOUNT MODEL
# ===================================================================

class Account(db.Model):
    """Bank accounts — savings, current, or fixed. Linked to one client."""
    __tablename__ = 'accounts'

    id             = db.Column(db.Integer, primary_key=True)
    account_number = db.Column(db.String(10),  unique=True, nullable=False, index=True)
    account_type   = db.Column(db.Enum(AccountType),   nullable=False, default=AccountType.SAVINGS)
    balance        = db.Column(db.Numeric(15, 2), nullable=False, default=0.00)
    status         = db.Column(db.Enum(AccountStatus), nullable=False, default=AccountStatus.ACTIVE, index=True)
    interest_rate  = db.Column(db.Numeric(5, 2),  nullable=False, default=0.00)
    created_at     = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # Foreign Key
    user_id = db.Column(
        db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False, index=True
    )

    # Relationships
    user = db.relationship('User', back_populates='accounts')
    sent_transactions = db.relationship(
        'Transaction', foreign_keys='Transaction.from_account_id',
        back_populates='from_account', lazy='dynamic'
    )
    received_transactions = db.relationship(
        'Transaction', foreign_keys='Transaction.to_account_id',
        back_populates='to_account', lazy='dynamic'
    )

    __table_args__ = (
        Index('idx_account_user_status', 'user_id', 'status'),
    )

    @staticmethod
    def generate_account_number():
        """
        Generate a unique 10-digit account number.
        First digit is 1-9 (never starts with 0).
        Checks database to guarantee uniqueness.
        """
        while True:
            first_digit    = str(random.randint(1, 9))
            other_digits   = ''.join(random.choices(string.digits, k=9))
            account_number = first_digit + other_digits
            if not Account.query.filter_by(account_number=account_number).first():
                return account_number

    def is_operational(self):
        """Returns True only if account is active — use before any transaction"""
        return self.status == AccountStatus.ACTIVE

    def __repr__(self):
        return f'<Account {self.account_number} | {self.account_type.value} | Balance: {self.balance}>'

    def to_dict(self):
        return {
            'id':             self.id,
            'account_number': self.account_number,
            'account_type':   self.account_type.value,
            'balance':        float(self.balance),
            'status':         self.status.value,
            'interest_rate':  float(self.interest_rate),
            'created_at':     self.created_at.isoformat() if self.created_at else None,
            'user_id':        self.user_id
        }


@event.listens_for(Account, 'before_insert')
def auto_generate_account_number(mapper, connection, target):
    """Auto-generate account number if not manually set"""
    if not target.account_number:
        target.account_number = Account.generate_account_number()


# ===================================================================
# TRANSACTION MODEL
# ===================================================================

class Transaction(db.Model):
    """
    Every financial movement in the system.
    transaction_id is our human-readable reference e.g. TXN-A1B2C3D4
    """
    __tablename__ = 'transactions'

    id               = db.Column(db.Integer, primary_key=True)
    transaction_id   = db.Column(db.String(20),  unique=True, nullable=False, index=True)
    amount           = db.Column(db.Numeric(15, 2), nullable=False)
    transaction_type = db.Column(db.Enum(TransactionType),   nullable=False, index=True)
    status           = db.Column(db.Enum(TransactionStatus), nullable=False,
                                 default=TransactionStatus.PENDING, index=True)
    description      = db.Column(db.String(200), nullable=True)
    timestamp        = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    completed_at     = db.Column(db.DateTime, nullable=True)
    ip_address       = db.Column(db.String(45), nullable=True)   # IPv6 compatible

    # Foreign Keys
    from_account_id = db.Column(
        db.Integer, db.ForeignKey('accounts.id', ondelete='SET NULL'),
        nullable=True, index=True
    )
    to_account_id = db.Column(
        db.Integer, db.ForeignKey('accounts.id', ondelete='SET NULL'),
        nullable=True, index=True
    )

    # Relationships
    from_account = db.relationship(
        'Account', foreign_keys=[from_account_id],
        back_populates='sent_transactions'
    )
    to_account = db.relationship(
        'Account', foreign_keys=[to_account_id],
        back_populates='received_transactions'
    )

    __table_args__ = (
        Index('idx_transaction_accounts',    'from_account_id', 'to_account_id'),
        Index('idx_transaction_status_type', 'status', 'transaction_type'),
        Index('idx_transaction_timestamp',   'timestamp', 'status'),
    )

    def __repr__(self):
        return (f'<Transaction {self.transaction_id} | '
                f'{self.transaction_type.value} | {self.amount} | {self.status.value}>')

    def to_dict(self):
        return {
            'id':               self.id,
            'transaction_id':   self.transaction_id,
            'amount':           float(self.amount),
            'transaction_type': self.transaction_type.value,
            'status':           self.status.value,
            'description':      self.description,
            'timestamp':        self.timestamp.isoformat() if self.timestamp else None,
            'completed_at':     self.completed_at.isoformat() if self.completed_at else None,
            'ip_address':       self.ip_address,
            'from_account_id':  self.from_account_id,
            'to_account_id':    self.to_account_id
        }


# ===================================================================
# LOAN MODEL
# ===================================================================

class Loan(db.Model):
    """Loan applications, approvals, and EMI tracking"""
    __tablename__ = 'loans'

    id               = db.Column(db.Integer, primary_key=True)
    amount_requested = db.Column(db.Numeric(15, 2), nullable=False)
    amount_approved  = db.Column(db.Numeric(15, 2), nullable=True)
    interest_rate    = db.Column(db.Numeric(5, 2),  nullable=False, default=0.00)
    tenure_months    = db.Column(db.Integer, nullable=False)
    emi_amount       = db.Column(db.Numeric(15, 2), nullable=True)
    purpose          = db.Column(db.String(50),  nullable=True)
    description      = db.Column(db.String(500), nullable=True)
    status           = db.Column(db.Enum(LoanStatus), nullable=False,
                                 default=LoanStatus.PENDING, index=True)
    applied_at       = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    approved_at      = db.Column(db.DateTime, nullable=True)

    # Foreign Keys
    user_id = db.Column(
        db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False, index=True
    )
    approved_by = db.Column(
        db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'),
        nullable=True
    )

    # Relationships
    borrower = db.relationship('User', foreign_keys=[user_id],     back_populates='loans')
    approver = db.relationship('User', foreign_keys=[approved_by], back_populates='approved_loans')

    __table_args__ = (
        Index('idx_loan_user_status', 'user_id', 'status'),
        Index('idx_loan_approval',    'approved_by', 'approved_at'),
    )

    def calculate_emi(self):
        """
        EMI Formula: [P x R x (1+R)^N] / [(1+R)^N - 1]
        P = Principal amount approved
        R = Monthly interest rate  (annual_rate / 12 / 100)
        N = Tenure in months
        Returns rounded float or None if no approved amount yet.
        """
        if not self.amount_approved:
            return None
        P = float(self.amount_approved)
        R = float(self.interest_rate) / (12 * 100)
        N = self.tenure_months
        if R == 0:
            return round(P / N, 2)
        emi = (P * R * pow(1 + R, N)) / (pow(1 + R, N) - 1)
        return round(emi, 2)

    def __repr__(self):
        return (f'<Loan {self.id} | User {self.user_id} | '
                f'{self.amount_requested} | {self.status.value}>')

    def to_dict(self):
        return {
            'id':               self.id,
            'amount_requested': float(self.amount_requested),
            'amount_approved':  float(self.amount_approved) if self.amount_approved else None,
            'interest_rate':    float(self.interest_rate),
            'tenure_months':    self.tenure_months,
            'emi_amount':       float(self.emi_amount) if self.emi_amount else None,
            'status':           self.status.value,
            'applied_at':       self.applied_at.isoformat()  if self.applied_at  else None,
            'approved_at':      self.approved_at.isoformat() if self.approved_at else None,
            'user_id':          self.user_id,
            'approved_by':      self.approved_by
        }


@event.listens_for(Loan, 'before_update')
def auto_calculate_emi_on_approval(mapper, connection, target):
    """When a loan is approved, auto-calculate EMI and set approval timestamp"""
    if target.status == LoanStatus.APPROVED and not target.emi_amount:
        target.emi_amount  = target.calculate_emi()
        target.approved_at = target.approved_at or datetime.utcnow()


# ===================================================================
# AUDIT LOG MODEL
# ===================================================================

class AuditLog(db.Model):
    """
    Security trail — every login, logout, transaction, approval
    is recorded here with user ID, IP address, and timestamp.
    """
    __tablename__ = 'audit_logs'

    id         = db.Column(db.Integer, primary_key=True)
    action     = db.Column(db.String(100), nullable=False, index=True)
    ip_address = db.Column(db.String(45),  nullable=True)
    timestamp  = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    details    = db.Column(db.Text, nullable=True)   # Store as JSON string for flexibility

    # Foreign Key — nullable so logs survive even if user is deleted
    user_id = db.Column(
        db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'),
        nullable=True, index=True
    )

    # Relationship
    user = db.relationship('User', back_populates='audit_logs')

    __table_args__ = (
        Index('idx_audit_user_timestamp',   'user_id', 'timestamp'),
        Index('idx_audit_action_timestamp', 'action',  'timestamp'),
    )

    def __repr__(self):
        return f'<AuditLog {self.id} | {self.action} | User {self.user_id} | {self.timestamp}>'

    def to_dict(self):
        return {
            'id':         self.id,
            'action':     self.action,
            'ip_address': self.ip_address,
            'timestamp':  self.timestamp.isoformat() if self.timestamp else None,
            'details':    self.details,
            'user_id':    self.user_id
        }