# Hospital Readmission Reduction Program (HRRP) Analysis

> **Project Status:** Data audit, cleaning pipeline, and SQLite database build complete. Actively running analytical SQL queries and compiling findings.

## Project Overview
Medicare reduces payments to hospitals with higher-than-expected 30-day readmission rates, making excess readmissions a direct financial risk for acute care hospitals. This project uses public Centers for Medicare & Medicaid Services (CMS) data to examine which hospital ownership types, states, and clinical conditions carry the highest excess readmission ratios (`excess_readmission_ratio > 1.0`, used as a proxy for payment penalty exposure). The goal is to recommend where a hospital quality team should focus improvement efforts first.

## Data Sources
* **HRRP Readmissions Data & Hospital General Information (CMS):** Public datasets covering the measurement window from **July 1, 2021 – June 30, 2024** *(update to match your exact audit dates if different)*.

## Findings

1. **Conditions barely differ in how often hospitals exceed expected readmissions.**
   46.8% to 49.9% of hospitals with a ratio are above 1.0 in every measure, close to the
   48.2% overall, which is expected because the ratio is centered on 1.0.
2. **Exceedances are largest in HIP-KNEE and CABG, but the data is thinnest there.**
   Among hospitals above 1.0, the average ratio is 1.128 (HIP-KNEE) and 1.078 (CABG),
   vs 1.039 to 1.056 for the other four. These two also have the most suppressed counts
   (82.5% and 58.7% of usable rows) and the lowest coverage (47.4% and 28.7%), so
   low-volume noise may inflate them.
3. **Proprietary hospitals have the highest average ratio in all six conditions** (groups
   of 50+ hospitals). Example: CABG, 61.8% above 1.0 vs 46.0% for non-profit private
   (avg ratio 1.035 vs 0.994). Also 58.6% vs 45.4% for HF and 56.0% vs 45.5% for PN.
   The gap is modest: 0.004 to 0.041 in average ratio.
4. **The gap holds within states.** In FL, CA and TX, Proprietary hospitals average higher
   than non-profit private (gaps of 0.041, 0.033, 0.017). TN reverses (-0.013, 22 vs 18
   hospitals). Only 4 states had 15+ hospitals of each type.
5. **Geography matters.** Among states with 50+ hospitals, NJ (1.027), FL (1.022) and IL
   (1.018) are highest, WI (0.981) lowest. 22 of 51 states have under 30 hospitals and
   are not ranked.
6. **Missing data differs by group.** Tribal (81.5%), Physician (77.4%) and Federal
   (71.7%) lose most rows to missing ratios. Proprietary loses 43.6% vs 29.9% for non-profit
   private. Suppressed rows average lower in 8 of 9 groups, but the Proprietary ranking
   holds with or without them.

**Where a quality team could start:** heart failure and pneumonia at proprietary hospitals.
They have the most complete data, the most hospitals above expected (1,282 and 1,271), and
Proprietary gaps of 13.2 and 10.5 points. CABG and HIP-KNEE look worse but need a
volume check first.

## Repository Structure & Pipeline
* **`docs/data_audit.md`**: Initial data profiling of 18,330 hospital-measure records across 6 clinical conditions, missingness rules, and analytical guardrails.
* **`src/clean_data.py`**: Joins the two CMS datasets, preserves leading zeros on 6-digit `facility_id` codes (559 IDs), and flags suppressed discharge counts (`counts_suppressed`) without dropping valid ratios.
* **`src/load_db.py`**: Loads the cleaned dataset into a local SQLite database (`data/processed/hrrp.db`) with explicit `PRIMARY KEY` and `CHECK` constraints, plus post-load type and row-count verification.
* **`sql/queries.sql` & `src/run_queries.py`**: *(In Progress)* Analytical queries evaluating penalty exposure across conditions, ownership types, and states.

## How to Run
From the project root directory, run the pipeline in order to rebuild the local SQLite database:

```bash
# 1. Clean and merge raw CMS datasets
python src/clean_data.py

# 2. Build and verify the SQLite database
python src/load_db.py

## Limitations & Analytical Guardrails
* **Snapshot Timing Mismatch:** Hospital General Information reflects a later snapshot than the readmissions measurement window, so a small number of hospitals may have changed ownership or operating status in between.

* **Proxy Metric:** The excess_readmission_ratio (predicted divided by expected readmissions) serves as a proxy for Medicare payment penalty exposure rather than the exact dollar penalty.

* **Small Sample & Waiver Rules:** Groups with fewer than 50 hospitals are flagged to avoid drawing conclusions from noisy samples, and Maryland hospitals are evaluated separately due to Maryland's Medicare payment waiver.

* **Date Window** one reporting window (2021-07 to 2024-06)
* **Query Results** Results cover only hospitals with a reported ratio, and these are associations, not causes (no adjustment for hospital size or patient mix).