# UK construction injury statistics by ComplyOnSite

A tidy, long-format copy of the Health and Safety Executive's official workplace injury and ill-health statistics for Great Britain, with a construction focus. It covers worker deaths from 1974, RIDDOR-reported non-fatal injuries, kinds of accident, and the Labour Force Survey estimates of self-reported injury and work-related ill health. Every value is copied from an HSE spreadsheet cell, or counted from HSE's own record-level list of fatalities, and carries the file, sheet and row it came from.

- [Data files](#files) in CSV and JSON, one per table family
- [Construction-only file](data/construction-only.csv) for site teams who only need section F
- [Three Datawrapper-ready chart files](#chart-files)
- [Method](#method), [caveats](#caveats) and [licence](LICENSE)
- [Checksums](CHECKSUMS.sha256): SHA-256 for every file in `data/` and `charts/`
- [Original HSE files](sources/) with SHA-256 checksums and a [download manifest](sources/MANIFEST.csv)
- [`validate.py`](validate.py) rebuilds everything from `sources/` and checks it against HSE's published headline figures; its output is in [`validation.txt`](validation.txt)

## Release used

Two HSE releases are combined. They are the latest available on 3 October 2026; the next annual release is due in November 2026.

| Release | Published | Data to | Files used |
|---|---|---|---|
| Fatal injury statistics, 2026 | 1 July 2026 | March 2026 (2025/26 provisional) | `ridfatal.xlsx`, `fatalities-reportable-under-riddor.xlsx`, `fatalinjuries.pdf` |
| Annual health and safety statistics, 2025 | 20 November 2025 | March 2025 (2024/25 provisional) | `ridhist.xlsx`, `ridind.xlsx`, `ridkind.xlsx`, `lfsinjind.xlsx`, `lfsinjsum.xlsx`, `lfsillind.xlsx`, `construction.pdf`, `hssh2425.pdf` |

The July 2026 release updates only the fatal injury tables. RIDDOR non-fatal, kind-of-accident and LFS tables are still the November 2025 versions; HSE's tables index says the full RIDDOR suite will be updated in November 2026. All files were downloaded on 3 October 2026 from `https://www.hse.gov.uk/statistics/assets/docs/`. Each URL, HTTP `Last-Modified`, retrieval time, size and SHA-256 is in [`sources/MANIFEST.csv`](sources/MANIFEST.csv).

## Why it is useful

HSE publishes these figures as filtered Excel workbooks with notes, merged headings and shorthand codes. That suits reading on screen but makes it awkward to chart a trend, compare construction with other industries or load the figures into a database. Here every number is one row with its year, industry, measure, unit and rate basis, so it can be filtered in a spreadsheet, queried in SQL or charted directly.

For site teams and principal contractors it answers practical questions with HSE's own numbers: how many construction workers die each year and how that has changed since 1981, which kinds of accident cause those deaths (falls from height account for 97 of the 186 construction worker deaths from 2021/22 to 2025/26p), how construction's self-reported injury rate compares with all industries, and how much ill health the sector reports. For analysts, the provenance columns make each figure checkable against the original cell.

## Files

### Data (`data/`)

Each table family is published as CSV and as JSON. The JSON file holds a `metadata` object (title, source files, licence, attribution, field list, record count) followed by `records`, one object per CSV row, with `null` where the CSV is empty.

| File | Rows | Contents | Source tables |
|---|---:|---|---|
| `riddor-fatal-injuries-by-industry` | 10,336 | Fatal injuries to workers, employees and the self-employed, counts and rates, by industry; fatal injuries to members of the public | RIDHIST Tables 1-2 (1974 to 2024/25p), RIDIND Table 1 (2014/15 to 2024/25p, SIC sections and divisions), RIDFATAL Tables 1-2 (2021/22 to 2025/26p) |
| `riddor-fatal-injuries-by-kind` | 10,449 | Fatal injuries to workers by kind of accident and SIC section | RIDKIND Table 1 (2014/15 to 2024/25p), RIDFATAL Table 3 (all industries, 2021/22 to 2025/26p), counts from HSE's record-level list (2021/22 to 2025/26p) |
| `riddor-nonfatal-injuries-by-industry` | 12,460 | Non-fatal injuries reported by employers: total, major/specified, over-3-day and over-7-day, counts and rates | RIDHIST Table 3 (1974 to 2024/25p), RIDIND Table 3 (2014/15 to 2024/25p) |
| `riddor-nonfatal-injuries-by-kind` | 8,415 | Non-fatal injuries to employees by kind of accident and SIC section: total, specified, over-7-day | RIDKIND Table 2 (2014/15 to 2024/25p) |
| `lfs-self-reported-injury` | 7,976 | Self-reported non-fatal workplace injury: incidence, rate per 100,000 workers, days lost, with 95% confidence intervals | LFSINJSUM Tables 1-5 (all industries, annual 2000/01 to 2024/25), LFSINJIND Tables 1-4 (by industry, 3- and 5-year averages) |
| `lfs-self-reported-ill-health` | 31,328 | Self-reported work-related ill health by industry: prevalence, incidence, days lost; all illness, musculoskeletal disorders, stress/depression/anxiety | LFSILLIND Tables 1-11 |
| `construction-only` | 4,301 | Every construction row from the six families above | as above |

Row counts are records, excluding the CSV header.

### Columns

All data files share the same columns.

| Column | Meaning |
|---|---|
| `dataset` | Table family (file name without extension). |
| `year` | Year or period exactly as HSE labels it, with `[Note n]` references removed. RIDDOR years are financial years, 1 April to 31 March (`2024/25` = 1 April 2024 to 31 March 2025); RIDHIST years up to 1985 are calendar years. HSE marks provisional figures `p` (`2025/26p`) and revised (finalised) figures `r` (`2024/25r`). LFS periods are survey years or ranges such as `2022/23 - 2024/25`. |
| `year_status` | `provisional`, `revised` or `final` for RIDDOR, from HSE's `p`/`r` suffix; `survey estimate` for LFS. |
| `provisional` | `true` when HSE marks the figure provisional. RIDFATAL five-year rows that include 2025/26p are also `true`. |
| `period_type` | `annual`; `5-year total` (RIDFATAL and record-list count rows covering 2021/22 to 2025/26p); `5-year average` (RIDFATAL rates over that period); `3-year annual average` or `5-year annual average` (LFS). |
| `industry` | Industry label as HSE gives it. RIDFATAL labels include the SIC code, for example `Construction (SIC F)`. |
| `industry_code` | SIC 2007 code as HSE gives it: `F`, `F (41-43)`, `41`, `41,43`, `A-U` for all industries, `G,I` and similar for HSE's combined groups. Empty for RIDHIST, whose broad groups span SIC 1980, 1992 and 2007. |
| `industry_level` | `All`, `Section`, `Division`, `Section group` (RIDFATAL combined sections), `Broad industry group` (RIDHIST) or `Missing industry`. |
| `breakdown_type`, `breakdown` | `kind of accident`, `injury category` or `condition`, and the HSE label for it. Empty when the row has no such breakdown. |
| `worker_group` | `workers` (employees and self-employed), `employees`, `self-employed` or `members of the public`. |
| `measure` | What is counted, for example `fatal_injuries`, `fatal_injury_rate`, `nonfatal_injuries_total`, `major_or_specified_injuries`, `over_7_day_injuries`, `incidence`, `incidence_rate`, `prevalence`, `prevalence_rate`, `days_lost`, `days_lost_per_worker`, `days_lost_per_case`. |
| `value` | The number as published. Empty when HSE shows a shorthand code or a blank cell. Never imputed. |
| `value_status` | Empty when `value` is present. Otherwise the HSE code (`[x]` unavailable, `[u]` unavailable or rate not provided, `[z]` not applicable, `[U1]` sample too small) or `blank in source`. The meaning of each code is in the source workbook's notes. |
| `unit` | `count`, `rate`, `thousand workers`, `thousand full-day equivalents` or `days`. LFS counts are in thousands, as HSE publishes them. |
| `rate_basis` | Denominator of a rate: `per 100,000 workers`, `per 100,000 employees`, `per 100,000 self-employed`, `per full-time equivalent worker` or `per case`. Empty for counts. |
| `ci_lower_95`, `ci_upper_95` | HSE's 95% confidence interval for LFS estimates. Empty for RIDDOR, which is a count, not a sample. |
| `sample_size_flag` | HSE's LFS low-sample warning, if any. |
| `significance_vs_all_industries`, `significance_vs_previous_period` | HSE's LFS significance results (`Higher`, `Lower`, `No`, or a shorthand code). |
| `source_table` | Workbook and table, for example `RIDHIST Table 1`. |
| `source_sheet`, `source_row` | Worksheet name and 1-based spreadsheet row of the source cell. Empty `source_row` for counts from the record list, whose `source_notes` lists the contributing rows instead. |
| `source_notes` | HSE note references removed from labels (`Note 10; Note 11` and so on), RIDHIST's regulation, classification and employment-data period, the LFS job-scope note, or the exact counting rule for record-list rows. |
| `source_url` | URL of the downloaded HSE file. |
| `source_published` | Publication date of that file as printed in it (or in its release for the record list). |

### Chart files (`charts/`)

Each is a small wide CSV ready to paste or upload into Datawrapper.

| File | Chart | Source |
|---|---|---|
| `construction-worker-fatalities-1981-to-2025-26.csv` | Line or column chart of construction worker deaths and the rate per 100,000 workers, 1981 to 2025/26p (45 rows) | RIDHIST Table 1 for 1981 to 2020/21; RIDFATAL Table 1 for 2021/22 to 2025/26p |
| `construction-fatal-injuries-by-kind-2021-22-to-2025-26.csv` | Bar chart of construction worker deaths by kind of accident, five-year total and 2025/26p (11 kinds with at least one death) | Counts from the record-level list, 1 July 2026 release |
| `construction-vs-all-industries-self-reported-injury-rate.csv` | Line chart with confidence bands: self-reported non-fatal injury rate per 100,000 workers, construction v all industries, non-overlapping 3-year averages from 2001/02-2003/04 to 2022/23-2024/25 (8 rows) | LFSINJIND Table 1 |

Suggested chart notes: "Source: HSE (RIDDOR / Labour Force Survey), Open Government Licence v3.0. 2025/26 figures are provisional." Rates before 2004/05 use a different employment source, so the rate series has a break there.

## Method

`build.py` (Python standard library only) reads each workbook directly from `sources/` with a small `.xlsx` reader and writes `data/` and `charts/`. It never edits a value: numbers are written as Python reads the cell, which removes binary floating-point noise such as `8.3800000000000008` but keeps HSE's published precision.

General rules for every table:

1. Locate the header row by its first cell and read each data row below it. Rows with an empty first cell are skipped.
2. Remove `[Note n]` references from year, industry and kind labels and record them in `source_notes`. Labels are otherwise unchanged, including HSE's own spellings.
3. Turn each numeric column into one row with its `measure`, `worker_group`, `unit` and `rate_basis`, taken from the column heading.
4. Write numbers to `value`. Write shorthand codes and blank cells to `value_status` with an empty `value`. Nothing is interpolated, smoothed or filled.
5. Set `year_status` from HSE's `p` and `r` suffixes.

Table-specific steps:

- **RIDHIST Table 1** (fatal injuries to workers, 1974 to 2024/25p): one row per year, broad industry group and column (workers, employees, self-employed; each as a count and a rate). The regulation, industry classification and employment-data codes in columns C to E are expanded from the workbook's `Background information` sheet into `source_notes`. Before 1981 only employee deaths were reported, so worker and self-employed values are `[x]`.
- **RIDHIST Table 2** (members of the public, 1981 to 2024/25p): a wide table with one column per broad group, unpivoted to one row per year and group.
- **RIDHIST Table 3** (non-fatal injuries, 1974 to 2024/25p): one row per employment status, year, group and column. Rates for the self-employed are `[u]` throughout because HSE does not publish them.
- **RIDIND Tables 1 and 3** (2014/15 to 2024/25p): all industries, every SIC section and division as HSE publishes them. HSE combines divisions 41 and 43 in some years (`41,43`) and that row is kept as published.
- **RIDKIND Tables 1 and 2** (2014/15 to 2024/25p): one row per year, SIC section and kind of accident. The percentage columns in Table 2 are not copied; they are rounded shares that can be recomputed from the counts.
- **RIDFATAL Tables 1-3** (2021/22 to 2025/26p, published 1 July 2026): Table 1 by main industry, Table 2 members of the public (wide by year, unpivoted), Table 3 all industries by kind of accident. The `Sort code` column supplies `industry_code`; code `0` is written as `A-U`. The five-year row is kept as a `5-year total` for counts and `5-year average` for rates.
- **Record-level fatality list** (`fatalities-reportable-under-riddor.xlsx`, sheet `Fatals 2122 to 2526p`): HSE's list of 1,098 deaths, one row each. RIDKIND has not yet been updated for 2025/26, so the construction kind-of-accident breakdown for the latest year comes from counting this list. Rows with `Employment Status - overview = Workers` are counted by year, `Top-level Industry (SIC section)` and `Kind of accident`, for every combination of the years, sections and kinds present in the list (a combination with no rows is a count of 0), plus a 2021/22 to 2025/26p total. Kind labels keep this file's spelling (`flying or falling`, not `flying/falling`). Age, sex and location fields are not used. `validate.py` confirms that these counts reproduce RIDFATAL Tables 1-3 exactly.
- **LFSINJSUM Tables 1-5**: all-industry annual estimates, 2000/01 to 2024/25, for all injuries, over-3-day and over-7-day absence injuries, and days lost. Estimates, rates and confidence limits are copied; counts stay in thousands.
- **LFSINJIND Tables 1-4 and LFSILLIND Tables 1-11**: rows at `All`, `Section` and `Division` level are kept; the `Group` and `Class` levels (4-digit SIC) are left out because most of their cells are `[U1]`. LFSILLIND includes annual rows at section level as well as 3- and 5-year averages.
- **Construction-only file**: rows whose industry is `Construction`, whose code is `F` or `F (41-43)`, or which are divisions `41`, `42`, `43` or `41,43`.
- **Chart 1** takes RIDHIST for 1981 to 2020/21 and RIDFATAL from 2021/22, so each year uses HSE's latest figure. The two releases agree for every overlapping construction year (checked).

## Validation

`python3 validate.py` checks, without network access:

1. every file in `sources/` matches `sources/SHA256SUMS`;
2. a fresh build from `sources/` reproduces every file in `data/` and `charts/` byte for byte;
3. HSE's own arithmetic holds: workers = employees + self-employed, non-fatal total = major/specified + over-3-day or over-7-day, kinds of accident sum to the all-kinds total, the record list reproduces RIDFATAL Tables 1-3, and construction worker deaths agree across RIDHIST, RIDIND and RIDFATAL;
4. 23 statements in HSE's summary publications (construction report, fatal injuries report and annual summary) match the tidy data, for example 35 construction worker deaths in 2024/25p, 25 in 2025/26p against an average of 37, 50,000 self-reported construction injuries a year, and 3,726 RIDDOR non-fatal injuries to construction employees in 2024/25p.

The 3 October 2026 run passed all 64 checks; see [`validation.txt`](validation.txt). Two HSE percentages (29% of LFS construction injuries over 7 days; 53% of construction ill health musculoskeletal) are checked within ±1.5 points, because HSE computes them from unrounded estimates and the tables publish rounded thousands.

## Caveats

- **Provisional and revised figures.** 2025/26 fatal figures are provisional (`p`) and will be finalised in July 2027. 2024/25 fatal figures were revised in July 2026: the all-industry worker total rose from 124 (RIDHIST, provisional) to 128 (RIDFATAL, revised). Both are kept, each with its source table; filter on `source_table` or use the latest `source_published` to avoid double counting. 2024/25 non-fatal RIDDOR figures remain provisional until November 2026.
- **Overlapping tables.** The same year can appear in RIDHIST, RIDIND, RIDKIND and RIDFATAL. Do not add rows across source tables, or across industry levels (a section and its divisions, or RIDFATAL's `of which` rows).
- **RIDDOR under-reporting.** HSE estimates that only around half of reportable non-fatal injuries to employees are reported, and self-employed injuries are severely under-reported, so HSE gives no self-employed non-fatal rates. Reporting levels may differ between industries. HSE treats the LFS as its preferred measure of the scale of non-fatal injury; RIDDOR is useful for detail such as kind of accident.
- **Breaks in the RIDDOR series.** Reporting rules changed in 1981, 1986, 1996, 2012 (over-3-day to over-7-day) and 2013 (major to specified injuries). Industry classification moved from SIC 1980 to SIC 1992 to SIC 2007, and rate denominators changed from Workforce Jobs to the Annual Population Survey in 2004/05. `source_notes` records the regime for each RIDHIST row. Railway and offshore non-fatal injuries are excluded from 2012/13 and ONR-enforced sites from 2024/25.
- **Small numbers.** Annual fatal counts for one industry are small and vary by chance; HSE recommends five-year averages for comparisons.
- **LFS sampling error.** LFS figures are survey estimates with 95% confidence intervals, rounded to thousands; differences inside the intervals may not be real. HSE suppresses estimates from too few sample cases (`[U1]`) and flags low samples. 2018/19 to 2023/24 estimates were reweighted in November 2025 and differ from earlier releases.
- **LFS job scope.** The industry workbooks (LFSINJIND, LFSILLIND) count only cases in the current or most recent job, so their `All industries` rows are lower than HSE's headline all-jobs figures. For example, LFSILLIND gives 1,494 thousand workers with work-related ill health in 2024/25, against HSE's headline 1.9 million. Use LFSINJSUM for headline injury totals.
- **Coronavirus.** HSE flags 2019/20 to 2021/22 as affected by the pandemic, and 2020/21 LFS days-lost estimates are unavailable.
- **Not included.** Fatal occupational disease (for example asbestos-related cancers); costs to Britain; RIDDOR regional, age and site-of-injury tables; LFS group and class levels. Members-of-the-public deaths are included only at the industry levels in RIDHIST Table 2 and RIDFATAL Table 2.

## Licence and attribution

The data is Crown copyright, published by HSE and reused under the [Open Government Licence v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/). HSE's [copyright page](https://www.hse.gov.uk/help/copyright.htm) (updated 29 August 2025, read 3 October 2026) states that Crown material on its website may be reused under the OGL and gives the preferred acknowledgement used here:

> Contains public sector information published by the Health and Safety Executive and licensed under the Open Government Licence.

ComplyOnSite's restructuring is offered under the same licence. This dataset is not endorsed by HSE. See [LICENSE](LICENSE) and [CITATION.cff](CITATION.cff).

## Made by ComplyOnSite

Made by [ComplyOnSite](https://complyonsite.com/), practical UK construction and waste compliance tools. If you turn these figures into site briefings, toolbox talks or tender evidence, our [free tools](https://complyonsite.com/tools) handle day-to-day site paperwork such as waste codes and consignment notes.
