"""
Models package initialization
Makes all models available from a single import
"""
from ..db import db
from .user import User
from .account import Account
from .transaction import Transaction
from .loan import Loan
from .audit_log import AuditLog

# Export all models
__all__ = ['db', 'User', 'Account', 'Transaction', 'Loan', 'AuditLog']