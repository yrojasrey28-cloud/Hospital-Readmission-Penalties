# Hospital Readmission Reduction Program (HRRP) Analysis

> **Project Status:** Data audit, cleaning pipeline, and SQLite database build complete. Actively running analytical SQL queries and compiling findings.

## Project Overview
Medicare reduces payments to hospitals with higher-than-expected 30-day readmission rates, making excess readmissions a direct financial risk for acute care hospitals. This project uses public Centers for Medicare & Medicaid Services (CMS) data to examine which hospital ownership types, states, and clinical conditions carry the highest excess readmission ratios (`excess_readmission_ratio > 1.0`, used as a proxy for payment penalty exposure). The goal is to recommend where a hospital quality team should focus improvement efforts first.

## Data Sources
* **HRRP Readmissions Data & Hospital General Information (CMS):** Public datasets covering the measurement window from **July 1, 2021 – June 30, 2024** *(update to match your exact audit dates if different)*.

## Repository Structure & Pipeline
* **`docs/data_audit.md`**: Initial data profiling of 18,330 hospital-measure records across 6 clinical conditions, missingness rules, and analytical guardrails.
* **`src/clean_data.py`**: Joins the two CMS datasets, preserves leading zeros on 6-digit `facility_id` codes (559 IDs), and flags suppressed discharge counts (`counts_suppressed`) without dropping valid ratios.
* **`src/load_db.py`**: Loads the cleaned dataset into a local SQLite database (`data/processed/hrrp.db`) with explicit `PRIMARY KEY` and `CHECK` constraints, plus post-load type and row-count verification.
* **`sql/queries.sql` & `src/run_queries.py`**: *(In Progress)* Analytical queries evaluating penalty exposure across conditions, ownership types, and states.

## Limitations & Analytical Guardrails
* **Snapshot Timing Mismatch:** Hospital General Information reflects a later snapshot than the readmissions measurement window, so a small number of hospitals may have changed ownership or operating status in between.

* **Proxy Metric:** The excess_readmission_ratio (predicted divided by expected readmissions) serves as a proxy for Medicare payment penalty exposure rather than the exact dollar penalty.

* **Small Sample & Waiver Rules:** Groups with fewer than 50 hospitals are flagged to avoid drawing conclusions from noisy samples, and Maryland hospitals are evaluated separately due to Maryland's Medicare payment waiver.

## How to Run
From the project root directory, run the pipeline in order to rebuild the local SQLite database:

```bash
# 1. Clean and merge raw CMS datasets
python src/clean_data.py

# 2. Build and verify the SQLite database
python src/load_db.py

