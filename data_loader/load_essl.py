"""
load_essl.py – Loads the ESSL punch export CSV/XLS.

Actual format (from uploaded file):
  Row 0 (header):
    Date, Employee Code, Employee Name, Company, Department, Category,
    Degination, Grade, Team, Shift, In Time, Out Time, Duration,
    Late By, Early By, Status, Punch Records, Overtime

  Duration:  H:MM  (e.g. "9:02", "8:33")
  Late By:   H:MM  or "00:00"
  Status:    "Present " | "Absent" | etc.
"""

import os, re
import pandas as pd


# ── Flexible column alias map ─────────────────────────────────────────────────
COLUMN_MAP = {
    "date":       ["date", "attendance date", "attn date"],
    "empcode":    ["employee code", "emp code", "emp_code", "empcode",
                   "employee id", "emp id", "empid", "id", "code"],
    "empname":    ["employee name", "emp name", "name", "emp_name"],
    "in_time":    ["in time", "in_time", "intime", "first in"],
    "out_time":   ["out time", "out_time", "outtime", "last out"],
    "duration":   ["duration", "worked hours", "total hours", "work hours",
                   "total work hours"],
    "late_by":    ["late by", "late_by", "lateby", "late"],
    "early_by":   ["early by", "early_by", "earlyby", "early"],
    "status":     ["status", "attendance status"],
    "punch_rec":  ["punch records", "punch record", "remarks", "punches"],
    "department":  ["department", "dept"],
    "designation": ["degination", "designation", "role"],
}


def _find_col(df_cols, aliases):
    lc = {c.strip().lower(): c for c in df_cols}
    for a in aliases:
        if a in lc:
            return lc[a]
    return None


def _parse_duration(val) -> float:
    """Convert 'H:MM', 'HH:MM', 'HH:MM:SS', float strings → float hours."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return 0.0
    s = str(val).strip()
    if not s or s in ("00:00", "0", "0.0", "--"):
        return 0.0
    # HH:MM:SS
    m = re.match(r"^(\d+):(\d+):(\d+)$", s)
    if m:
        return int(m.group(1)) + int(m.group(2)) / 60 + int(m.group(3)) / 3600
    # H:MM or HH:MM
    m = re.match(r"^(\d+):(\d+)$", s)
    if m:
        return int(m.group(1)) + int(m.group(2)) / 60
    # decimal
    try:
        return float(s)
    except ValueError:
        return 0.0


def _parse_late_minutes(val) -> int:
    """Convert 'H:MM' or 'HH:MM:SS' → integer minutes."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return 0
    s = str(val).strip()
    if not s or s in ("00:00", "0", "--"):
        return 0
    m = re.match(r"^(\d+):(\d+):(\d+)$", s)
    if m:
        return int(m.group(1)) * 60 + int(m.group(2))
    m = re.match(r"^(\d+):(\d+)$", s)
    if m:
        return int(m.group(1)) * 60 + int(m.group(2))
    try:
        return int(float(s))
    except ValueError:
        return 0


def _detect_header_row(df_raw: pd.DataFrame) -> int:
    """
    Find the row index that contains the actual column headers.
    Heuristic: look for a row containing 'date' or 'employee' in any cell.
    """
    for i, row in df_raw.iterrows():
        vals = [str(v).strip().lower() for v in row.fillna("").values]
        if any("date" in v or "employee" in v or "emp code" in v for v in vals):
            return i
    return 0


def load_essl(filepath: str) -> pd.DataFrame:
    """
    Load and normalise the ESSL punch file.

    Returns DataFrame with columns:
      emp_code, emp_name, date (date obj), in_time (str), out_time (str),
      duration_hours (float), late_minutes (int), early_minutes (int),
      status (str), punch_records (str)
    """
    if not os.path.exists(filepath):
        return pd.DataFrame()

    ext = os.path.splitext(filepath)[1].lower()
    try:
        # Read raw first to detect header row
        if ext == ".csv":
            try:
                raw = pd.read_csv(filepath, dtype=str, header=None,
                                  skip_blank_lines=True)
            except UnicodeDecodeError:
                raw = pd.read_csv(filepath, dtype=str, header=None,
                                  encoding="latin-1", skip_blank_lines=True)
        else:
            raw = pd.read_excel(filepath, dtype=str, header=None)
    except Exception as e:
        print(f"[ESSL] Error reading file: {e}")
        return pd.DataFrame()

    raw.dropna(how="all", inplace=True)
    raw.reset_index(drop=True, inplace=True)

    hdr = _detect_header_row(raw)
    # Use header row as column names, data starts below
    df = raw.iloc[hdr + 1:].copy()
    df.columns = [str(c).strip() for c in raw.iloc[hdr].values]
    df.reset_index(drop=True, inplace=True)
    df.dropna(how="all", inplace=True)

    # Map to standard column names
    mapped = {}
    for key, aliases in COLUMN_MAP.items():
        col = _find_col(df.columns, aliases)
        mapped[key] = df[col].astype(str).str.strip() if col else pd.Series(
            [""] * len(df), index=df.index)

    out = pd.DataFrame(index=df.index)
    out["emp_code"]      = mapped["empcode"].str.upper()
    out["emp_name"]      = mapped["empname"].str.strip().str.title()
    out["date_raw"]      = mapped["date"]
    out["in_time"]       = mapped["in_time"]
    out["out_time"]      = mapped["out_time"]
    out["duration_raw"]  = mapped["duration"]
    out["late_raw"]      = mapped["late_by"]
    out["early_raw"]     = mapped["early_by"]
    out["status"]        = mapped["status"].str.strip().str.title()
    out["punch_records"] = mapped["punch_rec"]
    
    # Clean up designation and department
    out["department"] = mapped["department"].str.strip().str.title()
    out["department"] = out["department"].replace({"Nan": "", "None": "", "Null": "", "0": ""})

    out["designation"] = mapped["designation"].str.strip().str.title()
    out["designation"] = out["designation"].replace({"Nan": "", "None": "", "Null": "", "0": ""})

    # Parse date
    out["date"] = pd.to_datetime(out["date_raw"], dayfirst=False,
                                 errors="coerce").dt.date
    out = out[out["date"].notna()].copy()

    # Parse numeric
    out["duration_hours"] = out["duration_raw"].apply(_parse_duration)
    out["late_minutes"]   = out["late_raw"].apply(_parse_late_minutes)
    out["early_minutes"]  = out["early_raw"].apply(_parse_late_minutes)

    out.drop(columns=["date_raw", "duration_raw", "late_raw", "early_raw"],
             inplace=True, errors="ignore")

    # Drop rows without emp_code
    out = out[out["emp_code"].notna() &
              (out["emp_code"] != "") &
              (out["emp_code"].str.upper() != "NAN")].copy()
    out.reset_index(drop=True, inplace=True)
    return out
