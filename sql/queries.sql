-- =============================================================================
-- queries.sql: HRRP analysis queries (run against data/processed/hrrp.db)
--
-- Table: analysis_table, one row per hospital per measure (18,330 rows).
-- Key columns:
--   excess_readmission_ratio  predicted / expected. Above 1.0 = more readmissions
--                             than expected, which is the penalty-exposure proxy.
--                             NULL when CMS did not report it. Never 0.
--   has_ratio                 1 if the ratio exists, 0 if not
--   counts_suppressed         1 if the readmission count was "Too Few to Report"
--                             (these rows still have a ratio)
--   in_general_info          1 if the hospital matched General Information,
--                             0 means ownership is "Unknown"
--
-- Rules carried over from docs/data_audit.md:
--   * Missing ratios stay out of every average (AVG ignores NULL) and out of
--     every percentage denominator (use SUM(has_ratio), not COUNT(*)).
--   * Each measure covers a different set of hospitals, so compare within a
--     measure first.
--   * Ownership comparisons exclude unmatched hospitals (in_general_info = 1).
--   * Report n everywhere. Groups with fewer than 50 hospitals are flagged and
--     not used for conclusions.
--
-- Do not put semicolons inside comments. run_queries.py splits on them.
-- =============================================================================


-- Q1: Which conditions carry the most readmission risk, and how complete is each measure?
-- Analyst Thinking: this is the baseline. Before comparing ownership or states I
-- need to know how many hospitals each measure covers and how many have a
-- ratio. Percentages use SUM(has_ratio) as the denominator so hospitals with no
-- ratio cannot make a measure look better or worse than it is.
-- There is only one reporting window (2021-07-01 to 2024-06-30), so this
-- compares conditions with each other. It is not a trend over time.
-- Added after the first run: the ratio is centered on 1.0 by design, so about
-- half of hospitals are above 1.0 for every measure and pct_above_1 barely
-- separates them (46.8 to 49.9). Severity (avg_ratio_when_above_1) and
-- pct_usable_suppressed (how much of a measure rests on low-volume hospitals)
-- are the columns that actually differ, so the results are sorted by severity.
SELECT
    measure,
    COUNT(*)                                                         AS hospitals_in_program,
    SUM(has_ratio)                                                   AS with_ratio,
    ROUND(100.0 * SUM(has_ratio) / COUNT(*), 1)                      AS pct_with_ratio,
    SUM(counts_suppressed)                                           AS counts_suppressed_rows,
    ROUND(100.0 * SUM(counts_suppressed) / SUM(has_ratio), 1)        AS pct_usable_suppressed,
    SUM(CASE WHEN excess_readmission_ratio > 1.0 THEN 1 ELSE 0 END)  AS n_above_1,
    ROUND(100.0 * SUM(CASE WHEN excess_readmission_ratio > 1.0 THEN 1 ELSE 0 END)
          / SUM(has_ratio), 1)                                       AS pct_above_1,
    ROUND(AVG(excess_readmission_ratio), 4)                          AS avg_ratio,
    ROUND(AVG(CASE WHEN excess_readmission_ratio > 1.0
                   THEN excess_readmission_ratio END), 4)            AS avg_ratio_when_above_1,
    ROUND(MAX(excess_readmission_ratio), 4)                          AS max_ratio
FROM analysis_table
GROUP BY measure
ORDER BY avg_ratio_when_above_1 DESC;


-- Q2: Within each condition, which ownership types have the highest penalty exposure?
-- Analyst Thinking: grouped by measure first, then ownership, because the audit
-- found each measure covers a different set of hospitals. Averaging across
-- measures would mix those populations. Only rows with a ratio and a General
-- Information match are used (has_ratio = 1 and in_general_info = 1), so
-- "Unknown" ownership never appears as a group.
-- avg_ratio_when_above_1 shows severity: among hospitals above 1.0, how far
-- above? pct_above_1 shows how common the problem is. Both matter for focus.
-- sample_flag marks groups under 50 hospitals, which the audit says not to
-- draw conclusions from.
SELECT
    measure,
    hospital_ownership,
    COUNT(*)                                                         AS n_hospitals,
    SUM(CASE WHEN excess_readmission_ratio > 1.0 THEN 1 ELSE 0 END)  AS n_above_1,
    ROUND(100.0 * SUM(CASE WHEN excess_readmission_ratio > 1.0 THEN 1 ELSE 0 END)
          / COUNT(*), 1)                                             AS pct_above_1,
    ROUND(AVG(excess_readmission_ratio), 4)                          AS avg_ratio,
    ROUND(AVG(CASE WHEN excess_readmission_ratio > 1.0
                   THEN excess_readmission_ratio END), 4)            AS avg_ratio_when_above_1,
    CASE WHEN COUNT(*) < 50 THEN 'low n (<50)' ELSE 'ok' END        AS sample_flag
FROM analysis_table
WHERE has_ratio = 1
  AND in_general_info = 1
GROUP BY measure, hospital_ownership
ORDER BY measure, avg_ratio DESC;


-- Q3: Which states have the highest penalty exposure at the hospital level?
-- Analyst Thinking: a state average over raw rows would give more weight to
-- hospitals that report more measures, and mixes populations across measures.
-- Instead I first build one summary row per hospital (the CTE), keeping only
-- hospitals with at least 3 usable measures. That threshold is a documented
-- choice: it drops hospitals with too little data to summarize. Change the 3 and
-- rerun to test how sensitive the ranking is.
-- States get a three-tier flag: ok (50 or more hospitals), caution (30 to 49)
-- and do not rank (under 30). The first run flagged 34 of 51 states under the
-- single 50 cutoff, so one hard cutoff left too little to compare.
-- Maryland is labelled because the audit notes Maryland hospitals may be
-- waived from payment adjustments, so its ratio may not mean a penalty.
WITH hospital_summary AS (
    SELECT
        facility_id,
        state,
        COUNT(*)                        AS usable_measures,
        AVG(excess_readmission_ratio)   AS hospital_avg_ratio
    FROM analysis_table
    WHERE has_ratio = 1
    GROUP BY facility_id, state
    HAVING COUNT(*) >= 3
)
SELECT
    state,
    COUNT(*)                                                        AS n_hospitals,
    ROUND(AVG(hospital_avg_ratio), 4)                               AS avg_ratio,
    ROUND(100.0 * SUM(CASE WHEN hospital_avg_ratio > 1.0 THEN 1 ELSE 0 END)
          / COUNT(*), 1)                                            AS pct_hospitals_above_1,
    CASE WHEN COUNT(*) >= 50 THEN 'ok'
         WHEN COUNT(*) >= 30 THEN 'caution (30-49)'
         ELSE 'do not rank (<30)' END                               AS sample_flag,
    CASE WHEN state = 'MD' THEN 'check payment waiver' ELSE '' END  AS note
FROM hospital_summary
GROUP BY state
ORDER BY avg_ratio DESC;


-- Q4: Do missing ratios and suppressed counts change the ownership comparison?
-- Analyst Thinking: ownership results only describe hospitals with a reported
-- ratio. If one ownership type loses far more rows to missing ratios, its
-- average is based on a different slice of hospitals and is less comparable.
-- pct_no_ratio shows that coverage gap (denominator is all rows).
-- pct_usable_suppressed shows how many usable rows have a "Too Few to Report"
-- readmission count.
-- The last three columns are a sensitivity check: if the average ratio for
-- suppressed rows is similar to the average for unsuppressed rows, then not
-- weighting by discharges (which suppressed rows lack) is unlikely to have
-- changed the story.
SELECT
    hospital_ownership,
    COUNT(*)                                                        AS hospital_measure_rows,
    COUNT(*) - SUM(has_ratio)                                       AS rows_no_ratio,
    ROUND(100.0 * (COUNT(*) - SUM(has_ratio)) / COUNT(*), 1)        AS pct_no_ratio,
    SUM(counts_suppressed)                                          AS suppressed_rows,
    ROUND(100.0 * SUM(counts_suppressed) / SUM(has_ratio), 1)       AS pct_usable_suppressed,
    ROUND(AVG(excess_readmission_ratio), 4)                         AS avg_ratio_all_usable,
    ROUND(AVG(CASE WHEN counts_suppressed = 0
                   THEN excess_readmission_ratio END), 4)           AS avg_ratio_unsuppressed,
    ROUND(AVG(CASE WHEN counts_suppressed = 1
                   THEN excess_readmission_ratio END), 4)           AS avg_ratio_suppressed
FROM analysis_table
WHERE in_general_info = 1
GROUP BY hospital_ownership
ORDER BY pct_no_ratio DESC;


-- Q5: Does the Proprietary gap hold inside the same state?
-- Analyst Thinking: Q2 says Proprietary hospitals run higher, and Q3 says some
-- states run higher. If Proprietary hospitals are concentrated in high-ratio
-- states, the ownership gap could really be a state effect. Comparing the two
-- ownership types inside each state removes that. Only states with at least 15
-- hospitals of each type are shown, and the same 3-usable-measure rule as Q3 is
-- used. gap is proprietary minus non-profit private, so a positive gap means
-- Proprietary is higher in that state. If this returns no rows, check that the
-- ownership strings match your data exactly.
WITH hospital_summary AS (
    SELECT
        facility_id,
        state,
        hospital_ownership,
        COUNT(*)                        AS usable_measures,
        AVG(excess_readmission_ratio)   AS hospital_avg_ratio
    FROM analysis_table
    WHERE has_ratio = 1
      AND in_general_info = 1
      AND hospital_ownership IN ('Proprietary', 'Voluntary non-profit - Private')
    GROUP BY facility_id, state, hospital_ownership
    HAVING COUNT(*) >= 3
)
SELECT
    state,
    SUM(CASE WHEN hospital_ownership = 'Proprietary' THEN 1 ELSE 0 END)   AS n_proprietary,
    SUM(CASE WHEN hospital_ownership <> 'Proprietary' THEN 1 ELSE 0 END)  AS n_nonprofit_private,
    ROUND(AVG(CASE WHEN hospital_ownership = 'Proprietary'
                   THEN hospital_avg_ratio END), 4)                       AS avg_ratio_proprietary,
    ROUND(AVG(CASE WHEN hospital_ownership <> 'Proprietary'
                   THEN hospital_avg_ratio END), 4)                       AS avg_ratio_nonprofit_private,
    ROUND(AVG(CASE WHEN hospital_ownership = 'Proprietary' THEN hospital_avg_ratio END)
        - AVG(CASE WHEN hospital_ownership <> 'Proprietary' THEN hospital_avg_ratio END), 4) AS gap
FROM hospital_summary
GROUP BY state
HAVING SUM(CASE WHEN hospital_ownership = 'Proprietary' THEN 1 ELSE 0 END) >= 15
   AND SUM(CASE WHEN hospital_ownership <> 'Proprietary' THEN 1 ELSE 0 END) >= 15
ORDER BY gap DESC;