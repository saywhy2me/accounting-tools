import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import date
from decimal import Decimal

from src.models.transaction import Transaction, TransactionType, Category
from src.reconciler import reconcile, MatchStatus


def make_txn(d, desc, amount, ttype=TransactionType.DEBIT):
    return Transaction(
        date=date.fromisoformat(d),
        description=desc,
        amount=Decimal(str(amount)),
        transaction_type=ttype,
    )


def test_exact_match():
    src = [make_txn("2026-05-01", "Office Rent", 2500)]
    led = [make_txn("2026-05-01", "Office Rent", 2500)]
    result = reconcile(src, led)
    assert len(result.matched) == 1
    assert result.matched[0].status == MatchStatus.EXACT
    assert result.unmatched_source == []
    assert result.unmatched_ledger == []


def test_fuzzy_date_match():
    src = [make_txn("2026-05-01", "Rent", 2500)]
    led = [make_txn("2026-05-03", "Rent", 2500)]  # 2 days off
    result = reconcile(src, led, date_window_days=3)
    assert len(result.matched) == 1
    assert result.matched[0].status == MatchStatus.FUZZY_DATE
    assert result.matched[0].date_diff_days == 2


def test_no_match_outside_window():
    src = [make_txn("2026-05-01", "Rent", 2500)]
    led = [make_txn("2026-05-10", "Rent", 2500)]  # 9 days off
    result = reconcile(src, led, date_window_days=3)
    assert len(result.unmatched_source) == 1
    assert len(result.unmatched_ledger) == 1


def test_unmatched_source():
    src = [make_txn("2026-05-01", "Bank Fee", 35)]
    led = []
    result = reconcile(src, led)
    assert len(result.unmatched_source) == 1
    assert result.unmatched_source[0].description == "Bank Fee"


def test_unmatched_ledger():
    src = []
    led = [make_txn("2026-05-01", "Unknown Entry", 100)]
    result = reconcile(src, led)
    assert len(result.unmatched_ledger) == 1


def test_amount_discrepancy_via_description():
    src = [make_txn("2026-05-15", "Salary Smith", 4500)]
    led = [make_txn("2026-05-15", "Salary Smith", 4200)]
    result = reconcile(src, led, description_threshold=0.4)
    assert len(result.matched) == 1
    assert result.matched[0].amount_diff == Decimal("300")
    assert result.is_balanced is False


def test_balanced_reconciliation():
    src = [make_txn("2026-05-01", "Rent", 1000), make_txn("2026-05-02", "Revenue", 2000, TransactionType.CREDIT)]
    led = [make_txn("2026-05-01", "Rent", 1000), make_txn("2026-05-02", "Revenue", 2000, TransactionType.CREDIT)]
    result = reconcile(src, led)
    assert result.is_balanced
    assert len(result.matched) == 2


def test_summary_keys():
    src = [make_txn("2026-05-01", "Rent", 500)]
    led = [make_txn("2026-05-01", "Rent", 500)]
    result = reconcile(src, led)
    s = result.summary()
    assert "matched_exact" in s
    assert "is_balanced" in s


def test_to_dict_is_json_serialisable_with_detail():
    import json

    src = [make_txn("2026-05-15", "Salary Smith", 4500),
           make_txn("2026-05-20", "Bank Fee", 35)]
    led = [make_txn("2026-05-15", "Salary Smith", 4200)]  # discrepancy + unmatched src
    result = reconcile(src, led, description_threshold=0.4)

    payload = result.to_dict()
    # Round-trips through json without error (no Decimal/date left unserialised).
    json.loads(json.dumps(payload))

    assert payload["summary"]["is_balanced"] is False
    assert len(payload["unmatched_source"]) == 1
    assert payload["unmatched_source"][0]["description"] == "Bank Fee"
    assert len(payload["discrepancies"]) == 1
    assert payload["discrepancies"][0]["amount_diff"] == 300.0


if __name__ == "__main__":
    tests = [
        test_exact_match,
        test_fuzzy_date_match,
        test_no_match_outside_window,
        test_unmatched_source,
        test_unmatched_ledger,
        test_amount_discrepancy_via_description,
        test_balanced_reconciliation,
        test_summary_keys,
        test_to_dict_is_json_serialisable_with_detail,
    ]
    passed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
            passed += 1
        except Exception as e:
            print(f"  FAIL  {t.__name__}: {e}")
    print(f"\n{passed}/{len(tests)} tests passed")
