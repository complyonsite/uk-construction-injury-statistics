#!/usr/bin/env python3
"""Build the tidy HSE injury dataset from the original files in sources/.

Python 3.9+ standard library only. Usage:

    python3 build.py            # write data/ and charts/
    python3 validate.py         # rebuild in memory, compare, check HSE headline figures

Every output value is copied from one cell of a source spreadsheet, except the
`riddor_fatal_records` rows, which are counts of rows in HSE's record-level
fatality list (see README, Method).
"""
import csv
import io
import json
import re
import zipfile
import xml.etree.ElementTree as ET
from collections import OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "sources"
BASE_URL = "https://www.hse.gov.uk/statistics/assets/docs/"

# Publication dates are as printed inside each source file (cover/contents sheet or PDF title page).
SOURCES = OrderedDict([
    ("ridfatal.xlsx", {"published": "2026-07-01", "title": "RIDFATAL: Work-related fatal injuries reportable under RIDDOR"}),
    ("fatalities-reportable-under-riddor.xlsx", {"published": "2026-07-01", "title": "Fatal injuries reported under RIDDOR, 2021/22 to 2025/26p (record-level list)"}),
    ("ridhist.xlsx", {"published": "2025-11-20", "title": "RIDHIST: Work-related injuries reported under RIDDOR from 1974"}),
    ("ridind.xlsx", {"published": "2025-11-20", "title": "RIDIND: Work-related injuries reported under RIDDOR by detailed industry"}),
    ("ridkind.xlsx", {"published": "2025-11-20", "title": "RIDKIND: Work-related injuries reported under RIDDOR by kind of accident and broad industry group"}),
    ("lfsinjind.xlsx", {"published": "2025-11-20", "title": "LFSINJIND: Self-reported workplace injury by industry"}),
    ("lfsinjsum.xlsx", {"published": "2025-11-20", "title": "LFSINJSUM: Self-reported workplace injuries - summary"}),
    ("lfsillind.xlsx", {"published": "2025-11-20", "title": "LFSILLIND: Self-reported work-related ill health by industry"}),
    ("construction.pdf", {"published": "2025-11-20", "title": "Construction statistics in Great Britain, 2025"}),
    ("fatalinjuries.pdf", {"published": "2026-07-01", "title": "Work-related fatal injuries in Great Britain, 2026"}),
    ("hssh2425.pdf", {"published": "2025-11-20", "title": "Health and safety at work: summary statistics for Great Britain 2025"}),
])

FIELDS = [
    "dataset", "year", "year_status", "provisional", "period_type",
    "industry", "industry_code", "industry_level",
    "breakdown_type", "breakdown", "worker_group",
    "measure", "value", "value_status", "unit", "rate_basis",
    "ci_lower_95", "ci_upper_95", "sample_size_flag",
    "significance_vs_all_industries", "significance_vs_previous_period",
    "source_table", "source_sheet", "source_row", "source_notes",
    "source_url", "source_published",
]

FAMILIES = OrderedDict([
    ("riddor-fatal-injuries-by-industry", "Work-related fatal injuries reported under RIDDOR by industry: workers 1974 to 2025/26p, members of the public 1981 to 2025/26p"),
    ("riddor-fatal-injuries-by-kind", "Work-related fatal injuries to workers reported under RIDDOR by kind of accident and industry, 2014/15 to 2025/26p"),
    ("riddor-nonfatal-injuries-by-industry", "Non-fatal injuries reported by employers under RIDDOR by industry, 1974 to 2024/25p"),
    ("riddor-nonfatal-injuries-by-kind", "Non-fatal injuries to employees reported under RIDDOR by kind of accident and industry, 2014/15 to 2024/25p"),
    ("lfs-self-reported-injury", "Labour Force Survey self-reported workplace non-fatal injury, all industries (annual) and by industry (3- and 5-year averages)"),
    ("lfs-self-reported-ill-health", "Labour Force Survey self-reported work-related ill health by industry, annual and 3- and 5-year averages"),
])

# ---------------------------------------------------------------------------
# Minimal .xlsx reader


_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_RID = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"


def _col(ref):
    n = 0
    for ch in re.match(r"[A-Z]+", ref).group(0):
        n = n * 26 + ord(ch) - 64
    return n - 1


def read_xlsx(path):
    """Return {sheet name: list of rows}, each row a list of cell values (None, str, int or float)."""
    z = zipfile.ZipFile(path)
    shared = []
    if "xl/sharedStrings.xml" in z.namelist():
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall(_NS + "si"):
            shared.append("".join(t.text or "" for t in si.iter(_NS + "t")))
    rels = {r.get("Id"): r.get("Target") for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))}
    book = ET.fromstring(z.read("xl/workbook.xml"))
    out = OrderedDict()
    for sh in book.find(_NS + "sheets"):
        target = rels[sh.get(_RID)].lstrip("/")
        if not target.startswith("xl/"):
            target = "xl/" + target
        rows = []
        for row in ET.fromstring(z.read(target)).iter(_NS + "row"):
            r = int(row.get("r")) - 1
            while len(rows) <= r:
                rows.append([])
            cells = rows[r]
            for c in row.findall(_NS + "c"):
                i = _col(c.get("r"))
                t = c.get("t")
                v = c.find(_NS + "v")
                if t == "s" and v is not None:
                    val = shared[int(v.text)]
                elif t == "inlineStr":
                    val = "".join(x.text or "" for x in c.iter(_NS + "t"))
                elif v is None:
                    val = None
                elif t in ("str", "e"):
                    val = v.text
                elif t == "b":
                    val = v.text == "1"
                else:
                    f = float(v.text)
                    val = int(f) if f.is_integer() else f
                while len(cells) <= i:
                    cells.append(None)
                cells[i] = val
        out[sh.get("name")] = rows
    return out


def cell(row, i):
    return row[i] if i < len(row) else None


# ---------------------------------------------------------------------------
# Helpers

NOTE_RE = re.compile(r"\[Note [^\]]*\]")


def clean(label):
    """Strip '[Note n]' references from a label. Returns (clean text, 'Note n; Note m')."""
    if label is None:
        return "", ""
    s = str(label)
    notes = [n[1:-1] for n in NOTE_RE.findall(s)]
    s = NOTE_RE.sub("", s).replace("\n", " ")
    s = re.sub(r"\s*,\s*$", "", re.sub(r"\s+", " ", s)).strip()
    s = re.sub(r"(\s*,)+$", "", s).strip()
    return s, "; ".join(notes)


def year_status(label):
    if re.search(r"\d{2}p$", label):
        return "provisional"
    if re.search(r"\d{2}r$", label):
        return "revised"
    return "final"


def put_value(rec, v):
    """Copy a source cell into value/value_status without changing it."""
    if isinstance(v, bool):
        raise ValueError("unexpected boolean cell")
    if isinstance(v, (int, float)):
        rec["value"] = v
        rec["value_status"] = ""
    elif v is None or (isinstance(v, str) and v.strip() == ""):
        rec["value"] = None
        rec["value_status"] = "blank in source"
    else:
        s = str(v).strip()
        if re.fullmatch(r"\[[A-Za-z0-9]+\]", s):
            rec["value"] = None
            rec["value_status"] = s
        else:
            raise ValueError("non-numeric value %r" % (v,))


def num_or_none(v):
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return v
    return None


def base(dataset, src, sheet, row_index, **kw):
    rec = OrderedDict((f, None) for f in FIELDS)
    rec.update(
        dataset=dataset,
        source_table=src.split(".")[0].upper() + " " + sheet,
        source_sheet=sheet,
        source_row=row_index + 1 if row_index is not None else None,  # 1-based spreadsheet row
        source_url=BASE_URL + src,
        source_published=SOURCES[src]["published"],
    )
    for k, v in kw.items():
        rec[k] = v
    return rec


def finalise(rec):
    if rec.get("year") is not None and rec.get("year_status") is None:
        rec["year_status"] = year_status(rec["year"])
    rec["provisional"] = rec["year_status"] == "provisional"
    for k in ("value_status", "source_notes", "breakdown_type", "breakdown", "industry_code",
              "industry_level", "rate_basis", "sample_size_flag", "significance_vs_all_industries",
              "significance_vs_previous_period"):
        if rec[k] is None:
            rec[k] = ""
    return rec


def code_text(table):
    """Map '(a)'..'(o)' codes from RIDHIST 'Background information' to readable text."""
    out = {}
    section = None
    for r in table:
        a = cell(r, 0)
        if isinstance(a, str) and a.startswith("Table "):
            section = a[:7]
            continue
        if isinstance(a, str) and re.fullmatch(r"\(\s*[a-z]\s*\)", a.strip()):
            key = re.sub(r"\s", "", a)
            period = cell(r, 1)
            text = cell(r, 2)
            if section == "Table A":
                out[key] = "Regulations %s: %s" % (period, str(text).strip().rstrip("."))
            elif section == "Table B":
                out[key] = "Industry classification %s: %s" % (period, text)
            elif section == "Table D":
                out[key] = "Employment data for rates %s: %s" % (period, str(text).split(".")[0])
    return out


def header_index(rows, startswith):
    for i, r in enumerate(rows):
        a = cell(r, 0)
        if isinstance(a, str) and a.startswith(startswith):
            return i
    raise ValueError("header not found: " + startswith)


# ---------------------------------------------------------------------------
# RIDDOR fatal injuries by industry

FATAL_COLS = [  # (column offset from first count column, worker_group, measure, unit, rate_basis)
    (0, "workers", "fatal_injuries", "count", ""),
    (1, "employees", "fatal_injuries", "count", ""),
    (2, "self-employed", "fatal_injuries", "count", ""),
    (3, "workers", "fatal_injury_rate", "rate", "per 100,000 workers"),
    (4, "employees", "fatal_injury_rate", "rate", "per 100,000 employees"),
    (5, "self-employed", "fatal_injury_rate", "rate", "per 100,000 self-employed"),
]


def ridfatal_industry_level(code):
    if code in ("A-U",):
        return "All"
    if code == "Z":
        return "Missing industry"
    if code == "E38":
        return "Division"
    if code in ("G,I", "J-N", "O-Q", "R-U"):
        return "Section group"
    return "Section"


def fatal_by_industry(wb):
    out = []
    ds = "riddor-fatal-injuries-by-industry"

    # RIDHIST Table 1: workers, broad industry group, 1974 to 2024/25p
    hist = wb["ridhist.xlsx"]
    codes = code_text(hist["Background information"])
    t = hist["Table 1"]
    h = header_index(t, "Year")
    for i in range(h + 1, len(t)):
        r = t[i]
        if cell(r, 0) is None:
            continue
        year, n1 = clean(cell(r, 0))
        ind, n2 = clean(cell(r, 1))
        notes = [n for n in (n1, n2) if n]
        notes += [codes.get(re.sub(r"\s", "", str(cell(r, k))), "") for k in (2, 3, 4)]
        for off, grp, meas, unit, basis in FATAL_COLS:
            rec = base(ds, "ridhist.xlsx", "Table 1", i, year=year, period_type="annual",
                       industry=ind, industry_level="All" if ind == "All industries" else "Broad industry group",
                       worker_group=grp, measure=meas, unit=unit, rate_basis=basis,
                       source_notes="; ".join(n for n in notes if n))
            put_value(rec, cell(r, 5 + off))
            out.append(finalise(rec))

    # RIDHIST Table 2: members of the public, wide table (one column per broad group)
    t = hist["Table 2"]
    h = header_index(t, "Year")
    heads = t[h]
    for i in range(h + 1, len(t)):
        r = t[i]
        if cell(r, 0) is None:
            continue
        year, n1 = clean(cell(r, 0))
        reg = [codes.get(re.sub(r"\s", "", str(cell(r, k))), "") for k in (1, 2)]
        for j in range(3, len(heads)):
            if heads[j] is None:
                continue
            ind, n2 = clean(heads[j])
            if ind.startswith("Number of fatal injuries to members of the public across all industries"):
                ind = "All industries"
            notes = [n for n in (n1, n2) if n] + reg
            rec = base(ds, "ridhist.xlsx", "Table 2", i, year=year, period_type="annual",
                       industry=ind, industry_level="All" if ind == "All industries" else "Broad industry group",
                       worker_group="members of the public", measure="fatal_injuries", unit="count",
                       source_notes="; ".join(n for n in notes if n))
            put_value(rec, cell(r, j))
            out.append(finalise(rec))

    # RIDIND Table 1: workers, SIC section and division, 2014/15 to 2024/25p
    t = wb["ridind.xlsx"]["Table 1"]
    h = header_index(t, "Year")
    for i in range(h + 1, len(t)):
        r = t[i]
        if cell(r, 0) is None:
            continue
        year, n1 = clean(cell(r, 0))
        ind, n2 = clean(cell(r, 3))
        for off, grp, meas, unit, basis in FATAL_COLS:
            rec = base(ds, "ridind.xlsx", "Table 1", i, year=year, period_type="annual",
                       industry=ind, industry_code=str(cell(r, 2)).strip(), industry_level=str(cell(r, 1)).strip(),
                       worker_group=grp, measure=meas, unit=unit, rate_basis=basis,
                       source_notes="; ".join(n for n in (n1, n2) if n))
            put_value(rec, cell(r, 4 + off))
            out.append(finalise(rec))

    # RIDFATAL Table 1: workers, main industry, 2021/22 to 2025/26p and 5-year total
    t = wb["ridfatal.xlsx"]["Table 1"]
    h = header_index(t, "Year")
    for i in range(h + 1, len(t)):
        r = t[i]
        if cell(r, 0) is None:
            continue
        year, n1 = clean(cell(r, 0))
        ind, n2 = clean(cell(r, 2))
        code = "A-U" if cell(r, 1) == 0 else str(cell(r, 1))
        five = " - " in year
        for off, grp, meas, unit, basis in FATAL_COLS:
            ptype = "annual"
            if five:
                ptype = "5-year total" if unit == "count" else "5-year average"
            rec = base(ds, "ridfatal.xlsx", "Table 1", i, year=year, period_type=ptype,
                       year_status="provisional" if five else None,
                       industry=ind, industry_code=code, industry_level=ridfatal_industry_level(code),
                       worker_group=grp, measure=meas, unit=unit, rate_basis=basis,
                       source_notes="; ".join(n for n in (n1, n2) if n))
            put_value(rec, cell(r, 3 + off))
            out.append(finalise(rec))

    # RIDFATAL Table 2: members of the public, wide by year
    t = wb["ridfatal.xlsx"]["Table 2"]
    h = header_index(t, "Main Industry")
    heads = t[h]
    for i in range(h + 1, len(t)):
        r = t[i]
        if cell(r, 0) is None:
            continue
        ind, n1 = clean(cell(r, 0))
        m = re.search(r"\(SIC ([^)]+)\)", ind)
        code = "A-U" if ind.startswith("All industries") else (m.group(1) if m else "")
        if code == "38":
            code = "E38"
        for j in range(1, len(heads)):
            if heads[j] is None:
                continue
            year, n2 = clean(heads[j])
            rec = base(ds, "ridfatal.xlsx", "Table 2", i, year=year, period_type="annual",
                       industry=ind, industry_code=code, industry_level=ridfatal_industry_level(code) if code else "",
                       worker_group="members of the public", measure="fatal_injuries", unit="count",
                       source_notes="; ".join(n for n in (n1, n2) if n) + "; column %d" % (j + 1))
            put_value(rec, cell(r, j))
            out.append(finalise(rec))
    return out


# ---------------------------------------------------------------------------
# RIDDOR fatal injuries by kind of accident

def fatal_by_kind(wb):
    out = []
    ds = "riddor-fatal-injuries-by-kind"
    groups = [(0, "workers"), (1, "employees"), (2, "self-employed")]

    t = wb["ridkind.xlsx"]["Table 1"]
    h = header_index(t, "Year")
    for i in range(h + 1, len(t)):
        r = t[i]
        if cell(r, 0) is None:
            continue
        year, n1 = clean(cell(r, 0))
        ind, n2 = clean(cell(r, 2))
        code = str(cell(r, 1)).strip()
        kind, n3 = clean(cell(r, 3))
        for off, grp in groups:
            rec = base(ds, "ridkind.xlsx", "Table 1", i, year=year, period_type="annual",
                       industry=ind, industry_code=code, industry_level="All" if code == "A-U" else "Section",
                       breakdown_type="kind of accident", breakdown=kind, worker_group=grp,
                       measure="fatal_injuries", unit="count",
                       source_notes="; ".join(n for n in (n1, n2, n3) if n))
            put_value(rec, cell(r, 4 + off))
            out.append(finalise(rec))

    t = wb["ridfatal.xlsx"]["Table 3"]
    h = header_index(t, "Year")
    for i in range(h + 1, len(t)):
        r = t[i]
        if cell(r, 0) is None:
            continue
        year, n1 = clean(cell(r, 0))
        kind, _ = clean(cell(r, 2))
        five = " - " in year
        for off, grp in groups:
            rec = base(ds, "ridfatal.xlsx", "Table 3", i, year=year,
                       period_type="5-year total" if five else "annual",
                       year_status="provisional" if five else None,
                       industry="All industries", industry_code="A-U", industry_level="All",
                       breakdown_type="kind of accident", breakdown=kind, worker_group=grp,
                       measure="fatal_injuries", unit="count", source_notes=n1)
            put_value(rec, cell(r, 3 + off))
            out.append(finalise(rec))

    out.extend(fatal_records_by_kind(wb))
    return out


RECORD_SHEET = "Fatals 2122 to 2526p"


def fatal_records(wb):
    t = wb["fatalities-reportable-under-riddor.xlsx"][RECORD_SHEET]
    h = header_index(t, "Enforcing authority")
    head = [clean(c)[0] for c in t[h]]
    idx = {name: head.index(name) for name in ("Year", "Employment Status - overview", "Kind of accident", "Top-level Industry (SIC section)")}
    recs = []
    for i in range(h + 1, len(t)):
        r = t[i]
        if cell(r, 0) is None:
            continue
        recs.append({
            "row": i + 1,
            "year": str(cell(r, idx["Year"])).strip(),
            "group": str(cell(r, idx["Employment Status - overview"])).strip(),
            "kind": str(cell(r, idx["Kind of accident"])).strip(),
            "section": str(cell(r, idx["Top-level Industry (SIC section)"])).strip(),
        })
    return recs


def fatal_records_by_kind(wb):
    """Count worker records by year x SIC section x kind of accident.

    The record list holds one row per death, so a combination with no rows is a count of 0.
    Every year, section and kind that occurs anywhere in the list is enumerated.
    """
    ds = "riddor-fatal-injuries-by-kind"
    src = "fatalities-reportable-under-riddor.xlsx"
    recs = [r for r in fatal_records(wb) if r["group"] == "Workers"]
    years = sorted({r["year"] for r in recs})
    sections = sorted({r["section"] for r in recs})
    kinds = sorted({r["kind"] for r in recs})
    period = "%s - %s" % (years[0], years[-1])
    out = []
    for year in years + [period]:
        for sec in sections:
            code = sec.split(" - ")[0].strip()
            name = sec.split(" - ", 1)[1].strip() if " - " in sec else sec
            for kind in kinds:
                rows = [r["row"] for r in recs if r["section"] == sec and r["kind"] == kind and (year == period or r["year"] == year)]
                rec = base(ds, src, RECORD_SHEET, None, year=year,
                           period_type="5-year total" if year == period else "annual",
                           year_status="provisional" if year == period else None,
                           industry=name, industry_code=code,
                           industry_level="Missing industry" if code == "Z" else "Section",
                           breakdown_type="kind of accident", breakdown=kind, worker_group="workers",
                           measure="fatal_injuries", unit="count",
                           source_notes="Derived: count of rows where Employment Status - overview = Workers, Year %s, "
                                        "Top-level Industry = '%s', Kind of accident = '%s'%s" % (
                                            "in " + period if year == period else "= " + year, sec, kind,
                                            ("; spreadsheet rows " + ",".join(str(x) for x in rows)) if rows else ""))
                rec["value"] = len(rows)
                rec["value_status"] = ""
                rec["source_table"] = "Fatalities reportable under RIDDOR (record list), aggregated"
                out.append(finalise(rec))
    return out


# ---------------------------------------------------------------------------
# RIDDOR non-fatal injuries

def nonfatal_by_industry(wb):
    out = []
    ds = "riddor-nonfatal-injuries-by-industry"
    hist = wb["ridhist.xlsx"]
    codes = code_text(hist["Background information"])
    t = hist["Table 3"]
    h = header_index(t, "Employment status")
    cols = [
        (6, "nonfatal_injuries_total", "count", ""),
        (7, "major_or_specified_injuries", "count", ""),
        (8, "over_3_day_injuries", "count", ""),
        (9, "over_7_day_injuries", "count", ""),
        (10, "nonfatal_injury_rate_total", "rate", "per 100,000 employees"),
        (11, "major_or_specified_injury_rate", "rate", "per 100,000 employees"),
        (12, "over_3_day_injury_rate", "rate", "per 100,000 employees"),
        (13, "over_7_day_injury_rate", "rate", "per 100,000 employees"),
    ]
    for i in range(h + 1, len(t)):
        r = t[i]
        if cell(r, 0) is None:
            continue
        grp = {"Employee": "employees", "Self-employed": "self-employed"}[str(cell(r, 0)).strip()]
        year, n1 = clean(cell(r, 1))
        ind, n2 = clean(cell(r, 2))
        notes = [n for n in (n1, n2) if n] + [codes.get(re.sub(r"\s", "", str(cell(r, k))), "") for k in (3, 4, 5)]
        for j, meas, unit, basis in cols:
            rec = base(ds, "ridhist.xlsx", "Table 3", i, year=year, period_type="annual",
                       industry=ind, industry_level="All" if ind == "All industries" else "Broad industry group",
                       worker_group=grp, measure=meas, unit=unit,
                       rate_basis=(basis.replace("employees", "self-employed") if grp == "self-employed" and basis else basis),
                       source_notes="; ".join(n for n in notes if n))
            put_value(rec, cell(r, j))
            out.append(finalise(rec))

    t = wb["ridind.xlsx"]["Table 3"]
    h = header_index(t, "Year")
    cols = [
        (4, "nonfatal_injuries_total", "count", ""),
        (5, "major_or_specified_injuries", "count", ""),
        (6, "over_7_day_injuries", "count", ""),
        (7, "nonfatal_injury_rate_total", "rate", "per 100,000 employees"),
        (8, "major_or_specified_injury_rate", "rate", "per 100,000 employees"),
        (9, "over_7_day_injury_rate", "rate", "per 100,000 employees"),
    ]
    for i in range(h + 1, len(t)):
        r = t[i]
        if cell(r, 0) is None:
            continue
        year, n1 = clean(cell(r, 0))
        ind, n2 = clean(cell(r, 3))
        for j, meas, unit, basis in cols:
            rec = base(ds, "ridind.xlsx", "Table 3", i, year=year, period_type="annual",
                       industry=ind, industry_code=str(cell(r, 2)).strip(), industry_level=str(cell(r, 1)).strip(),
                       worker_group="employees", measure=meas, unit=unit, rate_basis=basis,
                       source_notes="; ".join(n for n in (n1, n2) if n))
            put_value(rec, cell(r, j))
            out.append(finalise(rec))
    return out


def nonfatal_by_kind(wb):
    out = []
    ds = "riddor-nonfatal-injuries-by-kind"
    t = wb["ridkind.xlsx"]["Table 2"]
    h = header_index(t, "Year")
    cols = [(4, "nonfatal_injuries_total"), (5, "major_or_specified_injuries"), (6, "over_7_day_injuries")]
    for i in range(h + 1, len(t)):
        r = t[i]
        if cell(r, 0) is None:
            continue
        year, n1 = clean(cell(r, 0))
        ind, n2 = clean(cell(r, 2))
        code = str(cell(r, 1)).strip()
        kind, _ = clean(cell(r, 3))
        for j, meas in cols:
            rec = base(ds, "ridkind.xlsx", "Table 2", i, year=year, period_type="annual",
                       industry=ind, industry_code=code, industry_level="All" if code == "A-U" else "Section",
                       breakdown_type="kind of accident", breakdown=kind, worker_group="employees",
                       measure=meas, unit="count", source_notes="; ".join(n for n in (n1, n2) if n))
            put_value(rec, cell(r, j))
            out.append(finalise(rec))
    return out


# ---------------------------------------------------------------------------
# Labour Force Survey

LFS_LEVELS = ("All", "Section", "Division")

SAMPLE_FLAGS = {
    "Note 12": "low sample: 20-29 cases (HSE Note 12)",
    "Note 13": "low sample: 20-39 cases (HSE Note 13)",
}


def lfs_period_type(period):
    p = str(period).strip().lower()
    return {"annual": "annual", "3 year": "3-year annual average", "5 year": "5-year annual average"}[p]


def lfs_pairs(head):
    """Return [(estimate col, lower col, upper col, measure, unit, rate_basis)] from a header row."""
    names = [clean(c)[0] for c in head]
    pairs = []
    for j, n in enumerate(names):
        if not n.endswith(": Estimate"):
            continue
        stem = n[: -len(": Estimate")]
        lo, hi = j + 1, j + 2
        if stem in ("Incidence (000s)", "Incidence"):
            pairs.append((j, lo, hi, "incidence", "thousand workers", ""))
        elif stem == "Incidence rate per 100,000":
            pairs.append((j, lo, hi, "incidence_rate", "rate", "per 100,000 workers"))
        elif stem == "Prevalence rate per 100,000":
            pairs.append((j, lo, hi, "prevalence_rate", "rate", "per 100,000 workers"))
        elif stem == "Days lost per worker":
            pairs.append((j, lo, hi, "days_lost_per_worker", "days", "per full-time equivalent worker"))
        elif stem == "Days lost per case":
            pairs.append((j, lo, hi, "days_lost_per_case", "days", "per case"))
        else:
            raise ValueError("unknown LFS column " + n)
    # count columns are labelled 'Incidence: Estimate (000s)' etc.
    for j, n in enumerate(names):
        m = re.match(r"^(Incidence|Prevalence|Days lost): Estimate \(000s\)$", n)
        if m:
            meas = {"Incidence": "incidence", "Prevalence": "prevalence", "Days lost": "days_lost"}[m.group(1)]
            unit = "thousand full-day equivalents" if meas == "days_lost" else "thousand workers"
            pairs.append((j, j + 1, j + 2, meas, unit, ""))
    pairs.sort()
    return pairs, names


def lfs_rows(wb, src, sheet, ds, breakdown_type, breakdown, by_industry):
    t = wb[src][sheet]
    h = header_index(t, "Sort key")
    pairs, names = lfs_pairs(t[h])
    title, _ = clean(cell(t[0], 0))
    sig_all = names.index("Statistical significance vs All") if "Statistical significance vs All" in names else None
    sig_prev = names.index("Statistical significance vs Previous year")
    flag = names.index("Sample size flag")
    out = []
    for i in range(h + 1, len(t)):
        r = t[i]
        if cell(r, 0) is None:
            continue
        level = str(cell(r, 3)).strip()
        if level not in LFS_LEVELS:
            continue
        year, n1 = clean(cell(r, 2))
        scope = ""
        if by_industry:
            scope = "Scope (HSE Note 0): cases in the current or most recent job only, so totals are lower than HSE headline all-jobs estimates"
            ind, n2 = clean(cell(r, 5))
            code = str(cell(r, 6)).strip()
            bd = breakdown
        else:
            ind, n2, code = "All industries", "", "All"
            bd, _ = clean(cell(r, 4))
        for j, lo, hi, meas, unit, basis in pairs:
            rec = base(ds, src, sheet, i, year=year, year_status="survey estimate", period_type=lfs_period_type(cell(r, 1)),
                       industry=ind, industry_code=code, industry_level=level,
                       breakdown_type=breakdown_type, breakdown=bd, worker_group="workers",
                       measure=meas, unit=unit, rate_basis=basis,
                       sample_size_flag=SAMPLE_FLAGS[clean(cell(r, flag))[1]] if cell(r, flag) else "",
                       significance_vs_all_industries=str(cell(r, sig_all)) if sig_all is not None and cell(r, sig_all) is not None else "",
                       significance_vs_previous_period=str(cell(r, sig_prev)) if cell(r, sig_prev) is not None else "",
                       source_notes="; ".join(n for n in (n1, n2, scope) if n))
            put_value(rec, cell(r, j))
            rec["ci_lower_95"] = num_or_none(cell(r, lo))
            rec["ci_upper_95"] = num_or_none(cell(r, hi))
            rec["source_table"] = src.split(".")[0].upper() + " " + sheet
            out.append(finalise(rec))
    return out


INJURY_CATEGORY = {
    "Table-1": "All workplace injuries",
    "Table-2": "Workplace injuries with over three day absence",
    "Table-3": "Workplace injuries with over seven day absence",
    "Table-4": "All workplace injuries",
}

ILLNESS_CONDITION = {
    "Table-1": "All work-related illness",
    "Table-2": "Musculoskeletal disorders",
    "Table-3": "Musculoskeletal disorders mainly affecting the upper limbs or neck",
    "Table-4": "Musculoskeletal disorders mainly affecting the back",
    "Table-5": "Stress, depression or anxiety",
    "Table-6": "All work-related illness",
    "Table-7": "Musculoskeletal disorders",
    "Table-8": "Stress, depression or anxiety",
    "Table-9": "All work-related illness",
    "Table-10": "Musculoskeletal disorders",
    "Table-11": "Stress, depression or anxiety",
}


def lfs_injury(wb):
    ds = "lfs-self-reported-injury"
    out = []
    for sheet in ("Table-1", "Table-2", "Table-3", "Table-4", "Table-5"):
        out += lfs_rows(wb, "lfsinjsum.xlsx", sheet, ds, "injury category", None, by_industry=False)
    for sheet, cat in INJURY_CATEGORY.items():
        out += lfs_rows(wb, "lfsinjind.xlsx", sheet, ds, "injury category", cat, by_industry=True)
    return out


def lfs_ill_health(wb):
    ds = "lfs-self-reported-ill-health"
    out = []
    for sheet, cond in ILLNESS_CONDITION.items():
        out += lfs_rows(wb, "lfsillind.xlsx", sheet, ds, "condition", cond, by_industry=True)
    return out


# ---------------------------------------------------------------------------
# Construction filter and charts

def is_construction(rec):
    code = rec["industry_code"]
    if rec["industry"] == "Construction" or code in ("F", "F (41-43)"):
        return True
    if rec["industry_level"] == "Division" and code in ("41", "42", "43", "41,43"):
        return True
    return False


def build_tables(src_dir=SRC):
    wb = {name: read_xlsx(src_dir / name) for name in SOURCES if name.endswith(".xlsx")}
    tables = OrderedDict()
    tables["riddor-fatal-injuries-by-industry"] = fatal_by_industry(wb)
    tables["riddor-fatal-injuries-by-kind"] = fatal_by_kind(wb)
    tables["riddor-nonfatal-injuries-by-industry"] = nonfatal_by_industry(wb)
    tables["riddor-nonfatal-injuries-by-kind"] = nonfatal_by_kind(wb)
    tables["lfs-self-reported-injury"] = lfs_injury(wb)
    tables["lfs-self-reported-ill-health"] = lfs_ill_health(wb)
    construction = [r for rows in tables.values() for r in rows if is_construction(r)]
    return wb, tables, construction


def pick(rows, **kw):
    return [r for r in rows if all(r[k] == v for k, v in kw.items())]


def one(rows, **kw):
    found = pick(rows, **kw)
    if len(found) != 1:
        raise ValueError("expected one row for %r, found %d" % (kw, len(found)))
    return found[0]


def year_start(label):
    return int(re.match(r"\d{4}", label).group(0))


def charts(tables):
    """Return {filename: (header, rows)} for the Datawrapper CSVs."""
    out = OrderedDict()
    fatal = tables["riddor-fatal-injuries-by-industry"]

    # 1. Construction worker fatalities 1981 to 2025/26p.
    # RIDFATAL (July 2026) for 2021/22 onwards; RIDHIST (November 2025) for 1981 to 2020/21.
    rows = []
    ridfatal = {r["year"]: r for r in pick(fatal, source_sheet="Table 1", industry_code="F", worker_group="workers",
                                             measure="fatal_injuries", period_type="annual")
                if r["source_url"].endswith("ridfatal.xlsx")}
    ridfatal_rate = {r["year"]: r for r in pick(fatal, source_sheet="Table 1", industry_code="F", worker_group="workers",
                                                  measure="fatal_injury_rate", period_type="annual")
                     if r["source_url"].endswith("ridfatal.xlsx")}
    first_fatal = min(year_start(y) for y in ridfatal)
    for r in pick(fatal, source_table="RIDHIST Table 1", industry="Construction", worker_group="workers", measure="fatal_injuries"):
        y = year_start(r["year"])
        if y < 1981 or y >= first_fatal:
            continue
        rate = one(fatal, source_table="RIDHIST Table 1", industry="Construction", worker_group="workers",
                   measure="fatal_injury_rate", year=r["year"])
        rows.append([r["year"], r["value"], rate["value"], "RIDHIST Table 1"])
    for y in sorted(ridfatal, key=year_start):
        rows.append([y, ridfatal[y]["value"], ridfatal_rate[y]["value"], "RIDFATAL Table 1"])
    out["construction-worker-fatalities-1981-to-2025-26.csv"] = (
        ["Year", "Construction workers killed", "Rate per 100,000 construction workers", "Source table"], rows)

    # 2. Construction fatal injuries by kind of accident, 2021/22 to 2025/26p (counts of HSE records).
    kind = tables["riddor-fatal-injuries-by-kind"]
    rec = [r for r in kind if r["source_table"].startswith("Fatalities reportable") and r["industry_code"] == "F"]
    period = [r for r in rec if r["period_type"] == "5-year total"]
    latest_year = max((r["year"] for r in rec if r["period_type"] == "annual"), key=year_start)
    rows = []
    for r in sorted((p for p in period if p["value"] > 0), key=lambda x: (-x["value"], x["breakdown"])):
        latest = one(rec, period_type="annual", year=latest_year, breakdown=r["breakdown"])
        rows.append([r["breakdown"], r["value"], latest["value"]])
    out["construction-fatal-injuries-by-kind-2021-22-to-2025-26.csv"] = (
        ["Kind of accident", "Construction workers killed, %s (5-year total)" % period[0]["year"],
         "Construction workers killed, %s" % latest_year], rows)

    # 3. LFS self-reported non-fatal injury rate, construction vs all industries, 3-year averages.
    lfs = tables["lfs-self-reported-injury"]
    sel = dict(source_table="LFSINJIND Table-1", measure="incidence_rate", period_type="3-year annual average")
    rows = []
    for r in sorted(pick(lfs, industry_code="F", industry_level="Section", **sel), key=lambda x: year_start(x["year"])):
        a = one(lfs, industry_level="All", year=r["year"], **sel)
        rows.append([r["year"], r["value"], r["ci_lower_95"], r["ci_upper_95"], a["value"], a["ci_lower_95"], a["ci_upper_95"]])
    out["construction-vs-all-industries-self-reported-injury-rate.csv"] = (
        ["Period (3-year average)", "Construction", "Construction 95% CI lower", "Construction 95% CI upper",
         "All industries", "All industries 95% CI lower", "All industries 95% CI upper"], rows)
    return out


# ---------------------------------------------------------------------------
# Serialisation

def fmt(v):
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float):
        return repr(v)
    return str(v)


def to_csv(header, rows):
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    for r in rows:
        w.writerow([fmt(v) for v in r])
    return buf.getvalue()


def records_csv(records):
    return to_csv(FIELDS, [[r[f] for f in FIELDS] for r in records])


def records_json(name, title, records):
    srcs = sorted({r["source_url"] for r in records})
    meta = OrderedDict([
        ("name", name),
        ("title", title),
        ("publisher", "ComplyOnSite"),
        ("homepage", "https://complyonsite.com/"),
        ("source", "Health and Safety Executive (HSE), https://www.hse.gov.uk/statistics/"),
        ("source_files", srcs),
        ("licence", "Open Government Licence v3.0"),
        ("licence_url", "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/"),
        ("attribution", "Contains public sector information published by the Health and Safety Executive and licensed under the Open Government Licence."),
        ("fields", FIELDS),
        ("record_count", len(records)),
    ])
    # One record per line keeps the files compact and diff-friendly while remaining a single JSON document.
    head = json.dumps(OrderedDict([("metadata", meta)]), ensure_ascii=False, indent=1)[:-2]
    body = ",\n".join(json.dumps(r, ensure_ascii=False, separators=(",", ":")) for r in records)
    return head + ',\n "records": [\n' + body + "\n ]\n}\n"


def render(tables, construction):
    """Return {relative path: text} for every generated file."""
    files = OrderedDict()
    for name, rows in tables.items():
        files["data/%s.csv" % name] = records_csv(rows)
        files["data/%s.json" % name] = records_json(name, FAMILIES[name], rows)
    name = "construction-only"
    title = "All construction rows from the six table families: SIC 2007 section F, divisions 41, 42, 43 (and RIDIND's combined '41,43'), and RIDHIST's broad group 'Construction'"
    files["data/%s.csv" % name] = records_csv(construction)
    files["data/%s.json" % name] = records_json(name, title, construction)
    for fname, (header, rows) in charts(tables).items():
        files["charts/" + fname] = to_csv(header, rows)
    return files


def main():
    _, tables, construction = build_tables()
    files = render(tables, construction)
    for rel, text in files.items():
        p = ROOT / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    for rel, text in files.items():
        print("%-75s %7d rows" % (rel, text.count("\n") - 1 if rel.endswith(".csv") else json.loads(text)["metadata"]["record_count"]))


if __name__ == "__main__":
    main()
