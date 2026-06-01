import csv
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import List, Optional
from dateutil import parser as date_parser

from src.models.transaction import Transaction, TransactionType, Category


# Keywords to auto-classify transactions
_CATEGORY_KEYWORDS = {
    Category.PAYROLL: ["salary", "payroll", "wages", "compensation"],
    Category.TAX: ["tax", "irs", "hmrc", "vat", "gst"],
    Category.REVENUE: ["invoice", "payment received", "sales", "revenue", "deposit"],
    Category.EXPENSE: ["supplies", "rent", "utilities", "software", "subscription", "office"],
    Category.TRANSFER: ["transfer", "wire", "ach", "interbank"],
}


def _infer_category(description: str) -> Category:
    desc_lower = description.lower()
    for category, keywords in _CATEGORY_KEYWORDS.items():
        if any(kw in desc_lower for kw in keywords):
            return category
    return Category.OTHER


def _parse_amount(raw: str) -> Decimal:
    cleaned = re.sub(r"[^\d.\-]", "", raw.strip())
    try:
        return Decimal(cleaned).copy_abs()
    except InvalidOperation:
        raise ValueError(f"Cannot parse amount: '{raw}'")


def _infer_type(raw_amount: str, type_col: Optional[str]) -> TransactionType:
    if type_col:
        t = type_col.strip().lower()
        if t in ("credit", "cr", "deposit", "in"):
            return TransactionType.CREDIT
        if t in ("debit", "dr", "withdrawal", "out"):
            return TransactionType.DEBIT
    # Negative value → debit
    cleaned = raw_amount.strip().replace(",", "")
    if cleaned.startswith("-"):
        return TransactionType.DEBIT
    return TransactionType.CREDIT


def parse_csv(filepath: str | Path, date_col: str = "date",
              desc_col: str = "description", amount_col: str = "amount",
              type_col: Optional[str] = None, ref_col: Optional[str] = None,
              vendor_col: Optional[str] = None) -> List[Transaction]:
    """Parse a bank statement or expense CSV into Transaction objects.

    The parser is tolerant of column name variations — it tries an exact match
    first, then a case-insensitive match, so callers don't need to pre-normalise
    their headers.
    """
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"CSV file not found: {filepath}")

    transactions: List[Transaction] = []
    errors: List[str] = []

    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        if not reader.fieldnames:
            raise ValueError("CSV file has no header row")

        # Build a case-insensitive column lookup
        col_map = {c.lower(): c for c in reader.fieldnames}

        def get_col(name: str) -> Optional[str]:
            return col_map.get(name.lower())

        resolved_date = get_col(date_col)
        resolved_desc = get_col(desc_col)
        resolved_amount = get_col(amount_col)
        resolved_type = get_col(type_col) if type_col else None
        resolved_ref = get_col(ref_col) if ref_col else None
        resolved_vendor = get_col(vendor_col) if vendor_col else None

        if not resolved_date or not resolved_desc or not resolved_amount:
            missing = [c for c, r in [(date_col, resolved_date), (desc_col, resolved_desc), (amount_col, resolved_amount)] if not r]
            raise ValueError(f"Required columns not found in CSV: {missing}. Available: {list(reader.fieldnames)}")

        for line_num, row in enumerate(reader, start=2):
            try:
                txn_date = date_parser.parse(row[resolved_date]).date()
                raw_amount = row[resolved_amount]
                amount = _parse_amount(raw_amount)
                txn_type = _infer_type(raw_amount, row.get(resolved_type) if resolved_type else None)
                description = row[resolved_desc].strip()
                reference = row[resolved_ref].strip() if resolved_ref and row.get(resolved_ref) else None
                vendor = row[resolved_vendor].strip() if resolved_vendor and row.get(resolved_vendor) else None
                category = _infer_category(description)

                transactions.append(Transaction(
                    date=txn_date,
                    description=description,
                    amount=amount,
                    transaction_type=txn_type,
                    category=category,
                    reference=reference,
                    vendor=vendor,
                ))
            except Exception as exc:
                errors.append(f"Line {line_num}: {exc}")

    if errors:
        print(f"[csv_parser] {len(errors)} row(s) skipped:")
        for e in errors:
            print(f"  {e}")

    return transactions


def parse_invoices_csv(filepath: str | Path) -> List[dict]:
    """Parse an invoice list CSV. Expected columns:
    invoice_number, issue_date, due_date, vendor, amount, tax_rate, paid, payment_date
    Returns raw dicts — callers build Invoice objects with full line-item detail.
    """
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"Invoice CSV not found: {filepath}")

    rows = []
    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            rows.append({k.strip().lower(): v.strip() for k, v in row.items()})
    return rows
