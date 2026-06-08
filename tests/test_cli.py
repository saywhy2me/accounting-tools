import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import json
import tempfile
from click.testing import CliRunner
from main import cli


DATA = Path(__file__).parent.parent / "data"
TRANSACTIONS = str(DATA / "sample_transactions.csv")
LEDGER       = str(DATA / "sample_ledger.csv")
INVOICES     = str(DATA / "sample_invoices.csv")

runner = CliRunner()


def test_parse_exits_ok():
    result = runner.invoke(cli, ["parse", TRANSACTIONS])
    assert result.exit_code == 0, result.output


def test_parse_shows_totals():
    result = runner.invoke(cli, ["parse", TRANSACTIONS])
    assert "Total credits" in result.output
    assert "Total debits"  in result.output
    assert "Net"           in result.output


def test_reconcile_detects_imbalance():
    result = runner.invoke(cli, ["reconcile", TRANSACTIONS, LEDGER])
    assert result.exit_code == 1            # out-of-balance → non-zero exit
    assert "OUT OF BALANCE" in result.output


def test_reconcile_reports_discrepancy():
    result = runner.invoke(cli, ["reconcile", TRANSACTIONS, LEDGER])
    assert "AMOUNT DISCREPANCIES" in result.output
    assert "Salary" in result.output


def test_reconcile_saves_output_file():
    with tempfile.TemporaryDirectory() as tmp:
        out = str(Path(tmp) / "recon.txt")
        runner.invoke(cli, ["reconcile", TRANSACTIONS, LEDGER, "--output", out])
        assert Path(out).exists()
        assert "BANK RECONCILIATION" in Path(out).read_text()


def test_reconcile_json_is_valid_and_structured():
    result = runner.invoke(cli, ["reconcile", TRANSACTIONS, LEDGER, "--json"])
    assert result.exit_code == 1            # still flags out-of-balance
    payload = json.loads(result.output)     # output is pure JSON, no preamble
    assert payload["summary"]["is_balanced"] is False
    assert "unmatched_source" in payload
    assert "unmatched_ledger" in payload
    assert isinstance(payload["discrepancies"], list)


def test_reconcile_json_output_file_is_parseable():
    with tempfile.TemporaryDirectory() as tmp:
        out = str(Path(tmp) / "recon.json")
        runner.invoke(cli, ["reconcile", TRANSACTIONS, LEDGER, "--json", "-o", out])
        assert Path(out).exists()
        json.loads(Path(out).read_text(encoding="utf-8"))  # raises if malformed


def test_report_creates_xlsx():
    with tempfile.TemporaryDirectory() as tmp:
        out = str(Path(tmp) / "report.xlsx")
        result = runner.invoke(cli, ["report", TRANSACTIONS, "-o", out, "--date", "2026-05-31"])
        assert result.exit_code == 0, result.output
        assert Path(out).exists()


def test_report_with_invoices():
    with tempfile.TemporaryDirectory() as tmp:
        out = str(Path(tmp) / "report.xlsx")
        result = runner.invoke(cli, [
            "report", TRANSACTIONS, "-i", INVOICES, "-o", out, "--date", "2026-05-31"
        ])
        assert result.exit_code == 0, result.output
        assert "Outstanding" in result.output


if __name__ == "__main__":
    tests = [
        test_parse_exits_ok,
        test_parse_shows_totals,
        test_reconcile_detects_imbalance,
        test_reconcile_reports_discrepancy,
        test_reconcile_saves_output_file,
        test_reconcile_json_is_valid_and_structured,
        test_reconcile_json_output_file_is_parseable,
        test_report_creates_xlsx,
        test_report_with_invoices,
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
