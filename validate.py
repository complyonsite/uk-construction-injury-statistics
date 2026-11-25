#!/usr/bin/env python3
"""Validate the dataset. Python 3.9+ standard library only.

1. Source files match sources/SHA256SUMS.
2. Rebuilding from sources/ reproduces every file in data/ and charts/ byte for byte.
3. Internal arithmetic in the HSE tables holds (workers = employees + self-employed, etc.).
4. Figures HSE states in its own summary publications match the tidy data.

Run:  python3 validate.py        (exit status 1 if any check fails)
"""
import hashlib
import sys
from collections import defaultdict

import build

results = []


def check(name, ok, detail=""):
    results.append(ok)
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name, ("  [" + detail + "]") if detail else ""))


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
print("== 1. Source checksums")
listed = {}
for line in (build.SRC / "SHA256SUMS").read_text().splitlines():
    digest, name = line.split(None, 1)
    listed[name.strip()] = digest
for name in build.SOURCES:
    check("sha256 %s" % name, listed.get(name) == sha256(build.SRC / name))
extra = sorted(p.name for p in build.SRC.iterdir() if p.name not in build.SOURCES and p.name not in ("SHA256SUMS", "MANIFEST.csv"))
check("no unlisted files in sources/", not extra, ", ".join(extra))

# ---------------------------------------------------------------------------
print("\n== 2. Rebuild from sources/ and compare with published files")
wb, tables, construction = build.build_tables()
files = build.render(tables, construction)
for rel, text in files.items():
    on_disk = (build.ROOT / rel).read_text(encoding="utf-8") if (build.ROOT / rel).exists() else None
    check("reproduces %s" % rel, on_disk == text)
expected = set(files)
present = {str(p.relative_to(build.ROOT)) for d in ("data", "charts") for p in (build.ROOT / d).iterdir()}
check("no stray files in data/ or charts/", present == expected, ", ".join(sorted(present ^ expected)))
check("construction-only rows all come from the six families",
      all(any(r is x for x in tables[r["dataset"]]) for r in construction))
for name, rows in tables.items():
    print("      %-40s %6d rows" % (name, len(rows)))
print("      %-40s %6d rows" % ("construction-only", len(construction)))

# ---------------------------------------------------------------------------
print("\n== 3. Internal consistency of the source tables")
ALL = [r for rows in tables.values() for r in rows]


def num(r):
    return r["value"] if r["value_status"] == "" else None


def group_check(label, rows, keys, total_key, part_keys, field="worker_group"):
    """For each group of rows sharing `keys`, value[total] == sum(value[parts]) where all are numeric."""
    groups = defaultdict(dict)
    for r in rows:
        groups[tuple(r[k] for k in keys)][r[field]] = num(r)
    tested = bad = 0
    for g in groups.values():
        vals = [g.get(k) for k in [total_key] + part_keys]
        if any(v is None for v in vals):
            continue
        tested += 1
        if vals[0] != sum(vals[1:]):
            bad += 1
    check(label, bad == 0 and tested > 0, "%d groups tested, %d mismatches" % (tested, bad))


fatal_counts = [r for r in tables["riddor-fatal-injuries-by-industry"] + tables["riddor-fatal-injuries-by-kind"]
                if r["measure"] == "fatal_injuries" and r["worker_group"] in ("workers", "employees", "self-employed")
                and not r["source_table"].startswith("Fatalities reportable")]
group_check("fatal: workers = employees + self-employed (RIDHIST, RIDIND, RIDFATAL, RIDKIND)", fatal_counts,
            ("source_table", "source_row"), "workers", ["employees", "self-employed"])

nf = [r for r in tables["riddor-nonfatal-injuries-by-industry"] + tables["riddor-nonfatal-injuries-by-kind"]
      if r["unit"] == "count"]
for parts in (["major_or_specified_injuries", "over_3_day_injuries"], ["major_or_specified_injuries", "over_7_day_injuries"]):
    group_check("non-fatal: total = %s + %s (RIDHIST, RIDIND, RIDKIND)" % tuple(parts),
                [dict(r, part=r["measure"]) for r in nf], ("source_table", "source_row", "worker_group"),
                "nonfatal_injuries_total", parts, field="part")

kind_rows = [r for r in tables["riddor-fatal-injuries-by-kind"] + tables["riddor-nonfatal-injuries-by-kind"]
             if not r["source_table"].startswith("Fatalities reportable")]
sums = defaultdict(lambda: [None, 0, 0])
for r in kind_rows:
    k = (r["source_table"], r["year"], r["industry_code"], r["worker_group"], r["measure"])
    if r["breakdown"] == "All accident kinds":
        sums[k][0] = num(r)
    else:
        sums[k][2] += 1
        if num(r) is not None:
            sums[k][1] += num(r)
# RIDKIND Table 1 gives some groups (2025/26p missing industry, Z) only an 'All accident kinds' row,
# with no row per kind, so there is nothing to add up.
totals_only = [k for k, (t, s, parts) in sums.items() if parts == 0]
bad = [k for k, (t, s, parts) in sums.items() if parts and t is not None and t != s]
check("kind of accident: sum of kinds = 'All accident kinds' (RIDKIND, RIDFATAL Table 3)", not bad,
      "%d groups tested, %d mismatches, %d with only a total row" % (len(sums) - len(totals_only), len(bad), len(totals_only)))

# Record-level list v RIDFATAL tables (same 1 July 2026 release)
recs = build.fatal_records(wb)
workers = [r for r in recs if r["group"] == "Workers"]
ridfatal1 = [r for r in tables["riddor-fatal-injuries-by-industry"] if r["source_table"] == "RIDFATAL Table 1"
             and r["worker_group"] == "workers" and r["measure"] == "fatal_injuries" and r["period_type"] == "annual"]
mism = []
for r in ridfatal1:
    code = r["industry_code"]
    if code == "A-U":
        n = sum(1 for x in workers if x["year"] == r["year"])
    elif code == "E38":
        continue  # the record list has no division-level coding in this column
    else:
        letters = {"G,I": "GI", "J-N": "JKLMN", "O-Q": "OPQ", "R-U": "RSTU"}.get(code, code)
        n = sum(1 for x in workers if x["year"] == r["year"] and x["section"].split(" - ")[0] in letters)
    if n != r["value"]:
        mism.append("%s %s: records %d v table %s" % (r["year"], code, n, r["value"]))
check("record list: worker deaths by year and industry = RIDFATAL Table 1", not mism, "; ".join(mism[:5]))


def norm_kind(k):
    return k.replace("/", " or ").replace("  ", " ").strip().lower()


mism = []
for r in tables["riddor-fatal-injuries-by-kind"]:
    if r["source_table"] != "RIDFATAL Table 3" or r["worker_group"] != "workers" or r["period_type"] != "annual":
        continue
    if r["breakdown"] == "All accident kinds":
        continue
    n = sum(1 for x in workers if x["year"] == r["year"] and norm_kind(x["kind"]) == norm_kind(r["breakdown"]))
    if n != r["value"]:
        mism.append("%s %s: %d v %s" % (r["year"], r["breakdown"], n, r["value"]))
check("record list: worker deaths by year and kind = RIDFATAL Table 3", not mism, "; ".join(mism[:5]))

mop = [r for r in recs if r["group"] == "Members of the public"]
mism = []
for r in tables["riddor-fatal-injuries-by-industry"]:
    if r["source_table"] == "RIDFATAL Table 2" and r["industry_code"] == "A-U":
        n = sum(1 for x in mop if x["year"] == r["year"])
        if n != r["value"]:
            mism.append("%s: %d v %s" % (r["year"], n, r["value"]))
check("record list: members of the public by year = RIDFATAL Table 2", not mism, "; ".join(mism))

# Cross-release consistency for construction worker deaths
F = {}
for r in tables["riddor-fatal-injuries-by-industry"]:
    if r["measure"] == "fatal_injuries" and r["worker_group"] == "workers" and r["period_type"] == "annual" and build.is_construction(r) \
            and r["industry_level"] != "Division":
        F.setdefault(r["year"].rstrip("pr"), {})[r["source_table"]] = r["value"]
diff = {y: v for y, v in F.items() if len(set(v.values())) > 1}
check("construction worker deaths agree across RIDHIST, RIDIND and RIDFATAL where years overlap", not diff, str(diff))

# ---------------------------------------------------------------------------
print("\n== 4. Figures stated in HSE's own summary publications")


def get(**kw):
    rows = [r for r in ALL if all(r[k] == v for k, v in kw.items())]
    if len(rows) != 1:
        raise SystemExit("validator lookup did not resolve to one row: %r (%d rows)" % (kw, len(rows)))
    return rows[0]["value"]


def stated(source, page, quote, ok, derived):
    check('%s p.%s: "%s"' % (source, page, quote), ok, derived)


CON = "construction.pdf (Construction statistics in Great Britain, 2026)"
FAT = "fatalinjuries.pdf (Work-related fatal injuries in Great Britain, 2026)"
SUM = "hssh2526.pdf (Health and safety at work: summary statistics 2026)"
LFS_PERIOD = "2023/24 - 2025/26"

hist1 = dict(source_table="RIDHIST Table 1", period_type="annual")
v = get(industry="Construction", year="2025/26p", worker_group="workers", measure="fatal_injuries", **hist1)
stated(CON, 16, "There were 25 fatal injuries to workers in 2025/26p", v == 25, "RIDHIST Table 1 = %s" % v)

yrs = ["2021/22", "2022/23", "2023/24", "2024/25r", "2025/26p"]
vals = [get(industry="Construction", year=y, worker_group="workers", measure="fatal_injuries", **hist1) for y in yrs]
avg = sum(vals) / 5
stated(CON, 16, "annual average number of 37 fatalities for 2021/22-2025/26p", round(avg) == 37,
       "RIDHIST %s, mean %.1f" % (vals, avg))

k1 = dict(source_table="RIDKIND Table 1", industry_code="F", worker_group="workers", measure="fatal_injuries")
falls = sum(get(year=y, breakdown="Falls from a height", **k1) for y in yrs)
allk = sum(get(year=y, breakdown="All accident kinds", **k1) for y in yrs)
stated(CON, 16, "52% of deaths over the same five-year period were classified as Falls from a height",
       round(100 * falls / allk) == 52, "RIDKIND %d/%d = %.1f%%" % (falls, allk, 100 * falls / allk))

h2 = dict(source_table="RIDHIST Table 2", industry="Construction", measure="fatal_injuries")
v = get(year="2025/26p", **h2)
mvals = [get(year=y, **h2) for y in yrs]
stated(CON, 16, "3 fatal injuries to members of the public in 2025/26p ... annual average of 4",
       v == 3 and round(sum(mvals) / 5) == 4, "RIDHIST Table 2 = %s; five years %s" % (v, mvals))

lf = dict(source_table="LFSINJIND Table-1", industry_code="F", industry_level="Section", year=LFS_PERIOD)
inc = get(measure="incidence", **lf)
stated(CON, 18, "an estimated 48,000 workers who reported sustaining a workplace non-fatal injury", inc == 48,
       "LFSINJIND Table-1 = %s thousand" % inc)
rate_f = get(measure="incidence_rate", **lf)
rate_a = get(source_table="LFSINJIND Table-1", industry_level="All", year=LFS_PERIOD, measure="incidence_rate")
stated(CON, 18, "Around 2.4% of workers ... all industries (1.9%)",
       round(rate_f / 1000, 1) == 2.4 and round(rate_a / 1000, 1) == 1.9,
       "LFSINJIND rates %s and %s per 100,000" % (rate_f, rate_a))
o7 = get(source_table="LFSINJIND Table-3", industry_code="F", industry_level="Section", year=LFS_PERIOD, measure="incidence")
stated(CON, 18, "24% of these workplace non-fatal injuries resulted in absence from work of over 7 days (approximate: HSE uses unrounded estimates)",
       abs(100 * o7 / inc - 24) <= 1.5, "LFSINJIND Table-3/Table-1 = %s/%s = %.0f%%" % (o7, inc, 100 * o7 / inc))

h3 = dict(source_table="RIDHIST Table 3", industry="Construction", year="2025/26p", worker_group="employees")
t, s, o = (get(measure=m, **h3) for m in ("nonfatal_injuries_total", "major_or_specified_injuries", "over_7_day_injuries"))
stated(CON, 20, "3,672 non-fatal injuries to employees ... 1,381 (38%) were specified ... 2,291 (62%)",
       (t, s, o) == (3672, 1381, 2291), "RIDHIST Table 3 = %s, %s, %s" % (t, s, o))
i3 = dict(source_table="RIDIND Table 3", industry_code="F (41-43)", year="2025/26p")
t2 = get(measure="nonfatal_injuries_total", **i3)
check("RIDIND Table 3 construction 2025/26p total agrees with RIDHIST", t2 == t, "%s" % t2)

il = dict(source_table="LFSILLIND Table-1", industry_code="F", industry_level="Section", year=LFS_PERIOD)
prev = get(measure="prevalence", **il)
prate = get(measure="prevalence_rate", **il)
stated(CON, 8, "an estimated 84,000 workers suffering from work-related ill health ... Around 4.1 % (approximate: HSE uses unrounded estimates)",
       prev == 84 and abs(prate / 1000 - 4.1) <= 0.05,
       "LFSILLIND Table-1 = %s thousand, %s per 100,000" % (prev, prate))
msd = get(source_table="LFSILLIND Table-2", industry_code="F", industry_level="Section", year=LFS_PERIOD, measure="prevalence")
stated(CON, 8, "48% were musculoskeletal disorders (approximate: HSE uses unrounded estimates)",
       abs(100 * msd / prev - 48) <= 1.5, "LFSILLIND Table-2/Table-1 = %s/%s = %.1f%%" % (msd, prev, 100 * msd / prev))
mrate = get(source_table="LFSILLIND Table-2", industry_code="F", industry_level="Section", year=LFS_PERIOD, measure="prevalence_rate")
marate = get(source_table="LFSILLIND Table-2", industry_level="All", year=LFS_PERIOD, measure="prevalence_rate")
stated(CON, 10, "an estimated 40,000 workers suffering from a work-related musculoskeletal disorder ... Around 1.9% ... all industries (1.2%)",
       msd == 40 and round(mrate / 1000, 1) == 1.9 and round(marate / 1000, 1) == 1.2,
       "LFSILLIND Table-2 = %s thousand, %s and %s per 100,000" % (msd, mrate, marate))

dli = get(source_table="LFSINJIND Table-4", industry_code="F", industry_level="Section", year=LFS_PERIOD, measure="days_lost")
dlh = get(source_table="LFSILLIND Table-9", industry_code="F", industry_level="Section", year=LFS_PERIOD, measure="days_lost")
stated(CON, 23, "around 2.1 million working days (full-day equivalent) were lost each year due to: Workplace injury (20%) and Work-related illness (80%)",
       round((dli + dlh) / 1000, 1) == 2.1 and round(100 * dli / (dli + dlh)) == 20 and round(100 * dlh / (dli + dlh)) == 80,
       "LFSINJIND Table-4 %s + LFSILLIND Table-9 %s thousand = %s; %.1f%% injury" % (dli, dlh, dli + dlh, 100 * dli / (dli + dlh)))
pwi = get(source_table="LFSINJIND Table-4", industry_code="F", industry_level="Section", year=LFS_PERIOD, measure="days_lost_per_worker")
pwh = get(source_table="LFSILLIND Table-9", industry_code="F", industry_level="Section", year=LFS_PERIOD, measure="days_lost_per_worker")
pai = get(source_table="LFSINJIND Table-4", industry_level="All", year=LFS_PERIOD, measure="days_lost_per_worker")
pah = get(source_table="LFSILLIND Table-9", industry_level="All", year=LFS_PERIOD, measure="days_lost_per_worker")
stated(CON, 23, "around 1.1 working days lost per worker which is the same as the all industry level (1.1 days)",
       round(pwi + pwh, 1) == 1.1 and round(pai + pah, 1) == 1.1,
       "construction %s + %s; all industries %s + %s" % (pwi, pwh, pai, pah))

f1 = dict(source_table="RIDFATAL Table 1", worker_group="workers", period_type="annual")
v = get(industry_code="A-U", year="2025/26p", measure="fatal_injuries", **f1)
stated(FAT, 4, "126 workers killed in work-related accidents in 2025/26p", v == 126, "RIDFATAL Table 1 = %s" % v)
prev_y = get(industry_code="A-U", year="2024/25r", measure="fatal_injuries", **f1)
stated(FAT, 7, "a decrease of 2 fatalities from the previous year", prev_y - v == 2, "%s - %s" % (prev_y, v))
c26 = get(industry_code="F", year="2025/26p", measure="fatal_injuries", **f1)
c5 = get(source_table="RIDFATAL Table 1", worker_group="workers", industry_code="F", period_type="5-year total", measure="fatal_injuries")
stated(FAT, 8, "25 deaths in 2025/26p compared to an annual average of 37 over the last 5 years",
       c26 == 25 and round(c5 / 5) == 37, "RIDFATAL Table 1 = %s; 5-year total %s / 5 = %.1f" % (c26, c5, c5 / 5))
a26 = get(industry_code="A", year="2025/26p", measure="fatal_injuries", **f1)
a25 = get(industry_code="A", year="2024/25r", measure="fatal_injuries", **f1)
stated(FAT, 8, "agriculture, forestry and fishing ... 22 fatal injuries in 2025/26p ... previous year total (23)",
       (a26, a25) == (22, 23), "RIDFATAL Table 1 = %s, %s" % (a26, a25))
r26 = get(industry_code="A-U", year="2025/26p", measure="fatal_injury_rate", **f1)
stated(FAT, 19, "a fatal injury rate of 0.37 deaths per 100,000 workers", r26 == 0.37, "RIDFATAL Table 1 = %s" % r26)
rf = get(source_table="RIDFATAL Table 1", worker_group="workers", industry_code="F", period_type="5-year average", measure="fatal_injury_rate")
ra = get(source_table="RIDFATAL Table 1", worker_group="workers", industry_code="A-U", period_type="5-year average", measure="fatal_injury_rate")
stated(FAT, 9, "construction ... around 5 times as high as the average rate across all industries",
       4.5 <= rf / ra < 5.5, "RIDFATAL 5-year rates %s / %s = %.2f" % (rf, ra, rf / ra))
mp = get(source_table="RIDFATAL Table 2", industry_code="A-U", year="2025/26p")
stated(FAT, 5, "104 members of the public were also killed in work-related accidents in 2025/26p", mp == 104,
       "RIDFATAL Table 2 = %s" % mp)
fh = get(source_table="RIDFATAL Table 3", worker_group="workers", breakdown="Falls from a height", period_type="5-year total")
tot = get(source_table="RIDFATAL Table 3", worker_group="workers", breakdown="All accident kinds", period_type="5-year total")
stated(FAT, 11, "An average of 37 deaths per year were due to falls from a height, representing 28%",
       round(fh / 5) == 37 and round(100 * fh / tot) == 28, "RIDFATAL Table 3 %s/5 = %.1f; %s/%s = %.1f%%" % (fh, fh / 5, fh, tot, 100 * fh / tot))
period = "2021/22 - 2025/26p"
rk = dict(source_table="Fatalities reportable under RIDDOR (record list), aggregated", industry_code="F", year=period)
cf = get(breakdown="Falls from a height", **rk)
call = sum(r["value"] for r in ALL if r["source_table"] == rk["source_table"] and r["industry_code"] == "F" and r["year"] == period)
stated(FAT, 12, "over half of all deaths in construction over this five-year period ... falls from a height (average of 19 deaths per year)",
       cf / call > 0.5 and round(cf / 5) == 19, "record list %s/%s = %.1f%%; %s/5 = %.1f" % (cf, call, 100 * cf / call, cf, cf / 5))
y05 = get(industry="All industries", year="2005/06", worker_group="workers", measure="fatal_injuries", **hist1)
y81 = get(industry="All industries", year="1981", worker_group="workers", measure="fatal_injuries", **hist1)
stated(FAT, 19, "217 twenty years ago (2005/06) and 495 in 1981", (y05, y81) == (217, 495), "RIDHIST Table 1 = %s, %s" % (y05, y81))

v = get(industry="All industries", year="2025/26p", worker_group="workers", measure="fatal_injuries", **hist1)
stated(SUM, 2, "126 workers killed in work-related accidents in 2025/26", v == 126, "RIDHIST Table 1 = %s" % v)
v = get(source_table="RIDHIST Table 3", industry="All industries", year="2025/26p", worker_group="employees", measure="nonfatal_injuries_total")
stated(SUM, 2, "58,298 employee work-related non-fatal injuries reported by employers in 2025/26", v == 58298,
       "RIDHIST Table 3 = %s" % v)
v = get(source_table="LFSINJSUM Table-1", year="2025/26", measure="incidence")
stated(SUM, 2, "0.7 million workers sustaining a workplace non-fatal injury in 2025/26", round(v / 1000, 1) == 0.7,
       "LFSINJSUM Table-1 = %s thousand" % v)
ia = dict(industry_level="All", year="2025/26", period_type="annual")
p1 = get(source_table="LFSILLIND Table-1", measure="prevalence", **ia)
print('NOTE  %s p.2 headline "1.8 million" workers with work-related ill health is an all-jobs estimate from a workbook not '
      'included here. LFSILLIND "All industries" 2025/26 = %s thousand covers the current or most recent job only '
      '(LFSILLIND Note 0), so it is expected to be lower. Not counted as a check.' % (SUM, p1))
check("LFSILLIND all-industries prevalence is below the all-jobs headline, as its Note 0 scope implies", p1 < 1800, "%s < 1800 thousand" % p1)

# ---------------------------------------------------------------------------
print("\n%d checks, %d failed" % (len(results), results.count(False)))
sys.exit(0 if all(results) else 1)
