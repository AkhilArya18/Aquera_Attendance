"""
load_login.py – Loads the Login-Logout / Muster Roll sheet.

Actual uploaded format (login_logout.xls - Attendance Muster Roll):
  Row 0: Company name
  Row 1: Address
  Row 2: Report title
  Row 3 (header): SNO | Name | Employee No | Department | Designation |
                  Date of Joining | Manager No | Manager Name |
                  Attendance Date | Day | Session1 Status | Session2 Status |
                  In Time [Asia/Kolkata] | Out Time [Asia/Kolkata] |
                  Shift Name | Shift In Time | Shift Out Time | Total Work Hours
  Row 4+: data

Leave codes appear in Session1 Status / Session2 Status columns (EL, CL, etc.)
"""

import os, re
import pandas as pd

LEAVE_CODES = {"el", "cl", "sl", "ml", "pl", "lop", "wfh", "od",
               "leave", "sick", "casual", "earned", "maternity",
               "paternity", "comp off", "co"}

COLUMN_MAP = {
    "empcode":    ["employee no", "employee id", "emp no", "emp id",
                   "empid", "emp code", "employee code", "empcode", "code"],
    "empname":    ["name", "employee name", "emp name"],
    "date":       ["attendance date", "date", "attn date"],
    "login":      ["in time [asia/kolkata]", "in time", "login time",
                   "login", "in_time"],
    "logout":     ["out time [asia/kolkata]", "out time", "logout time",
                   "logout", "out_time"],
    "s1_status":  ["session1  status", "session1 status", "s1 status",
                   "session 1", "session1"],
    "s2_status":  ["session2  status", "session2 status", "s2 status",
                   "session 2", "session2"],
    "leave_type": ["leave type", "leave", "remarks", "status"],
    "work_hours": ["total work hours", "work hours", "worked hours",
                   "total hours", "duration"],
    "department": ["department", "dept"],
    "designation": ["designation"],
    "manager_name": ["manager name", "reporting manager", "manager"],
}


def _find_col(df_cols, aliases):
    """Find a column by alias, normalizing whitespace."""
    import re
    lc = {re.sub(r'\s+', ' ', c.strip().lower()): c for c in df_cols}
    for a in aliases:
        an = re.sub(r'\s+', ' ', a.strip().lower())
        if an in lc:
            return lc[an]
    return None


def _detect_header_row(raw: pd.DataFrame) -> int:
    """Find the row with actual column headers (SNO, Name, Employee No…)."""
    for i, row in raw.iterrows():
        vals = [str(v).strip().lower() for v in row.fillna("").values]
        # Must contain at least one of these marker tokens
        if any(v in ("sno", "name", "employee no", "employee  no",
                     "attendance date", "emp no", "empno") for v in vals):
            return i
    return 0


def _is_leave_code(val) -> str | None:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    s = str(val).strip().upper()
    if s.lower() in LEAVE_CODES:
        return s
    return None


def _parse_duration(val) -> float:
    """'H:MM', 'HH:MM' or 'H : MM' → float hours."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return 0.0
    s = str(val).strip()
    if not s or s in ("00:00", "0", "0.0", "--", "nan"):
        return 0.0
    
    # Normalize: remove spaces around colon
    s = re.sub(r"\s*:\s*", ":", s)
    
    # Match H:MM or H:MM:SS
    m = re.match(r"^(\d+):(\d+)(?::\d+)?$", s)
    if m:
        return int(m.group(1)) + int(m.group(2)) / 60
    
    try:
        return float(s)
    except ValueError:
        return 0.0


def load_login(filepath: str) -> pd.DataFrame:
    """
    Load and normalise the login/logout muster roll file.

    Returns DataFrame with columns:
      emp_code, emp_name, date (date obj), login_time (str),
      logout_time (str), leave_type (str or None), work_hours (float)
    """
    if not os.path.exists(filepath):
        return pd.DataFrame()

    ext = os.path.splitext(filepath)[1].lower()
    try:
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
        print(f"[Login] Error reading file: {e}")
        return pd.DataFrame()

    raw.dropna(how="all", inplace=True)
    raw.reset_index(drop=True, inplace=True)

    hdr = _detect_header_row(raw)
    df = raw.iloc[hdr + 1:].copy()
    df.columns = [str(c).strip() for c in raw.iloc[hdr].values]
    df.reset_index(drop=True, inplace=True)
    df.dropna(how="all", inplace=True)

    # Map standard columns
    mapped = {}
    for key, aliases in COLUMN_MAP.items():
        col = _find_col(df.columns, aliases)
        mapped[key] = df[col].astype(str).str.strip() if col else pd.Series(
            [""] * len(df), index=df.index)

    out = pd.DataFrame(index=df.index)
    out["emp_code"]    = mapped["empcode"].str.upper()
    out["emp_name"]    = mapped["empname"].str.strip().str.title()
    out["date_raw"]    = mapped["date"]
    out["login_time"]  = mapped["login"]
    out["logout_time"] = mapped["logout"]
    out["work_hours"]  = mapped["work_hours"].apply(_parse_duration)
    
    # Clean up fields
    out["department"] = mapped["department"].str.strip().str.title()
    out["department"] = out["department"].replace({"Nan": "", "None": "", "Null": "", "0": ""})
    
    out["designation"] = mapped["designation"].str.strip().str.title()
    out["designation"] = out["designation"].replace({"Nan": "", "None": "", "Null": "", "0": ""})
    
    out["manager_name"] = mapped["manager_name"].str.strip().str.title()
    out["manager_name"] = out["manager_name"].replace({"Nan": "", "None": "", "Null": "", "0": ""})

    # Detect leave from session status columns or explicit leave_type col
    s1 = mapped["s1_status"].apply(_is_leave_code)
    s2 = mapped["s2_status"].apply(_is_leave_code)
    lt = mapped["leave_type"].apply(_is_leave_code)

    out["leave_type"] = s1.combine_first(s2).combine_first(lt)

    # Clean up times that are shift info or 00:00
    def clean_time(t):
        s = str(t).strip()
        if s in ("nan", "", "00 : 00", "00:00"):
            return ""
        # Normalise "HH : MM" → "HH:MM"
        s = re.sub(r"\s*:\s*", ":", s)
        return s

    out["login_time"]  = out["login_time"].apply(clean_time)
    out["logout_time"] = out["logout_time"].apply(clean_time)

    # Parse date — handle datetime strings like "2026-02-16 00:00:00"
    out["date"] = pd.to_datetime(out["date_raw"], errors="coerce").dt.date
    out = out[out["date"].notna()].copy()

    out.drop(columns=["date_raw"], inplace=True, errors="ignore")
    out = out[out["emp_code"].notna() &
              (out["emp_code"] != "") &
              (out["emp_code"].str.upper() != "NAN")].copy()
    out.reset_index(drop=True, inplace=True)
    return out
