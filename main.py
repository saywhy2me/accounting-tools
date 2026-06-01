"""Financial Automation CLI.

Usage:
  python main.py parse     <csv_file>                          - Parse and summarise transactions
  python main.py reconcile <source_csv> <ledger_csv>          - Reconcile two transaction files
  python main.py report    <transactions_csv> [--invoices/-i]  - Generate Excel report
  python main.py dupes     <csv_file>                          - Detect duplicate payments
"""

import sys
from datetime import date
from pathlib import Path

import click
from tabulate import tabulate

from src.parsers.csv_parser import parse_csv, parse_invoices_csv
from src.reconciler import reconcile, format_reconciliation_report
from src.reports.excel_report import generate_report
from src.models.transaction import Invoice, TransactionType
from src.utils.currency import format_currency
from src.utils.validators import validate_transactions
from src.utils.duplicate_detector import find_duplicates, format_duplicate_report


@click.group()
def cli():
    """Financial Automation — parse, reconcile, and report on your transactions."""


# ── parse ──────────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("csv_file", type=click.Path(exists=True))
@click.option("--date-col",   default="date",        show_default=True)
@click.option("--desc-col",   default="description", show_default=True)
@click.option("--amount-col", default="amount",      show_default=True)
@click.option("--type-col",   default="type",        show_default=True)
@click.option("--vendor-col", default=None)
@click.option("--ref-col",    default=None)
def parse(csv_file, date_col, desc_col, amount_col, type_col, vendor_col, ref_col):
    """Parse a transaction CSV and print a summary table."""
    click.echo(f"Parsing: {csv_file}")
    transactions = parse_csv(
        csv_file,
        date_col=date_col,
        desc_col=desc_col,
        amount_col=amount_col,
        type_col=type_col,
        vendor_col=vendor_col,
        ref_col=ref_col,
    )

    issues = validate_transactions(transactions)
    if issues:
        click.secho(f"\n{len(issues)} validation warning(s):", fg="yellow")
        for i in issues:
            click.echo(f"  {i}")

    total_credits = sum(t.amount for t in transactions if t.transaction_type == TransactionType.CREDIT)
    total_debits  = sum(t.amount for t in transactions if t.transaction_type == TransactionType.DEBIT)

    rows = [
        [str(t.date), t.transaction_type.value, t.category.value,
         t.description[:45], format_currency(t.amount)]
        for t in sorted(transactions, key=lambda t: t.date)
    ]

    click.echo()
    click.echo(tabulate(rows, headers=["Date", "Type", "Category", "Description", "Amount"],
                        tablefmt="simple"))
    click.echo()
    click.secho(f"  Total transactions : {len(transactions)}", bold=True)
    click.secho(f"  Total credits      : {format_currency(total_credits)}", fg="green")
    click.secho(f"  Total debits       : {format_currency(total_debits)}", fg="red")
    click.secho(f"  Net                : {format_currency(total_credits - total_debits)}",
                fg="green" if total_credits >= total_debits else "red", bold=True)


# ── reconcile ─────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("source_csv", type=click.Path(exists=True))
@click.argument("ledger_csv", type=click.Path(exists=True))
@click.option("--date-window", default=3, show_default=True,
              help="Days of tolerance for fuzzy date matching.")
@click.option("--desc-threshold", default=0.4, show_default=True,
              help="Minimum Jaccard similarity for description matching.")
@click.option("--output", "-o", default=None,
              help="Save plain-text report to this file path.")
def reconcile_cmd(source_csv, ledger_csv, date_window, desc_threshold, output):
    """Reconcile two transaction CSVs and report discrepancies."""
    click.echo(f"Source : {source_csv}")
    click.echo(f"Ledger : {ledger_csv}")

    source  = parse_csv(source_csv)
    ledger  = parse_csv(ledger_csv)
    result  = reconcile(source, ledger,
                        date_window_days=date_window,
                        description_threshold=desc_threshold)
    report  = format_reconciliation_report(result)

    click.echo()
    click.echo(report)

    if output:
        Path(output).write_text(report, encoding="utf-8")
        click.secho(f"\nReport saved to: {output}", fg="cyan")

    if not result.is_balanced:
        sys.exit(1)


# ── report ────────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("transactions_csv", type=click.Path(exists=True))
@click.option("--invoices", "-i", "invoices_csv", default=None,
              type=click.Path(exists=True),
              help="CSV of invoices for the AR Aging sheet.")
@click.option("--output", "-o", default="financial_report.xlsx", show_default=True,
              help="Output .xlsx file path.")
@click.option("--date", "report_date", default=None,
              help="Report as-of date (YYYY-MM-DD). Defaults to today.")
def report(transactions_csv, invoices_csv, output, report_date):
    """Generate a formatted Excel workbook from transaction (and optional invoice) data."""
    as_of = date.fromisoformat(report_date) if report_date else date.today()

    click.echo(f"Transactions : {transactions_csv}")
    if invoices_csv:
        click.echo(f"Invoices     : {invoices_csv}")
    click.echo(f"As-of date   : {as_of}")

    transactions = parse_csv(transactions_csv)
    invoices = None

    if invoices_csv:
        raw_invoices = parse_invoices_csv(invoices_csv)
        invoices = []
        for row in raw_invoices:
            try:
                from dateutil import parser as dp
                inv = Invoice(
                    invoice_number=row["invoice_number"],
                    issue_date=dp.parse(row["issue_date"]).date(),
                    due_date=dp.parse(row["due_date"]).date(),
                    vendor=row["vendor"],
                    line_items=[{"description": "Total", "amount": row["amount"]}],
                    paid=row.get("paid", "false").lower() in ("true", "yes", "1"),
                    payment_date=(dp.parse(row["payment_date"]).date()
                                  if row.get("payment_date") else None),
                )
                invoices.append(inv)
            except Exception as exc:
                click.secho(f"  Skipping invoice row: {exc}", fg="yellow")

    out_path = generate_report(transactions, invoices=invoices,
                               output_path=output, report_date=as_of)

    click.secho(f"\nReport generated: {out_path}", fg="green", bold=True)
    click.echo(f"  Transactions  : {len(transactions)}")
    if invoices:
        click.echo(f"  Invoices      : {len(invoices)}")
        outstanding = [inv for inv in invoices if not inv.paid]
        click.echo(f"  Outstanding   : {len(outstanding)}")


# ── dupes ─────────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("csv_file", type=click.Path(exists=True))
@click.option("--date-window", default=5, show_default=True,
              help="Days of tolerance for near-duplicate detection.")
@click.option("--threshold", default=0.6, show_default=True,
              help="Minimum description similarity (0-1) for near-duplicate matching.")
@click.option("--output", "-o", default=None,
              help="Save plain-text report to this file path.")
def dupes(csv_file, date_window, threshold, output):
    """Scan a transaction CSV for duplicate and near-duplicate payments."""
    click.echo(f"Scanning: {csv_file}")
    transactions = parse_csv(csv_file)
    pairs = find_duplicates(transactions,
                            date_window_days=date_window,
                            description_threshold=threshold)
    report = format_duplicate_report(pairs)

    click.echo()
    click.echo(report)

    if output:
        Path(output).write_text(report, encoding="utf-8")
        click.secho(f"\nReport saved to: {output}", fg="cyan")

    if pairs:
        click.secho(f"\n{len(pairs)} suspected duplicate(s) found — review before payment.", fg="yellow")
        sys.exit(1)
    else:
        click.secho("\nNo duplicates detected.", fg="green")


# entry point alias so `python main.py reconcile ...` works
cli.add_command(reconcile_cmd, name="reconcile")

if __name__ == "__main__":
    cli()
