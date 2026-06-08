# Accounting Tools — Financial Automation CLI

A command-line application for automating common accounting tasks: parsing transaction exports, reconciling bank statements, generating formatted Excel reports, and detecting duplicate payments. Built in Python with no proprietary dependencies — works with any CSV export from any bank or accounting system.

---

## Features

| Feature | Description |
|---|---|
| **CSV Parser** | Ingests bank/expense CSVs with tolerance for varying column names; auto-classifies transactions by category |
| **Bank Reconciler** | Matches two transaction sources with exact, fuzzy-date, and description-similarity matching; flags discrepancies |
| **Excel Report Generator** | Produces a formatted 3-sheet workbook: Financial Summary, Transaction Detail, AR Aging |
| **Duplicate Detector** | Scans for exact and near-duplicate payments using amount + description similarity + date proximity |

---

## Installation

**Requirements:** Python 3.11+

```bash
git clone https://github.com/saywhy2me/accounting-tools.git
cd accounting-tools
pip install -r requirements.txt
```

**Dependencies installed:**
- `pandas` — data handling
- `openpyxl` — Excel (.xlsx) generation
- `pdfplumber` — PDF parsing (future use)
- `reportlab` — PDF output (future use)
- `click` — CLI framework
- `python-dateutil` — flexible date parsing
- `tabulate` — terminal table formatting

---

## Recommended Workflow

The four commands are designed to be used in sequence at the end of each accounting period (weekly, monthly, etc.):

```
1. PARSE         — Load and validate your raw transaction export
        ↓
2. RECONCILE     — Compare your bank export against your internal ledger
        ↓
3. DUPES         — Scan for accidental duplicate payments before closing
        ↓
4. REPORT        — Generate the final Excel workbook for review/filing
```

---

## Usage

### 1. `parse` — Load and summarise transactions

Reads a CSV file and prints a summary table with totals by type.

```bash
python main.py parse <csv_file> [OPTIONS]
```

**Options:**

| Flag | Default | Description |
|---|---|---|
| `--date-col` | `date` | Column name for the transaction date |
| `--desc-col` | `description` | Column name for the description |
| `--amount-col` | `amount` | Column name for the amount |
| `--type-col` | `type` | Column name for credit/debit type |
| `--vendor-col` | _(none)_ | Column name for vendor |
| `--ref-col` | _(none)_ | Column name for reference number |

**Example:**
```bash
python main.py parse data/sample_transactions.csv
```

**Output:**
```
Date        Type    Category    Description                       Amount
----------  ------  ----------  --------------------------------  ----------
2026-05-01  debit   expense     Office Rent Payment               $2,500.00
2026-05-02  credit  revenue     Client Invoice Payment - ABC Corp $8,750.00
...

  Total transactions : 15
  Total credits      : $25,050.00
  Total debits       : $30,580.54
  Net                : -$5,530.54
```

**Auto-detected categories:**

| Category | Trigger keywords |
|---|---|
| `revenue` | invoice, payment received, sales, deposit |
| `payroll` | salary, payroll, wages, compensation |
| `tax` | tax, irs, hmrc, vat, gst |
| `expense` | supplies, rent, utilities, software, subscription |
| `transfer` | transfer, wire, ach, interbank |
| `other` | _(anything else)_ |

---

### 2. `reconcile` — Compare bank export vs internal ledger

Matches transactions from two sources and reports any gaps or discrepancies. Returns exit code `1` if out of balance — useful in scripts.

```bash
python main.py reconcile <source_csv> <ledger_csv> [OPTIONS]
```

**Options:**

| Flag | Default | Description |
|---|---|---|
| `--date-window` | `3` | Days of tolerance for fuzzy date matching |
| `--desc-threshold` | `0.4` | Minimum description similarity (0–1) for loose matching |
| `--output / -o` | _(none)_ | Save the report to a file |
| `--json` | _off_ | Emit a machine-readable JSON report (summary + unmatched + discrepancy detail) instead of plain text — pipe it into other tooling |

**Matching strategy (applied in order):**
1. **Exact** — same date, amount, and type
2. **Fuzzy date** — same amount and type, date within `--date-window` days
3. **Description similarity** — same type, Jaccard similarity above `--desc-threshold`, date within `2× window`

**Example:**
```bash
python main.py reconcile data/sample_transactions.csv data/sample_ledger.csv --output recon_may2026.txt
```

**Output:**
```
==============================================================
  BANK RECONCILIATION REPORT
==============================================================
  Matched (exact)  : 13
  Matched (fuzzy)  : 2
  Unmatched source : 0
  Unmatched ledger : 1
  Discrepancies    : 1
  Source total     : $55,630.54
  Ledger total     : $55,365.54
  Balance diff     : $265.00
  Status           : OUT OF BALANCE
==============================================================

UNMATCHED IN LEDGER (ledger has, bank missing):
  2026-05-30  credit  $35.00   Unrecorded Bank Fee

AMOUNT DISCREPANCIES:
  2026-05-15  Salary - Jane Smith   src=$4,500.00  led=$4,200.00  diff=$300.00
==============================================================
```

---

### 3. `dupes` — Detect duplicate payments

Scans a single transaction file for payments that may have been processed twice. Returns exit code `1` if any are found.

```bash
python main.py dupes <csv_file> [OPTIONS]
```

**Options:**

| Flag | Default | Description |
|---|---|---|
| `--date-window` | `5` | Days of tolerance between potential duplicates |
| `--threshold` | `0.6` | Minimum description similarity (Jaccard) for near-duplicate matching |
| `--output / -o` | _(none)_ | Save the plain-text report to a file |

**Detection types:**
- **Exact** — same date, amount, and description
- **Near** — same amount, similar description (above threshold), within date window

**Example:**
```bash
python main.py dupes data/sample_transactions.csv
```

**Output (when duplicates are found):**
```
==============================================================
  DUPLICATE PAYMENT REPORT
==============================================================
  Exact duplicates : 1
  Near duplicates  : 1
  Total suspected  : 2
==============================================================

EXACT DUPLICATES:
  [EXACT] 2026-05-06 vs 2026-05-06  $12,000.00  Payroll Week 1 / Payroll Week 1

NEAR DUPLICATES:
  [NEAR] 2026-05-15 vs 2026-05-16  $4,500.00  Salary - Jane / Salary Jane Smith  [sim=73%, gap=1d]

  Amount at risk : $16,500.00
==============================================================
```

---

### 4. `report` — Generate Excel workbook

Produces a formatted `.xlsx` file with up to 3 sheets. The file is ready for review, email, or archiving.

```bash
python main.py report <transactions_csv> [OPTIONS]
```

**Options:**

| Flag | Default | Description |
|---|---|---|
| `--invoices / -i` | _(none)_ | CSV of invoices to include the AR Aging sheet |
| `--output / -o` | `financial_report.xlsx` | Output file path |
| `--date` | today | Report as-of date (YYYY-MM-DD) |

**Example:**
```bash
python main.py report data/sample_transactions.csv \
  --invoices data/sample_invoices.csv \
  --output reports/may2026.xlsx \
  --date 2026-05-31
```

**Sheets generated:**

**Sheet 1 — Financial Summary**
- Credits, debits, and net by category
- Total row at the bottom
- Net values colour-coded green (positive) / red (negative)

**Sheet 2 — Transaction Detail**
- All transactions sorted by date
- Green rows = credits, orange rows = debits
- Frozen header row for easy scrolling

**Sheet 3 — AR Aging** _(only when `--invoices` is provided)_
- Unpaid invoices only
- Bucketed: Current / 1–30 / 31–60 / 61–90 / 90+ days
- Yellow highlight for overdue, red for 60+ days
- Bucket summary table below the detail

**Invoice CSV format:**
```csv
invoice_number,issue_date,due_date,vendor,amount,tax_rate,paid,payment_date
INV-001,2026-05-01,2026-06-01,Acme Corp,5000,8.5,false,
INV-002,2026-04-15,2026-05-15,Beta Ltd,2500,0,true,2026-05-14
```

---

## CSV Format Reference

The parser accepts any CSV with at minimum three columns: date, description, and amount. Column names are matched case-insensitively.

**Minimal format:**
```csv
date,description,amount
2026-05-01,Office Rent,2500.00
2026-05-02,Client Payment,8750.00
```

**Full format (with type, vendor, reference):**
```csv
date,description,amount,type,reference,vendor
2026-05-01,Office Rent,-2500.00,debit,REF-001,Prime Properties
2026-05-02,Invoice Payment,8750.00,credit,INV-045,ABC Corp
```

**Type detection rules:**
- If a `type` column exists: looks for `credit/cr/deposit/in` or `debit/dr/withdrawal/out`
- If no `type` column: negative amount → debit, positive → credit

---

## Project Structure

```
accounting-tools/
├── main.py                        # CLI entry point (parse, reconcile, report, dupes)
├── requirements.txt
├── src/
│   ├── models/
│   │   └── transaction.py         # Transaction and Invoice dataclasses
│   ├── parsers/
│   │   └── csv_parser.py          # Tolerant CSV ingestion with auto-category inference
│   ├── reconciler.py              # Bank reconciliation engine
│   ├── reports/
│   │   └── excel_report.py        # Excel workbook generator (openpyxl)
│   └── utils/
│       ├── currency.py            # Decimal-safe formatting and arithmetic
│       ├── duplicate_detector.py  # Exact and near-duplicate payment detection
│       └── validators.py          # Input validation at system boundaries
├── data/
│   ├── sample_transactions.csv    # 15-row bank export sample
│   ├── sample_ledger.csv          # 16-row ledger sample (with deliberate discrepancy)
│   └── sample_invoices.csv        # 6-row invoice sample (3 paid, 3 outstanding)
└── tests/
    ├── test_reconciler.py         # 9 tests
    ├── test_excel_report.py       # 7 tests
    ├── test_cli.py                # 9 tests
    └── test_duplicate_detector.py # 9 tests
```

---

## Running the Tests

```bash
python tests/test_reconciler.py
python tests/test_excel_report.py
python tests/test_cli.py
python tests/test_duplicate_detector.py
```

All 31 tests should pass with no dependencies beyond `requirements.txt`.

---

## Design Notes

- **`Decimal` throughout** — all financial arithmetic uses Python's `Decimal` type to avoid floating-point rounding errors
- **Tolerant parsing** — the CSV parser matches column names case-insensitively and skips unparseable rows with a warning rather than crashing
- **Exit codes** — `reconcile` and `dupes` return exit code `1` when problems are found, making them composable in shell scripts or CI pipelines
- **No cloud required** — everything runs locally; no API keys, no accounts needed
