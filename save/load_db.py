"""
Run from the project root (after clean.py):  python src/load_db.py
Output:                                      data/processed/hrrp.db
"""

from pathlib import Path
import sqlite3

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"

CSV_FILE = PROCESSED / "analysis_table.csv"
DB_FILE = PROCESSED / "hrrp.db"
TABLE = "analysis_table"

# Same numbers as clean.py and docs/data_audit.md.
EXPECTED_ROWS = 18_330
EXPECTED_HOSPITALS = 3_055
EXPECTED_USABLE_RATIOS = 11_720

# The schema is written out by hand instead of letting
# pandas.to_sql guess. to_sql picks column types from the data it sees, so a
# column that is empty in the first rows can end up with the wrong type, and it
# cannot add a primary key or CHECK rules. Writing the schema myself means the
# database enforces the rules too, not just my Python code.
# Each entry: (column name, SQLite type, extra constraints)
COLUMNS = [
    ("facility_id", "TEXT", "NOT NULL CHECK (length(facility_id) = 6)"),
    ("facility_name", "TEXT", "NOT NULL"),
    ("state", "TEXT", "NOT NULL"),
    ("measure_name", "TEXT", "NOT NULL"),
    ("measure", "TEXT", "NOT NULL"),
    ("excess_readmission_ratio", "REAL", ""),
    ("predicted_readmission_rate", "REAL", ""),
    ("expected_readmission_rate", "REAL", ""),
    ("number_of_discharges", "INTEGER", ""),
    ("number_of_readmissions", "INTEGER", ""),
    ("footnote", "TEXT", ""),
    ("has_ratio", "INTEGER", "NOT NULL CHECK (has_ratio IN (0, 1))"),
    ("missing_reason", "TEXT", ""),
    ("counts_suppressed", "INTEGER", "NOT NULL CHECK (counts_suppressed IN (0, 1))"),
    ("hospital_type", "TEXT", "NOT NULL"),
    ("hospital_ownership", "TEXT", "NOT NULL"),
    ("in_general_info", "INTEGER", "NOT NULL CHECK (in_general_info IN (0, 1))"),
    ("start_date", "TEXT", "NOT NULL"),
    ("end_date", "TEXT", "NOT NULL"),
]

COLUMN_NAMES = [c[0] for c in COLUMNS]
REAL_COLS = [c[0] for c in COLUMNS if c[1] == "REAL"]
INT_COUNT_COLS = ["number_of_discharges", "number_of_readmissions"]
BOOL_COLS = ["has_ratio", "counts_suppressed", "in_general_info"]
NULLABLE_TEXT_COLS = ["footnote", "missing_reason"]


def build_create_sql() -> str:
    col_defs = [f"    {name} {sql_type} {rules}".rstrip() for name, sql_type, rules in COLUMNS]

    # The primary key is (facility_id, measure_name) because
    # the audit says the grain is one row per hospital per measure. If a bad
    # load ever duplicated rows, SQLite would refuse it.
    col_defs.append("    PRIMARY KEY (facility_id, measure_name)")

    # has_ratio and the ratio must agree. This stops a row
    # that says "usable" but has no number, or the reverse.
    col_defs.append(
        "    CHECK ((has_ratio = 1 AND excess_readmission_ratio IS NOT NULL) "
        "OR (has_ratio = 0 AND excess_readmission_ratio IS NULL))"
    )
    return f"CREATE TABLE {TABLE} (\n" + ",\n".join(col_defs) + "\n)"


def check(condition: bool, message: str) -> None:
    """Fail loudly. Raised error instead of assert so it cannot be switched off."""
    if not condition:
        raise ValueError(f"CHECK FAILED: {message}")


def read_csv() -> pd.DataFrame:
    if not CSV_FILE.exists():
        raise FileNotFoundError(f"Run clean.py first. Missing: {CSV_FILE}")

    # Read everything as text, then convert column by column.
    # If I let pandas guess, facility_id "010001" becomes the number 10001 and
    # the leading zero is lost. keep_default_na=False means only an empty cell
    # becomes NULL, never a real string that merely looks like "NA".
    df = pd.read_csv(CSV_FILE, dtype=str, keep_default_na=False)

    check(list(df.columns) == COLUMN_NAMES,
          f"CSV columns do not match schema.\nCSV:    {list(df.columns)}\nSchema: {COLUMN_NAMES}")

    # Real numbers: empty cell -> NULL. errors="raise" so bad text stops the load.
    for col in REAL_COLS:
        df[col] = pd.to_numeric(df[col].mask(df[col] == ""), errors="raise")

    # Whole-number counts: nullable Int64 keeps NULLs without turning ints into floats.
    for col in INT_COUNT_COLS:
        df[col] = pd.to_numeric(df[col].mask(df[col] == ""), errors="raise").astype("Int64")

    # SQLite has no True/False type. The convention is 1 and 0,
    # which also lets SQL do SUM(has_ratio) to count usable rows.
    for col in BOOL_COLS:
        df[col] = df[col].map({"True": 1, "False": 0})
        check(df[col].notna().all(), f"{col} has values other than True/False")
        df[col] = df[col].astype(int)

    # Blank footnote means "no footnote", stored as NULL rather than "".
    for col in NULLABLE_TEXT_COLS:
        df[col] = df[col].mask(df[col] == "")

    # Dates stay as ISO text (YYYY-MM-DD). SQLite has no date type, but ISO text
    # sorts and compares correctly.
    return df


def load_table(df: pd.DataFrame) -> None:
    # Analyst Thinking: a local SQLite file is one portable file with no server
    # to install, so anyone can clone the repo, run two scripts, and get the
    # same database. Queries live in queries.sql and run against this file, so
    # every finding can be re-created from raw CSV with one command chain.
    # Rebuilding from scratch on every run (DROP + CREATE) makes the load
    # repeatable: no leftover rows from an older run.

    # Convert pandas NA/NaN to None so sqlite3 stores NULL; .tolist() gives
    # plain Python types that sqlite3 understands.
    rows = df.astype(object).where(df.notna(), None).values.tolist()

    placeholders = ", ".join("?" for _ in COLUMN_NAMES)
    insert_sql = f"INSERT INTO {TABLE} ({', '.join(COLUMN_NAMES)}) VALUES ({placeholders})"

    conn = sqlite3.connect(DB_FILE)
    try:
        # One transaction: either every row loads or none do.
        with conn:
            conn.execute(f"DROP TABLE IF EXISTS {TABLE}")
            conn.execute(build_create_sql())
            conn.executemany(insert_sql, rows)

            # Indexes speed up the columns I will filter and
            # group by most. They do not change results, only query speed.
            conn.execute(f"CREATE INDEX idx_measure ON {TABLE} (measure)")
            conn.execute(f"CREATE INDEX idx_ownership ON {TABLE} (hospital_ownership)")
            conn.execute(f"CREATE INDEX idx_state ON {TABLE} (state)")
    finally:
        conn.close()


def verify_load(csv_rows: int) -> None:
    """Query the database back and prove the load matches the CSV and the audit."""
    print("\nVerifying database ...")
    conn = sqlite3.connect(DB_FILE)
    try:
        # 1. Row counts: CSV vs database vs audit
        db_rows = conn.execute(f"SELECT COUNT(*) FROM {TABLE}").fetchone()[0]
        print(f"Row count: CSV = {csv_rows:,} | database = {db_rows:,} | audit = {EXPECTED_ROWS:,}")
        check(db_rows == csv_rows == EXPECTED_ROWS, "row counts do not match")

        # 2. Declared column types match the schema
        info = conn.execute(f"PRAGMA table_info({TABLE})").fetchall()  # (cid, name, type, ...)
        declared = {row[1]: row[2] for row in info}
        print("\nSchema (column: declared type)")
        for name, sql_type, _ in COLUMNS:
            print(f"  {name}: {declared[name]}")
            check(declared[name] == sql_type, f"{name} declared {declared[name]}, expected {sql_type}")

        # 3. Stored types match too.
        # Analyst Thinking: SQLite lets a column hold any type, so the declared
        # type alone proves nothing. typeof() shows what was actually stored.
        print("\nStored types (typeof per column)")
        for name, sql_type, _ in COLUMNS:
            found = {
                t for (t,) in conn.execute(f"SELECT DISTINCT typeof({name}) FROM {TABLE}")
            }
            allowed = {sql_type.lower(), "null"}
            print(f"  {name}: {sorted(found)}")
            check(found <= allowed, f"{name} stores {found}, expected only {allowed}")

        # 4. Leading zeros survived
        zero_ids = conn.execute(
            f"SELECT COUNT(DISTINCT facility_id) FROM {TABLE} WHERE facility_id LIKE '0%'"
        ).fetchone()[0]
        print(f"\nHospitals with a leading-zero facility_id: {zero_ids:,}")
        check(zero_ids > 0, "no facility_id starts with 0; leading zeros may have been lost")

        # 5. Key audit numbers, computed in SQL
        hospitals = conn.execute(f"SELECT COUNT(DISTINCT facility_id) FROM {TABLE}").fetchone()[0]
        usable = conn.execute(f"SELECT SUM(has_ratio) FROM {TABLE}").fetchone()[0]
        print(f"Distinct hospitals: {hospitals:,} (audit {EXPECTED_HOSPITALS:,})")
        print(f"Rows with a ratio:  {usable:,} (audit {EXPECTED_USABLE_RATIOS:,})")
        check(hospitals == EXPECTED_HOSPITALS, "hospital count does not match audit")
        check(usable == EXPECTED_USABLE_RATIOS, "usable ratio count does not match audit")

        # 6. Quick look at the data
        print("\nUsable ratios by measure")
        for measure, n, usable_n in conn.execute(
            f"SELECT measure, COUNT(*), SUM(has_ratio) FROM {TABLE} GROUP BY measure ORDER BY 3 DESC"
        ):
            print(f"  {measure:<10} rows = {n:,}  usable = {usable_n:,}")

        print("\nSample rows")
        for row in conn.execute(
            f"SELECT facility_id, state, measure, excess_readmission_ratio, missing_reason "
            f"FROM {TABLE} LIMIT 5"
        ):
            print(f"  {row}")

        print("\nAll database checks passed.")
    finally:
        conn.close()


def main():
    PROCESSED.mkdir(parents=True, exist_ok=True)

    df = read_csv()
    print(f"Read {len(df):,} rows from {CSV_FILE.name}")

    load_table(df)
    print(f"Loaded table '{TABLE}' into {DB_FILE}")

    verify_load(csv_rows=len(df))


if __name__ == "__main__":
    main()