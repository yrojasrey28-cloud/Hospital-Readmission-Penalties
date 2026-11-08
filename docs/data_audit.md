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

### Auguit Values & Placeholders
* **Numeric Columns** Cleaned and checked for hidden text strings. Found that 'Number of Readmssions' contains' 3,683 rows with the placeholder ''Too few to Report'' and 6,610 missing values ('Nan')
* **Date:** Confrimed uniform reporting windows ('07/01/2021' to '06/30/2024') across all records
* **Join Coverage** Verified that meaching leys maintain exact 6-digit string formatting with leading zeros intact.
---

## 5. Hospital General Information Dataset (`Hospital_General_Information.csv`)
* **Total Rows & Columns:** []
* **Primary Key Uniqueness (`is_unique`):** 
  * Is `Facility ID` completely unique? []
* **Join Relationship Check:** 
  * Confirmed a ___ relationship between the readmissions file and general information.