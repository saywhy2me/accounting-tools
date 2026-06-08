import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import date
from decimal import Decimal

from src.models.transaction import Transaction, TransactionType
from src.utils.duplicate_detector import find_duplicates, duplicates_to_dict, DupeKind


def make_txn(d, desc, amount, ttype=TransactionType.DEBIT):
    return Transaction(
        date=date.fromisoformat(d),
        description=desc,
        amount=Decimal(str(amount)),
        transaction_type=ttype,
    )


def test_exact_duplicate_detected():
    t = make_txn("2026-05-01", "Vendor Payment", 500)
    result = find_duplicates([t, t])
    assert len(result) == 1
    assert result[0].kind == DupeKind.EXACT


def test_no_duplicate_different_amounts():
    a = make_txn("2026-05-01", "Vendor Payment", 500)
    b = make_txn("2026-05-01", "Vendor Payment", 600)
    assert find_duplicates([a, b]) == []


def test_no_duplicate_different_types():
    a = make_txn("2026-05-01", "Vendor Payment", 500, TransactionType.DEBIT)
    b = make_txn("2026-05-01", "Vendor Payment", 500, TransactionType.CREDIT)
    assert find_duplicates([a, b]) == []


def test_near_duplicate_similar_description():
    a = make_txn("2026-05-01", "Office Rent May 2026", 2500)
    b = make_txn("2026-05-02", "Office Rent May", 2500)  # slightly different description, 1 day apart
    result = find_duplicates([a, b], date_window_days=5, description_threshold=0.5)
    assert len(result) == 1
    assert result[0].kind == DupeKind.NEAR


def test_no_duplicate_outside_date_window():
    a = make_txn("2026-05-01", "Rent Payment", 1000)
    b = make_txn("2026-05-10", "Rent Payment", 1000)  # 9 days apart
    assert find_duplicates([a, b], date_window_days=5) == []


def test_no_duplicate_description_too_different():
    a = make_txn("2026-05-01", "Google Ads", 500)
    b = make_txn("2026-05-01", "Office Rent", 500)
    assert find_duplicates([a, b], description_threshold=0.6) == []


def test_multiple_duplicates_all_detected():
    a = make_txn("2026-05-01", "Payroll", 12000)
    b = make_txn("2026-05-01", "Payroll", 12000)
    c = make_txn("2026-05-02", "Payroll", 12000)
    result = find_duplicates([a, b, c], date_window_days=3, description_threshold=0.8)
    assert len(result) >= 1


def test_no_false_positive_clean_data():
    txns = [
        make_txn("2026-05-01", "Rent", 2500),
        make_txn("2026-05-02", "Payroll", 12000),
        make_txn("2026-05-05", "Software Sub", 150),
        make_txn("2026-05-10", "Revenue", 8000, TransactionType.CREDIT),
    ]
    assert find_duplicates(txns) == []


def test_amount_at_risk_calculated():
    a = make_txn("2026-05-01", "Duplicate Entry", 750)
    b = make_txn("2026-05-01", "Duplicate Entry", 750)
    result = find_duplicates([a, b])
    assert result[0].amount == Decimal("750")


def test_duplicates_to_dict_is_json_serialisable():
    import json

    a = make_txn("2026-05-01", "Vendor Payment", 500)
    b = make_txn("2026-05-01", "Vendor Payment", 500)
    payload = duplicates_to_dict(find_duplicates([a, b]))
    json.loads(json.dumps(payload))  # raises if any Decimal/date left unserialised

    assert payload["summary"]["exact"] == 1
    assert payload["summary"]["total"] == 1
    assert payload["summary"]["amount_at_risk"] == 500.0
    assert len(payload["duplicates"]) == 1
    assert payload["duplicates"][0]["kind"] == "exact"
    assert payload["duplicates"][0]["a"]["amount"] == 500.0


def test_duplicates_to_dict_empty_when_no_pairs():
    payload = duplicates_to_dict([])
    assert payload["summary"]["total"] == 0
    assert payload["summary"]["amount_at_risk"] == 0.0
    assert payload["duplicates"] == []


if __name__ == "__main__":
    tests = [
        test_exact_duplicate_detected,
        test_no_duplicate_different_amounts,
        test_no_duplicate_different_types,
        test_near_duplicate_similar_description,
        test_no_duplicate_outside_date_window,
        test_no_duplicate_description_too_different,
        test_multiple_duplicates_all_detected,
        test_no_false_positive_clean_data,
        test_amount_at_risk_calculated,
        test_duplicates_to_dict_is_json_serialisable,
        test_duplicates_to_dict_empty_when_no_pairs,
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
