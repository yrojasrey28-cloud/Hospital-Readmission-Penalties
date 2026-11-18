"""
run_queries.py: run every query in sql/queries.sql against hrrp.db and print the tables.

Run from the project root:  python src/run_queries.py
Also saves each result to data/processed/query_results/ for charts and the write-up.
"""

from pathlib import Path
import re
import sqlite3

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DB_FILE = ROOT / "data" / "processed" / "hrrp.db"
SQL_FILE = ROOT / "sql" / "queries.sql"
RESULTS_DIR = ROOT / "data" / "processed" / "query_results"


def split_statements(sql_text: str):
    """Split the file into complete SQL statements.

    Analyst Thinking: sqlite3.complete_statement() knows where a statement
    really ends (a semicolon outside of comments and strings), so this is safer
    than sql_text.split(";").
    """
    statements, buffer = [], ""
    for line in sql_text.splitlines(keepends=True):
        buffer += line
        if sqlite3.complete_statement(buffer):
            statements.append(buffer.strip())
            buffer = ""
    return statements


def main():
    if not DB_FILE.exists():
        raise FileNotFoundError(f"Run load_db.py first. Missing: {DB_FILE}")
    if not SQL_FILE.exists():
        raise FileNotFoundError(f"Missing query file: {SQL_FILE}")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    pd.set_option("display.width", 220)
    pd.set_option("display.max_columns", None)
    pd.set_option("display.max_rows", None)

    statements = [s for s in split_statements(SQL_FILE.read_text()) if re.search(r"(?im)^\s*(SELECT|WITH)\b", s)]

    conn = sqlite3.connect(DB_FILE)
    try:
        for stmt in statements:
            # Title = the "-- Q1: ..." line in the comment above the statement.
            match = re.search(r"(?m)^-- (Q\d+):\s*(.*)$", stmt)
            label, title = (match.group(1), match.group(2)) if match else ("Q?", "query")

            df = pd.read_sql_query(stmt, conn)

            print("\n" + "=" * 100)
            print(f"{label}: {title}  ({len(df)} rows)")
            print("=" * 100)
            print(df.to_string(index=False))

            df.to_csv(RESULTS_DIR / f"{label.lower()}.csv", index=False)
    finally:
        conn.close()

    print(f"\nSaved results to {RESULTS_DIR}")


if __name__ == "__main__":
    main()