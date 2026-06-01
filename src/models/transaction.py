from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Optional
from enum import Enum


class TransactionType(Enum):
    DEBIT = "debit"
    CREDIT = "credit"


class Category(Enum):
    REVENUE = "revenue"
    EXPENSE = "expense"
    PAYROLL = "payroll"
    TAX = "tax"
    TRANSFER = "transfer"
    OTHER = "other"


@dataclass
class Transaction:
    date: date
    description: str
    amount: Decimal
    transaction_type: TransactionType
    category: Category = Category.OTHER
    reference: Optional[str] = None
    vendor: Optional[str] = None
    notes: Optional[str] = None

    @property
    def signed_amount(self) -> Decimal:
        return self.amount if self.transaction_type == TransactionType.CREDIT else -self.amount

    def to_dict(self) -> dict:
        return {
            "date": self.date.isoformat(),
            "description": self.description,
            "amount": float(self.amount),
            "type": self.transaction_type.value,
            "category": self.category.value,
            "reference": self.reference,
            "vendor": self.vendor,
            "notes": self.notes,
        }


@dataclass
class Invoice:
    invoice_number: str
    issue_date: date
    due_date: date
    vendor: str
    line_items: list = field(default_factory=list)
    tax_rate: Decimal = Decimal("0.00")
    paid: bool = False
    payment_date: Optional[date] = None

    @property
    def subtotal(self) -> Decimal:
        return sum(Decimal(str(item.get("amount", 0))) for item in self.line_items)

    @property
    def tax_amount(self) -> Decimal:
        return (self.subtotal * self.tax_rate / Decimal("100")).quantize(Decimal("0.01"))

    @property
    def total(self) -> Decimal:
        return self.subtotal + self.tax_amount

    @property
    def is_overdue(self) -> bool:
        return not self.paid and date.today() > self.due_date

    def to_dict(self) -> dict:
        return {
            "invoice_number": self.invoice_number,
            "issue_date": self.issue_date.isoformat(),
            "due_date": self.due_date.isoformat(),
            "vendor": self.vendor,
            "subtotal": float(self.subtotal),
            "tax_rate": float(self.tax_rate),
            "tax_amount": float(self.tax_amount),
            "total": float(self.total),
            "paid": self.paid,
            "payment_date": self.payment_date.isoformat() if self.payment_date else None,
            "is_overdue": self.is_overdue,
            "line_items": self.line_items,
        }
