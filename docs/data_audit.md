# Data Audit: Hospital Readmissions Reduction Program (HRRP)

Audit of the two raw CMS files before any cleaning. Findings are listed first, then the evidence behind them. Anything marked **TODO** is not yet verified.

## 1. Sources

| File | Source | Released / modified | Downloaded |
|---|---|---|---|
| `FY_2026_Hospital_Readmissions_Reduction_Program_Hospital.csv` | CMS Provider Data Catalog, Hospital Readmissions Reduction Program |
| `Hospital_General_Information.csv` | CMS Provider Data Catalog, Hospital General Information |

Footnote definitions: CMS footnote crosswalk.
The two files were released about six months apart. Hospital ownership and type change rarely, so I use the later General Information snapshot to describe hospitals in the earlier readmissions release. This is listed as a limitation.

## 2. Summary of findings and decisions

| # | Finding | Evidence | Decision | Why |
|---|---|---|---|---|
| 1 | Grain is one row per hospital per measure | 3,055 hospitals x 6 measures = 18,330 rows; 0 duplicate (Facility ID, Measure Name) pairs | Keep this grain for the analysis table | Matches the source, keeps SQL aggregation simple, avoids hiding gaps in a wide table |
| 2 | Missing numbers are the text "N/A", not blanks | "N/A" in 6,610 ratio rows and 10,088 discharge rows | Read with `keep_default_na=False` and map placeholders explicitly | pandas otherwise converts text to NaN silently |
| 3 | 36% of rows have no ratio | 6,610 of 18,330; usable range by measure is 29% to 89% | Keep rows, keep NULL (never 0), add `has_ratio` | A zero would claim "no excess readmissions"; flags keep exclusions visible |
| 4 | Missing ratios are explained by footnotes | Footnote 1: 3,150; footnote 5: 3,255; footnote 7: 205 | Add `missing_reason` column | Keeps the three causes separate |
| 5 | Counts are suppressed on rows that have a ratio | "Too Few to Report" in 3,683 rows, all with a ratio | Add `counts_suppressed`; do not use discharge weighting as the primary method | Weighting would drop 31% of usable rows |
| 6 | Each measure covers a different set of hospitals | CABG 878 hospitals vs pneumonia 2,715 | Analyze per measure; document any hospital-level threshold | Averaging across measures mixes populations |
| 7 | Only acute care hospitals are in the program | All 3,035 matched hospitals are Acute Care Hospitals | Describe results as acute care hospitals only | Prevents overgeneralizing |
| 8 | 20 hospitals have no General Information match | 120 rows (0.65%), 39 usable | Left join, flag `in_general_info = False`, ownership "Unknown"; exclude only from ownership comparisons | Nothing silently dropped |
| 9 | Some ownership groups are very small | Tribal 9, Federal 23 matched hospitals | Always report n; no conclusions for groups under 30 | Small groups give unstable results |
| 10 | Ratio equals predicted / expected | Max absolute difference 6.5e-5 across 11,720 rows | Add as an assertion in the cleaning script | A check in code protects every rerun |

## 3. Readmissions file

**Shape:** 18,330 rows, 12 columns, 3,055 hospitals.

**Columns:** Facility Name, Facility ID, State, Measure Name, Number of Discharges, Footnote, Excess Readmission Ratio, Predicted Readmission Rate, Expected Readmission Rate, Number of Readmissions, Start Date, End Date.

**Measurement window:** every row has start date 07/01/2021 and end date 06/30/2024.

**Grain check:** every hospital has exactly 6 rows (one per measure: AMI, CABG, COPD, HF, HIP-KNEE, PN), with 0 duplicate pairs.

### 3a. Usable ratio values by measure

| Measure | Hospitals | Usable ratio | Share |
|---|---|---|---|
| READM-30-PN-HRRP | 3,055 | 2,715 | 89% |
| READM-30-HF-HRRP | 3,055 | 2,621 | 86% |
| READM-30-COPD-HRRP | 3,055 | 2,323 | 76% |
| READM-30-AMI-HRRP | 3,055 | 1,736 | 57% |
| READM-30-HIP-KNEE-HRRP | 3,055 | 1,447 | 47% |
| READM-30-CABG-HRRP | 3,055 | 878 | 29% |
| **All** | **18,330** | **11,720** | **64%** |

Hospitals by number of usable measures: 0 measures: 222 (7.3%); 1: 202; 2: 239; 3: 484; 4: 599; 5: 662; 6: 647 (21%).

### 3b. Placeholders

| Column | Placeholder values |
|---|---|
| Excess Readmission Ratio | "N/A" (6,610) |
| Predicted / Expected Readmission Rate | each missing in 6,610 rows (**TODO:** confirm they are the same rows) |
| Number of Discharges | "N/A" (10,088) |
| Number of Readmissions | "N/A" (6,610) and "Too Few to Report" (3,683) |
| Footnote | blank (11,343), meaning no footnote |

"N/A" and "Too Few to Report" mean different things and stay separate.

### 3c. Footnotes

| Footnote | Meaning (CMS) | Rows | Has ratio | Has discharge count |
|---|---|---|---|---|
| (blank) | No footnote | 11,343 | all | 7,798 yes, 3,545 no |
| 1 | Number of cases too few to report | 3,150 | none | none |
| 5 | Results not available for this reporting period | 3,255 | none | none |
| 7 | No cases met the criteria for this measure | 205 | none | all (**TODO:** check values, possibly zeros) |
| 29 | Partial performance period data due to a CMS-approved exception | 377 | all | 239 yes, 138 no |

Of the 6,610 rows with no ratio, 48% are footnote 1, 49% footnote 5, and 3% footnote 7.

**Suppressed counts:** 3,683 rows have a ratio but "Too Few to Report" for the readmission count and no discharge count (3,545 with a blank footnote, 138 with footnote 29). That is 31% of the 11,720 usable rows.

### 3d. Ratio validation

- Excess Readmission Ratio equals Predicted / Expected within rounding (n = 11,720; max absolute difference 6.5e-5, due to four-decimal storage).
- Ratio range 0.47 to 1.63; median 0.997; mean 1.002. No zeros or extreme values.

## 4. Hospital General Information file

**Shape:** 5,419 rows, 38 columns. `Facility ID` is unique.

**Facility ID format:** 6 characters in both files, so leading zeros were preserved (files read as text).

**Hospitals in the program (3,035 matched):**

| Ownership | Hospitals |
|---|---|
| Voluntary non-profit, private | 1,474 |
| Proprietary | 619 |
| Voluntary non-profit, other | 241 |
| Government, hospital district or authority | 220 |
| Voluntary non-profit, church | 199 |
| Government, local | 135 |
| Physician | 70 |
| Government, state | 45 |
| Government, federal | 23 |
| Tribal | 9 |

Groups under 30 hospitals (federal, tribal) are not used for conclusions.

## 5. Join audit

**Relationship:** many-to-one (6 readmissions rows per General Information row), because `Facility ID` is unique in General Information.

**Join method:** left join with readmissions as the base and `validate="many_to_one"`. Result: 18,330 rows, same as the source.

### 5a. In General Information but not in readmissions (2,384)

General Information lists all Medicare-registered hospitals. The program covers only acute care hospitals.

| Hospital type | Not in program |
|---|---|
| Critical access | 1,382 |
| Psychiatric | 624 |
| Veterans Administration | 132 |
| Children's | 94 |
| Acute care | 72 |
| Rural emergency | 43 |
| Department of Defense | 32 |
| Long-term | 5 |

**The 72 acute care hospitals not in the program:** 59 are in US territories (PR 53, GU 2, VI 2, AS 1, MP 1). The other 13 are scattered (TX 5, AZ 2, GA 2, CA 1, UT 1, VA 1, WY 1) with no explanation found.

### 5b. In readmissions but not in General Information (20 hospitals, 120 rows)

- 120 rows is 0.65% of the data; 39 of them have a usable ratio.
- 3 of the 20 appear in General Information under a different ID with the same name: Ascension Seton Smithville (450143 to 671304), Eastland Memorial Hospital (450411 to 671303), and Carthage Area Hospital (330060 to 331318 or 331324).
- The other 17 have no match. The cause is not verified (possibly closure or renaming between releases).
- Decision: keep all 20 with `in_general_info = False` and ownership "Unknown". ID remapping is a possible later improvement, not done now because name matches alone are not proof.

## 6. Limitations

- The two files were released at different times (see section 1).
- 36% of hospital-measure rows have no ratio, so results describe hospitals with reportable data. Half of the missing rows are "not available," and the reason is unknown.
- The excess readmission ratio is a proxy for penalty exposure. It is not the payment penalty itself.
- Maryland hospitals may be waived from payment adjustments under the program. **TODO:** check Maryland rows in the file.

## 7. Open items

- [ ] Footnote 7 rows: check the discharge values.
- [ ] Confirm ratio, predicted, and expected rates are missing on the same rows.
- [ ] Confirm release and download dates, and add the footnote source URL.
- [ ] Check Maryland hospitals in the data.
- [ ] Explain (or label unexplained) the 17 unmatched hospitals and the 13 acute care hospitals outside US territories.