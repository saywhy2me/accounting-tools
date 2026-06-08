"""Bank statement reconciler.

Compares two sets of transactions (e.g. bank export vs internal ledger) and
produces a ReconciliationResult with matched pairs, unmatched entries, and
amount discrepancies.

Matching strategy (in order):
  1. Exact match  — same date, same amount, same type
  2. Fuzzy match  — same amount + type, date within tolerance window
  3. Description match — same amount + type, description similarity above threshold
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from enum import Enum
from typing import List, Optional, Tuple

from src.models.transaction import Transaction, TransactionType
from src.utils.currency import format_currency


class MatchStatus(Enum):
    EXACT = "exact"
    FUZZY_DATE = "fuzzy_date"
    DESCRIPTION = "description"
    UNMATCHED_SOURCE = "unmatched_source"
    UNMATCHED_LEDGER = "unmatched_ledger"
    AMOUNT_DISCREPANCY = "amount_discrepancy"


@dataclass
class MatchedPair:
    source: Transaction
    ledger: Transaction
    status: MatchStatus
    amount_diff: Decimal = Decimal("0.00")
    date_diff_days: int = 0

    @property
    def has_discrepancy(self) -> bool:
        return self.amount_diff != Decimal("0.00")


@dataclass
class ReconciliationResult:
    matched: List[MatchedPair] = field(default_factory=list)
    unmatched_source: List[Transaction] = field(default_factory=list)
    unmatched_ledger: List[Transaction] = field(default_factory=list)

    @property
    def source_total(self) -> Decimal:
        return sum(
            (p.source.signed_amount for p in self.matched),
            Decimal("0.00"),
        ) + sum((t.signed_amount for t in self.unmatched_source), Decimal("0.00"))

    @property
    def ledger_total(self) -> Decimal:
        return sum(
            (p.ledger.signed_amount for p in self.matched),
            Decimal("0.00"),
        ) + sum((t.signed_amount for t in self.unmatched_ledger), Decimal("0.00"))

    @property
    def balance_difference(self) -> Decimal:
        return self.source_total - self.ledger_total

    @property
    def is_balanced(self) -> bool:
        return self.balance_difference == Decimal("0.00")

    @property
    def discrepancies(self) -> List[MatchedPair]:
        return [p for p in self.matched if p.has_discrepancy]

    def summary(self) -> dict:
        return {
            "matched_exact": sum(1 for p in self.matched if p.status == MatchStatus.EXACT),
            "matched_fuzzy": sum(1 for p in self.matched if p.status in (MatchStatus.FUZZY_DATE, MatchStatus.DESCRIPTION)),
            "unmatched_source": len(self.unmatched_source),
            "unmatched_ledger": len(self.unmatched_ledger),
            "discrepancies": len(self.discrepancies),
            "source_total": float(self.source_total),
            "ledger_total": float(self.ledger_total),
            "balance_difference": float(self.balance_difference),
            "is_balanced": self.is_balanced,
        }

    def to_dict(self) -> dict:
        """Full JSON-serialisable view: summary plus unmatched and discrepancy detail."""
        return {
            "summary": self.summary(),
            "unmatched_source": [t.to_dict() for t in self.unmatched_source],
            "unmatched_ledger": [t.to_dict() for t in self.unmatched_ledger],
            "discrepancies": [
                {
                    "source": p.source.to_dict(),
                    "ledger": p.ledger.to_dict(),
                    "amount_diff": float(p.amount_diff),
                    "date_diff_days": p.date_diff_days,
                }
                for p in self.discrepancies
            ],
        }


def _description_similarity(a: str, b: str) -> float:
    """Simple token overlap ratio — no external deps needed."""
    tokens_a = set(a.lower().split())
    tokens_b = set(b.lower().split())
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    return len(intersection) / len(union)


def _try_exact(source: Transaction, candidates: List[Transaction]) -> Optional[int]:
    for i, t in enumerate(candidates):
        if (t.date == source.date
                and t.amount == source.amount
                and t.transaction_type == source.transaction_type):
            return i
    return None


def _try_fuzzy_date(source: Transaction, candidates: List[Transaction],
                    window_days: int) -> Optional[Tuple[int, int]]:
    best_idx, best_gap = None, window_days + 1
    for i, t in enumerate(candidates):
        if t.amount != source.amount or t.transaction_type != source.transaction_type:
            continue
        gap = abs((t.date - source.date).days)
        if gap <= window_days and gap < best_gap:
            best_idx, best_gap = i, gap
    return (best_idx, best_gap) if best_idx is not None else None


def _try_description(source: Transaction, candidates: List[Transaction],
                     threshold: float, date_window_days: int = 7) -> Optional[Tuple[int, float]]:
    best_idx, best_score = None, threshold - 0.01
    for i, t in enumerate(candidates):
        if t.transaction_type != source.transaction_type:
            continue
        if abs((t.date - source.date).days) > date_window_days:
            continue
        score = _description_similarity(source.description, t.description)
        if score > best_score:
            best_idx, best_score = i, score
    return (best_idx, best_score) if best_idx is not None else None


def reconcile(
    source: List[Transaction],
    ledger: List[Transaction],
    date_window_days: int = 3,
    description_threshold: float = 0.4,
) -> ReconciliationResult:
    """Reconcile two transaction lists.

    Args:
        source: Transactions from the bank/external source (ground truth).
        ledger: Transactions from the internal ledger/books.
        date_window_days: Days of tolerance for fuzzy date matching.
        description_threshold: Minimum Jaccard similarity for description matching.

    Returns:
        ReconciliationResult with all match details.
    """
    result = ReconciliationResult()
    remaining_ledger = list(ledger)

    for src_txn in source:
        # 1. Exact match
        idx = _try_exact(src_txn, remaining_ledger)
        if idx is not None:
            result.matched.append(MatchedPair(
                source=src_txn,
                ledger=remaining_ledger.pop(idx),
                status=MatchStatus.EXACT,
            ))
            continue

        # 2. Fuzzy date match
        fuzzy = _try_fuzzy_date(src_txn, remaining_ledger, date_window_days)
        if fuzzy is not None:
            idx, gap = fuzzy
            result.matched.append(MatchedPair(
                source=src_txn,
                ledger=remaining_ledger.pop(idx),
                status=MatchStatus.FUZZY_DATE,
                date_diff_days=gap,
            ))
            continue

        # 3. Description similarity match (wider date window, amount may differ)
        desc = _try_description(src_txn, remaining_ledger, description_threshold,
                                date_window_days=date_window_days * 2)
        if desc is not None:
            idx, _ = desc
            ledger_txn = remaining_ledger.pop(idx)
            result.matched.append(MatchedPair(
                source=src_txn,
                ledger=ledger_txn,
                status=MatchStatus.DESCRIPTION,
                amount_diff=src_txn.amount - ledger_txn.amount,
                date_diff_days=abs((src_txn.date - ledger_txn.date).days),
            ))
            continue

        result.unmatched_source.append(src_txn)

    result.unmatched_ledger.extend(remaining_ledger)
    return result


def format_reconciliation_report(result: ReconciliationResult) -> str:
    """Return a human-readable plain-text reconciliation report."""
    lines = []
    sep = "=" * 62

    lines.append(sep)
    lines.append("  BANK RECONCILIATION REPORT")
    lines.append(sep)

    s = result.summary()
    lines.append(f"  Matched (exact)  : {s['matched_exact']}")
    lines.append(f"  Matched (fuzzy)  : {s['matched_fuzzy']}")
    lines.append(f"  Unmatched source : {s['unmatched_source']}")
    lines.append(f"  Unmatched ledger : {s['unmatched_ledger']}")
    lines.append(f"  Discrepancies    : {s['discrepancies']}")
    lines.append(f"  Source total     : {format_currency(result.source_total)}")
    lines.append(f"  Ledger total     : {format_currency(result.ledger_total)}")
    lines.append(f"  Balance diff     : {format_currency(result.balance_difference)}")
    lines.append(f"  Status           : {'BALANCED' if result.is_balanced else 'OUT OF BALANCE'}")
    lines.append(sep)

    if result.unmatched_source:
        lines.append("\nUNMATCHED IN SOURCE (bank has, ledger missing):")
        for t in result.unmatched_source:
            lines.append(f"  {t.date}  {t.transaction_type.value:<6}  "
                         f"{format_currency(t.amount):<12}  {t.description[:40]}")

    if result.unmatched_ledger:
        lines.append("\nUNMATCHED IN LEDGER (ledger has, bank missing):")
        for t in result.unmatched_ledger:
            lines.append(f"  {t.date}  {t.transaction_type.value:<6}  "
                         f"{format_currency(t.amount):<12}  {t.description[:40]}")

    if result.discrepancies:
        lines.append("\nAMOUNT DISCREPANCIES:")
        for p in result.discrepancies:
            lines.append(f"  {p.source.date}  {p.source.description[:30]:<30}  "
                         f"src={format_currency(p.source.amount)}  "
                         f"led={format_currency(p.ledger.amount)}  "
                         f"diff={format_currency(p.amount_diff)}")

    lines.append(sep)
    return "\n".join(lines)
