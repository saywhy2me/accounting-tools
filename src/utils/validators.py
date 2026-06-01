from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import List

from src.models.transaction import Transaction, Invoice


def validate_transactions(transactions: List[Transaction]) -> List[str]:
    issues = []
    for i, t in enumerate(transactions):
        if t.amount <= Decimal("0"):
            issues.append(f"Transaction {i}: amount must be positive (got {t.amount})")
        if t.date > date.today():
            issues.append(f"Transaction {i}: future date {t.date}")
        if not t.description.strip():
            issues.append(f"Transaction {i}: empty description")
    return issues


def validate_invoice(invoice: Invoice) -> List[str]:
    issues = []
    if invoice.due_date < invoice.issue_date:
        issues.append(f"Invoice {invoice.invoice_number}: due_date before issue_date")
    if invoice.total <= Decimal("0"):
        issues.append(f"Invoice {invoice.invoice_number}: total must be positive")
    if not invoice.vendor.strip():
        issues.append(f"Invoice {invoice.invoice_number}: empty vendor name")
    if invoice.paid and not invoice.payment_date:
        issues.append(f"Invoice {invoice.invoice_number}: marked paid but no payment_date")
    return issues


def validate_file_path(path: str, extensions: List[str]) -> Path:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"File not found: {path}")
    if p.suffix.lower() not in extensions:
        raise ValueError(f"Unsupported file type '{p.suffix}'. Expected: {extensions}")
    return p
