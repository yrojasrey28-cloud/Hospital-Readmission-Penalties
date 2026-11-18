"""
Run from the project root:  python src/clean.py
Output:                     data/processed/analysis_table.csv

All expected numbers below come from docs/data_audit.md.
"""

from pathlib import Path
import re

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"

READM_FILE = RAW / "FY_2026_Hospital_Readmissions_Reduction_Program_Hospital.csv"
GEN_FILE = RAW / "Hospital_General_Information.csv"
OUT_FILE = PROCESSED / "analysis_table.csv"

# The expected values are written down once, here, from the
# audit. If CMS re-releases the file and the numbers move, the script stops and
# I re-audit instead of quietly producing different results.
EXPECTED_ROWS = 18_330
EXPECTED_HOSPITALS = 3_055
EXPECTED_MEASURES = 6
EXPECTED_USABLE_RATIOS = 11_720
EXPECTED_MISSING_RATIOS = 6_610
EXPECTED_SUPPRESSED_COUNTS = 3_683
EXPECTED_UNMATCHED_HOSPITALS = 20
EXPECTED_UNMATCHED_ROWS = 120
EXPECTED_MISSING_REASONS = {          # footnote -> rows with no ratio (audit 3c)
    "too_few_cases": 3_150,           # footnote 1
    "not_available": 3_255,           # footnote 5
    "no_cases_met_criteria": 205,     # footnote 7
}
EXPECTED_START_DATE = "2021-07-01"
EXPECTED_END_DATE = "2024-06-30"
RATIO_TOLERANCE = 1e-4                # audit: max diff 6.5e-5 from 4-decimal storage

# Text values that mean "no number here" in the numeric columns.
MISSING_TOKENS = ["N/A", "Too Few to Report", ""]

# Footnote codes that explain a missing ratio (audit 3c).
FOOTNOTE_REASON = {
    "1": "too_few_cases",
    "5": "not_available",
    "7": "no_cases_met_criteria",
}

RATE_COLS = [
    "excess_readmission_ratio",
    "predicted_readmission_rate",
    "expected_readmission_rate",
]
COUNT_COLS = ["number_of_discharges", "number_of_readmissions"]

FINAL_COLUMNS = [
    "facility_id", "facility_name", "state",
    "measure_name", "measure",
    "excess_readmission_ratio", "predicted_readmission_rate",
    "expected_readmission_rate", "number_of_discharges", "number_of_readmissions",
    "footnote", "has_ratio", "missing_reason", "counts_suppressed",
    "hospital_type", "hospital_ownership", "in_general_info",
    "start_date", "end_date",
]


def to_snake_case(name: str) -> str:
    """Convert column names to snake_case so SQL and pandas queries stay clean."""
    name = name.strip().lower()
    name = re.sub(r"[^a-z0-9]+", "_", name)
    return name.strip("_")


def check(condition: bool, message: str) -> None:
    """Fail loudly when a rule is broken.

    Analyst Thinking: I raise an error instead of using `assert` because Python
    can switch asserts off (python -O). A data-quality rule must never be
    skippable.
    """
    if not condition:
        raise ValueError(f"VALIDATION FAILED: {message}")


def load_raw():
    # 1. Check that files exist
    if not READM_FILE.exists():
        raise FileNotFoundError(f"Could not find readmission file at: {READM_FILE}")
    if not GEN_FILE.exists():
        raise FileNotFoundError(f"Could not find general info file at: {GEN_FILE}")

    # 2. Read everything as text.
    # dtype=str keeps Facility IDs like "010001" with their
    # leading zero. keep_default_na=False stops pandas from silently turning
    # "N/A" into NaN, so I decide what each placeholder means myself.
    print("Loading raw data files ...")
    readm_df = pd.read_csv(READM_FILE, dtype=str, keep_default_na=False)
    gen_df = pd.read_csv(GEN_FILE, dtype=str, keep_default_na=False)

    # 3. snake_case the column names
    readm_df.columns = [to_snake_case(c) for c in readm_df.columns]
    gen_df.columns = [to_snake_case(c) for c in gen_df.columns]

    # 4. Print shapes to compare against the audit
    print(f"Readmission shape: {readm_df.shape} (expected rows: {EXPECTED_ROWS})")
    print(f"General Info shape: {gen_df.shape}")

    return readm_df, gen_df


def clean_readmission(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    required = (
        ["facility_id", "facility_name", "state", "measure_name", "footnote",
         "start_date", "end_date"]
        + RATE_COLS + COUNT_COLS
    )
    missing_cols = [c for c in required if c not in df.columns]
    if missing_cols:
        raise KeyError(f"Expected columns missing from readmissions file: {missing_cols}")

    # Trim stray whitespace so "HF " and "HF" never become two different values.
    for col in df.columns:
        df[col] = df[col].str.strip()

    # Facility ID is an identifier, not a number. zfill(6)
    # restores any leading zeros so the join to General Information matches.
    df["facility_id"] = df["facility_id"].str.zfill(6)

    # Short measure label (AMI, HF, PN ...) is easier to group by in SQL.
    df["measure"] = df["measure_name"].str.replace(
        r"^READM-30-|-HRRP$", "", regex=True
    )

    # Build this flag BEFORE the text becomes NULL.
    # After conversion, "Too Few to Report" and "N/A" both look like NaN and
    # the difference is lost forever. They mean different things (audit 3b).
    df["counts_suppressed"] = df["number_of_readmissions"] == "Too Few to Report"

    # Convert placeholders to real numbers.
    # Note: errors="raise" means a new, unexpected text value
    # (e.g. "Not Available") crashes the script. errors="coerce" would turn it
    # into NaN silently and I would never know. Missing stays NULL, never 0,
    # because 0 would claim "no excess readmissions".
    for col in RATE_COLS + COUNT_COLS:
        cleaned = df[col].mask(df[col].isin(MISSING_TOKENS))
        df[col] = pd.to_numeric(cleaned, errors="raise")

    # Counts are whole numbers; nullable Int64 keeps them as integers with NULLs.
    for col in COUNT_COLS:
        df[col] = df[col].astype("Int64")

    # has_ratio is the one flag that decides "usable row".
    # I keep rows without a ratio (excluding them is a visible filter later,
    # not a hidden deletion now).
    df["has_ratio"] = df["excess_readmission_ratio"].notna()

    # The footnote explains WHY a ratio is missing. Three
    # different causes should not be lumped together (audit finding 4).
    # Footnote 29 rows have a ratio, so they get no missing_reason.
    reason = df["footnote"].map(FOOTNOTE_REASON)
    df["missing_reason"] = reason.where(~df["has_ratio"])
    unexplained = ~df["has_ratio"] & df["missing_reason"].isna()
    df.loc[unexplained, "missing_reason"] = "unknown"

    # Real dates, so SQLite can sort and filter them. Format is MM/DD/YYYY.
    for col in ["start_date", "end_date"]:
        df[col] = pd.to_datetime(df[col], format="%m/%d/%Y", errors="raise")

    return df


def clean_general(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # General Information has many columns I do not need
    # (address, phone ...). Keep only what the questions use. facility_name and
    # state are NOT kept, because the readmissions file already has them and
    # duplicates would create confusing _x / _y columns after the merge.
    keep = ["facility_id", "hospital_type", "hospital_ownership"]
    missing_cols = [c for c in keep if c not in df.columns]
    if missing_cols:
        raise KeyError(f"Expected columns missing from General Info file: {missing_cols}")
    df = df[keep].copy()

    for col in keep:
        df[col] = df[col].str.strip()
    df["facility_id"] = df["facility_id"].str.zfill(6)

    for col in ["hospital_type", "hospital_ownership"]:
        df[col] = df[col].replace("", "Unknown")

    # The many-to-one join only works if Facility ID is unique
    # on this side. If it is not, the merge would duplicate readmission rows and
    # inflate every count. Check now, with a clear message.
    if df["facility_id"].duplicated().any():
        raise ValueError("Facility ID is not unique in General Information.")

    return df


def build_analysis_table(readm: pd.DataFrame, gen: pd.DataFrame) -> pd.DataFrame:
    # LEFT join with readmissions as the base. Readmissions is
    # the dataset I am analyzing; General Information only adds labels. An inner
    # join would drop the 20 unmatched hospitals (120 rows) silently, and an
    # outer join would add 2,384 hospitals that are not in the program.
    # validate="many_to_one" makes pandas error if the join is not 6-to-1.
    merged = readm.merge(
        gen,
        on="facility_id",
        how="left",
        validate="many_to_one",
        indicator=True,
    )

    # Flag the unmatched hospitals instead of removing them.
    merged["in_general_info"] = merged["_merge"] == "both"
    merged = merged.drop(columns="_merge")

    # Set "Unknown" only AFTER the flag exists. If I filled
    # first, I could no longer tell a real "Unknown" from a failed match.
    merged["hospital_type"] = merged["hospital_type"].fillna("Unknown")
    merged["hospital_ownership"] = merged["hospital_ownership"].fillna("Unknown")

    # A left join must never change the row count.
    if len(merged) != len(readm):
        raise ValueError(
            f"Join changed row count: {len(readm)} -> {len(merged)}"
        )

    return merged[FINAL_COLUMNS]


def validate(df: pd.DataFrame) -> None:
    """Re-check every audit finding that can be checked in code."""
    print("Validating against audit ...")

    # Finding 1: grain
    check(len(df) == EXPECTED_ROWS, f"rows {len(df)} != {EXPECTED_ROWS}")
    check(df["facility_id"].nunique() == EXPECTED_HOSPITALS,
          f"hospitals {df['facility_id'].nunique()} != {EXPECTED_HOSPITALS}")
    check(df["measure_name"].nunique() == EXPECTED_MEASURES, "measure count changed")
    check(not df.duplicated(["facility_id", "measure_name"]).any(),
          "duplicate (facility_id, measure_name) pairs found")
    check((df.groupby("facility_id").size() == EXPECTED_MEASURES).all(),
          "some hospitals do not have exactly 6 rows")
    check(df["facility_id"].str.len().eq(6).all(), "facility_id is not 6 characters")

    # Findings 2-3: missing ratios stay NULL, flag matches
    check(int(df["has_ratio"].sum()) == EXPECTED_USABLE_RATIOS, "usable ratio count changed")
    check(int((~df["has_ratio"]).sum()) == EXPECTED_MISSING_RATIOS, "missing ratio count changed")
    usable = df[df["has_ratio"]]
    check((usable["excess_readmission_ratio"] > 0).all(), "zero or negative ratio found")

    # Finding 4: every missing ratio has a known footnote reason
    reasons = df["missing_reason"].value_counts().to_dict()
    check("unknown" not in reasons, f"missing ratios with unexplained footnote: {reasons}")
    check(reasons == EXPECTED_MISSING_REASONS,
          f"missing_reason counts {reasons} != {EXPECTED_MISSING_REASONS}")

    # Finding 5: suppressed counts only on rows that have a ratio
    check(int(df["counts_suppressed"].sum()) == EXPECTED_SUPPRESSED_COUNTS,
          "suppressed count changed")
    check(df.loc[df["counts_suppressed"], "has_ratio"].all(),
          "suppressed counts found on rows without a ratio")

    # Finding 8: unmatched hospitals
    unmatched = df[~df["in_general_info"]]
    check(unmatched["facility_id"].nunique() == EXPECTED_UNMATCHED_HOSPITALS,
          "unmatched hospital count changed")
    check(len(unmatched) == EXPECTED_UNMATCHED_ROWS, "unmatched row count changed")
    check(df["hospital_ownership"].notna().all(), "null ownership remains")
    check((unmatched["hospital_ownership"] == "Unknown").all(),
          "unmatched hospitals should be 'Unknown'")

    # Finding 7: only acute care hospitals (among matched rows)
    matched_types = set(df.loc[df["in_general_info"], "hospital_type"].unique())
    check(matched_types == {"Acute Care Hospitals"},
          f"unexpected hospital types in program: {matched_types}")

    # Finding 10: ratio == predicted / expected
    diff = (
        usable["excess_readmission_ratio"]
        - usable["predicted_readmission_rate"] / usable["expected_readmission_rate"]
    ).abs().max()
    check(diff < RATIO_TOLERANCE, f"ratio != predicted/expected (max diff {diff:.2e})")

    # Measurement window
    check(df["start_date"].dt.strftime("%Y-%m-%d").eq(EXPECTED_START_DATE).all(),
          "start date changed")
    check(df["end_date"].dt.strftime("%Y-%m-%d").eq(EXPECTED_END_DATE).all(),
          "end date changed")

    print("All validation checks passed.")


def report_open_items(df: pd.DataFrame) -> None:
    """Print information for the TODOs in the audit. These never fail the run."""
    print("\n--- Open items from audit (information only) ---")

    fn7 = df[df["footnote"] == "7"]
    print("Footnote 7 discharge values:")
    print(fn7["number_of_discharges"].value_counts(dropna=False).head())

    same_rows = (
        df["excess_readmission_ratio"].isna().equals(df["predicted_readmission_rate"].isna())
        and df["excess_readmission_ratio"].isna().equals(df["expected_readmission_rate"].isna())
    )
    print(f"Ratio, predicted, expected missing on the same rows: {same_rows}")

    md = df[df["state"] == "MD"]
    print(f"Maryland rows: {len(md)} ({md['facility_id'].nunique()} hospitals), "
          f"with ratio: {int(md['has_ratio'].sum())}")


def main():
    PROCESSED.mkdir(parents=True, exist_ok=True)

    # 1. Load raw data
    readm_raw, gen_raw = load_raw()

    # 2. Clean each file on its own
    readm_clean = clean_readmission(readm_raw)
    gen_clean = clean_general(gen_raw)
    print(f"Cleaned readmission shape: {readm_clean.shape}")
    print(f"Cleaned general info shape: {gen_clean.shape}")

    # 3. Merge into one analysis table
    analysis = build_analysis_table(readm_clean, gen_clean)

    # 4. Validate BEFORE saving.
    # A file that fails validation is never written, so a
    # bad table cannot reach the database or the findings.
    validate(analysis)
    report_open_items(analysis)

    # 5. Save
    analysis.to_csv(OUT_FILE, index=False)
    print(f"\nSaved {len(analysis):,} rows x {analysis.shape[1]} columns to {OUT_FILE}")


if __name__ == "__main__":
    main()