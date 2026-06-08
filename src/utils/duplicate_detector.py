"""Duplicate payment detector.

Flags transactions that are likely duplicates based on:
  - Exact match    : same amount, type, date, description
  - Near-duplicate : same amount + type, description similarity above threshold,
                     date within a rolling window
"""

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from enum import Enum
from typing import List, Tuple

from src.models.transaction import Transaction, TransactionType


class DupeKind(Enum):
    EXACT = "exact"
    NEAR = "near"


@dataclass
class DuplicatePair:
    a: Transaction
    b: Transaction
    kind: DupeKind
    similarity: float
    date_diff_days: int
    amount: Decimal

    def summary_line(self) -> str:
        return (
            f"[{self.kind.value.upper()}]  "
            f"{self.a.date} vs {self.b.date}  "
            f"${self.amount:,.2f}  "
            f"{self.a.description[:35]} / {self.b.description[:35]}"
        )

    def to_dict(self) -> dict:
        """JSON-serialisable view of the suspected duplicate pair."""
        return {
            "kind": self.kind.value,
            "similarity": round(self.similarity, 4),
            "date_diff_days": self.date_diff_days,
            "amount": float(self.amount),
            "a": self.a.to_dict(),
            "b": self.b.to_dict(),
        }


def _jaccard(a: str, b: str) -> float:
    ta, tb = set(a.lower().split()), set(b.lower().split())
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def find_duplicates(
    transactions: List[Transaction],
    date_window_days: int = 5,
    description_threshold: float = 0.6,
) -> List[DuplicatePair]:
    """Scan a transaction list and return all suspected duplicate pairs.

    Only compares debits to debits and credits to credits — a credit and a
    debit for the same amount are a transfer, not a duplicate.

    Args:
        transactions: Flat list of transactions (any order).
        date_window_days: Maximum date gap (in days) for near-duplicate detection.
        description_threshold: Minimum Jaccard similarity for near-duplicate matching.

    Returns:
        List of DuplicatePair, deduplicated (each pair reported once).
    """
    pairs: List[DuplicatePair] = []
    seen: set[Tuple[int, int]] = set()

    sorted_txns = sorted(transactions, key=lambda t: (t.date, t.amount))

    for i, a in enumerate(sorted_txns):
        for j, b in enumerate(sorted_txns):
            if j <= i:
                continue
            if (i, j) in seen:
                continue
            if a.transaction_type != b.transaction_type:
                continue
            if a.amount != b.amount:
                continue

            date_diff = abs((a.date - b.date).days)

            # Stop scanning once dates are too far apart (list is date-sorted)
            if date_diff > date_window_days:
                break

            sim = _jaccard(a.description, b.description)

            if date_diff == 0 and a.description == b.description:
                pairs.append(DuplicatePair(a, b, DupeKind.EXACT, 1.0, 0, a.amount))
                seen.add((i, j))
            elif sim >= description_threshold:
                pairs.append(DuplicatePair(a, b, DupeKind.NEAR, sim, date_diff, a.amount))
                seen.add((i, j))

    return pairs


def duplicates_to_dict(pairs: List[DuplicatePair]) -> dict:
    """Build a JSON-serialisable report: summary counts plus per-pair detail."""
    amount_at_risk = sum((p.amount for p in pairs), Decimal("0"))
    return {
        "summary": {
            "exact": sum(1 for p in pairs if p.kind == DupeKind.EXACT),
            "near": sum(1 for p in pairs if p.kind == DupeKind.NEAR),
            "total": len(pairs),
            "amount_at_risk": float(amount_at_risk),
        },
        "duplicates": [p.to_dict() for p in pairs],
    }


def format_duplicate_report(pairs: List[DuplicatePair]) -> str:
    if not pairs:
        return "No duplicate payments detected."

    lines = ["=" * 62, "  DUPLICATE PAYMENT REPORT", "=" * 62]
    exact = [p for p in pairs if p.kind == DupeKind.EXACT]
    near  = [p for p in pairs if p.kind == DupeKind.NEAR]

    lines.append(f"  Exact duplicates : {len(exact)}")
    lines.append(f"  Near duplicates  : {len(near)}")
    lines.append(f"  Total suspected  : {len(pairs)}")
    lines.append("=" * 62)

    if exact:
        lines.append("\nEXACT DUPLICATES (same date, amount, description):")
        for p in exact:
            lines.append(f"  {p.summary_line()}")

    if near:
        lines.append("\nNEAR DUPLICATES (same amount, similar description, close dates):")
        for p in near:
            lines.append(
                f"  {p.summary_line()}  "
                f"[sim={p.similarity:.0%}, gap={p.date_diff_days}d]"
            )

    total_at_risk = sum(p.amount for p in pairs)
    lines.append(f"\n  Amount at risk : ${total_at_risk:,.2f}")
    lines.append("=" * 62)
    return "\n".join(lines)
