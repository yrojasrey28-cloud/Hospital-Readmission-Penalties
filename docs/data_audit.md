CMS Hospital Readmissions & General Information
## Start with Importing Dataset 

## 1. Readmissions Dataset (`FY_2026_Hospital_Readmissions_Reduction_Program_Hospital.csv`)
* **File Release Date / Source:** [August 13 2026, CMS Provider Data]
* **Dataset Shape**
* **Total Rows:** [18,330]
* **Total Columns** [12]
* **Total Unique Hospitasl** [3,055]
* **Datasets First 6 Rows**
* **Target Grain:** One row per `Facility ID` per `Measure Name`.

## 2. Audit Findings & Validation Checks:
* **Row Count per Hospital Check (`rows_per_hospital.value_counts()`):** 
  * [3,055 hospitals had exactly 6 rows.]
* **Measure Count & Names (`nunique()` & `unique()`):** 
  * Total unique measures: [6]
  * Measures found: ['READM-30-HIP-KNEE-HRRP', 'READM-30-CABG-HRRP', 'READM-30-AMI-HRRP', 'READM-30-COPD-HRRP','READM-30-PN-HRRP','READM-30-HF-HRRP']
* **Duplicate Pair Check (`subset=["Facility ID", "Measure Name"]`):** 
  * Total duplicate pairs found: [0]
* **Grain Verification Status:** 
  * **Verified:** The readmissions file successfully conforms to a grain of one row per Facility ID per Measure Name.

### 3.Audit Values & Placeholders
* **Numeric Columns** Cleaned and checked for hidden text strings. Found that 'Number of Readmssions' contains' 3,683 rows with the placeholder ''Too few to Report'' and 6,610 missing values ('Nan')
* **Date:** Confrimed uniform reporting windows ('07/01/2021' to '06/30/2024') across all records
* **Ratio Column** Found how many rows for each hospital had values that were not empty and were be used in conserdation with the ratio value. Total rows vs Values used (non-empty)



---

## 5. Hospital General Information Dataset (`Hospital_General_Information.csv`)
* **Total Rows & Columns:** [5419, 38]
* **Primary Key Uniqueness (`is_unique`):** 
  * Is `Facility ID` completely unique? [True]
* **Hospital Ownership** analyzing categorial distributions establishes a clear baseline for our population size, helping to identify low volume groups.
* **Join Coverage** verfied that Faciity ID for both datasets had the same length of 6 digits, not losing or adding and leading zeros.
  * Revealed 20 hospitals are
* **Join Relationship Check:** 
  * Confirmed a ___ relationship between the readmissions file and general information.

## Footnotes
* **1.** The number of cases/patients is too few to report.
* **5** Results are not available for this reporting period.
* **7** No cases met the criteria for this measure.
* **29.** This measure was calculated using partial performance period data due to a CMS-approved exception.