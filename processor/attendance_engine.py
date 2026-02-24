"""
attendance_engine.py – Merges ESSL and Login-Logout data, applies attendance
rules and computes per-employee daily + summary records.
"""

import pandas as pd
from datetime import date, timedelta
import config


def _working_days_back(n: int, from_date: date = None) -> list:
    if from_date is None:
        from_date = date.today()
    days = []
    d = from_date
    while len(days) < n:
        days.append(d)
        d -= timedelta(days=1)
    return sorted(days)


def _fmt_hours(h: float) -> str:
    """Convert float hours → 'H:MM' string."""
    if not h or h <= 0:
        return "—"
    hrs = int(h)
    mins = int(round((h - hrs) * 60))
    return f"{hrs}:{mins:02d}"


def classify_day(row: dict, shifts: dict) -> str:
    raw_punches = str(row.get("punch_records", "")).strip()
    has_essl = raw_punches != "" and raw_punches.lower() != "nan"
    has_login = pd.notna(row.get("login_time")) and row.get("login_time") != ""
    work_hrs = float(row.get("work_hours", 0))
    dur_h = float(row.get("duration_hours", 0) or 0)
    
    in_time_str = str(row.get("in_time", "")).strip()
    emp_code = str(row.get("emp_code", "")).upper()
    dept = str(row.get("department", "")).upper()

    # Determine shift start time
    shift_start_str = shifts.get("global", config.OFFICE_START_TIME)
    if dept in shifts.get("departments", {}):
        shift_start_str = shifts.get("departments")[dept]
    if emp_code in shifts.get("employees", {}):
        shift_start_str = shifts.get("employees")[emp_code]

    # Calculate late minutes if we have an in_time
    late_m = 0
    if in_time_str and in_time_str != "nan":
        try:
            # Parse in_time HH:MM
            h_in, m_in = map(int, in_time_str.split(":")[:2])
            in_mins = h_in * 60 + m_in
            
            # Parse shift HH:MM
            h_sh, m_sh = map(int, shift_start_str.split(":")[:2])
            sh_mins = h_sh * 60 + m_sh
            
            late_raw = in_mins - sh_mins
            late_m = late_raw if late_raw > 0 else 0
            
            # Update row data so late_minutes column reflects reality
            row["calculated_late_minutes"] = late_m
        except Exception:
            late_m = int(row.get("late_minutes", 0) or 0)
    else:
        late_m = int(row.get("late_minutes", 0) or 0)

    # 1. Leave Logic (Highest priority)
    if pd.notna(row.get("leave_type")) and str(row.get("leave_type")).strip() != "":
        return f"On Leave: {row['leave_type']}"

    # Use the maximum duration from both sources to determine "Present" status
    effective_dur = max(dur_h, work_hrs)

    # 2. Incomplete (Punch out missing in ESSL, but only if no Login data fills the gap)
    if has_essl and (pd.isna(row.get("out_time")) or str(row.get("out_time")).strip() == ""):
        if effective_dur < config.MIN_HOURS_PRESENT:
            return "Incomplete"

    # 3. Mobile Login detection: Login data exists but no ESSL punches
    if not has_essl and (has_login or work_hrs > 0):
        if late_m > config.LATE_THRESHOLD_MINUTES:
            return "Late"
        return "Mobile Login"

    # 4. Absent (No ESSL, no login data)
    if not has_essl and not has_login and work_hrs == 0:
        return "Absent"

    # 5. Classification based on effective duration
    if effective_dur >= config.MIN_HOURS_PRESENT:
        if late_m > config.LATE_THRESHOLD_MINUTES:
            return "Late"
        return "Present"
    elif effective_dur > 0:
        return "Short Hours"

    return "Absent"


def process_attendance(essl_df: pd.DataFrame, login_df: pd.DataFrame, categories: dict = None, shifts: dict = None) -> pd.DataFrame:
    if essl_df.empty and login_df.empty:
        return pd.DataFrame()

    if categories is None:
        categories = {"1500": "Series 1500", "IND": "India Series", "US": "US Series", "OTHER": "Other"}
    if shifts is None:
        shifts = {"global": config.OFFICE_START_TIME, "departments": {}, "employees": {}}

    def get_category(code):
        c = str(code).upper()
        # Order matters: check longest prefixes first if needed,
        # but here we just check our keys
        for prefix, name in categories.items():
            if prefix != "OTHER" and c.startswith(prefix):
                return name
        return categories.get("OTHER", "Other")

    essl = essl_df.copy() if not essl_df.empty else pd.DataFrame(
        columns=["emp_code", "emp_name", "date", "in_time", "out_time", "duration_hours", "late_minutes", "punch_records"])

    if not essl.empty:
        # Aggregation logic: Earliest In, Latest Out, Sum of Durations, Concat Status/Punches
        # We need to preserve emp_name as well
        agg_cols = {
            "emp_name": "first",
            "in_time": "min",
            "out_time": "max",
            "duration_hours": "sum",
            "late_minutes": "sum",
            "early_minutes": "sum",
            "department": "first",
            "status": lambda x: " / ".join(filter(None, set(map(str, x)))),
            "punch_records": lambda x: " | ".join(filter(None, set(map(str, x))))
        }
        # Only include columns that actually exist
        agg_cols = {k: v for k, v in agg_cols.items() if k in essl.columns}
        essl = essl.groupby(["emp_code", "date"], as_index=False).agg(agg_cols)

    login_cols = ["emp_code", "emp_name", "date", "login_time", "logout_time",
                  "leave_type", "work_hours", "department", "designation", "manager_name"]
    if not login_df.empty:
        login = login_df[[c for c in login_cols if c in login_df.columns]].copy()
        # Aggregate login data by (emp_code, date)
        # We take earliest login, latest logout, sum work hours, and first designation/manager
        agg_login = {
            "emp_name": "first",
            "login_time": "min",
            "logout_time": "max",
            "work_hours": "sum",
            "leave_type": "first", # Assuming same leave type if multiple rows
            "department": "first",
            "designation": "first",
            "manager_name": "first"
        }
        agg_login = {k: v for k, v in agg_login.items() if k in login.columns}
        login = login.groupby(["emp_code", "date"], as_index=False).agg(agg_login)
    else:
        login = pd.DataFrame(columns=login_cols)

    # Full outer merge
    merge_cols = ["emp_code", "date"]
    merged = pd.merge(essl, login, on=merge_cols, how="outer",
                      suffixes=("", "_login"))

    # Merge overlapping text columns, prioritizing login sheet values if present
    for col in ["emp_name", "department", "designation"]:
        login_col = f"{col}_login"
        if login_col in merged.columns:
            merged[login_col] = merged[login_col].replace(["", "nan", "Nan", "None"], None)
            merged[col] = merged[col].replace(["", "nan", "Nan", "None"], None)
            # prioritize login over essl
            merged[col] = merged[login_col].combine_first(merged[col])
            merged.drop(columns=[login_col], inplace=True)

    for col in ["in_time", "out_time", "status", "punch_records", "department",
                "login_time", "logout_time", "leave_type", "designation", "manager_name"]:
        if col not in merged.columns:
            merged[col] = ""
        merged[col] = (merged[col].fillna("").astype(str).str.strip()
                       .replace("nan", "").replace("None", ""))

    for col in ["duration_hours", "late_minutes", "early_minutes", "work_hours"]:
        if col not in merged.columns:
            merged[col] = 0.0
        merged[col] = pd.to_numeric(merged[col], errors="coerce").fillna(0)

    # Effective duration = Max of ESSL duration and Login work_hours
    merged["effective_hours"] = merged[["duration_hours", "work_hours"]].max(axis=1)

    merged["day_status"] = merged.apply(lambda r: classify_day(r.to_dict(), shifts), axis=1)
    
    # Optional: Update late_minutes to use the newly calculated ones if 'calculated_late_minutes' was set in dict mapping? 
    # Since apply() on axis=1 with dict copy modifies row dict, better to do vector assignment where possible, or just leave it.
    # We will just accept the day_status as calculated.

    merged["duration_fmt"] = merged["effective_hours"].apply(_fmt_hours)
    merged["category"] = merged["emp_code"].apply(get_category)

    merged.sort_values(["emp_code", "date"], inplace=True)
    merged.reset_index(drop=True, inplace=True)
    return merged


def employee_summary(merged: pd.DataFrame) -> pd.DataFrame:
    if merged.empty:
        return pd.DataFrame()

    rows = []
    for emp_code, grp in merged.groupby("emp_code"):
        emp_name = grp["emp_name"].dropna()
        emp_name = emp_name[emp_name != ""].iloc[0] if not emp_name[emp_name != ""].empty else emp_code

        designation = grp["designation"].dropna()
        designation = designation[designation != ""].iloc[0] if not designation[designation != ""].empty else ""

        manager = grp["manager_name"].dropna()
        manager = manager[manager != ""].iloc[0] if not manager[manager != ""].empty else ""

        dept = grp["department"].dropna()
        dept = dept[dept != ""].iloc[0] if not dept[dept != ""].empty else ""

        category = grp["category"].iloc[0] if "category" in grp.columns else "Other"

        total    = len(grp)
        present  = int(grp["day_status"].str.contains("Present|Late|Short|Manual|Mobile", na=False).sum())
        absent   = int((grp["day_status"] == "Absent").sum())
        late     = int((grp["day_status"] == "Late").sum())
        short_h  = int((grp["day_status"] == "Short Hours").sum())
        on_leave = int(grp["day_status"].str.startswith("On Leave", na=False).sum())
        incomplete = int((grp["day_status"] == "Incomplete").sum())

        dur_vals = grp["effective_hours"][grp["effective_hours"] > 0]
        avg_dur  = round(float(dur_vals.mean()), 2) if not dur_vals.empty else 0.0
        pct      = round(present / total * 100, 1) if total else 0

        latest = grp.sort_values("date").iloc[-1]["day_status"]

        rows.append({
            "emp_code":      emp_code,
            "emp_name":      emp_name,
            "department":    dept,
            "designation":   designation,
            "manager_name":  manager,
            "category":      category,
            "total_days":    total,
            "present_days":  present,
            "absent_days":   absent,
            "late_count":    late,
            "short_hours":   short_h,
            "on_leave":      on_leave,
            "incomplete":    incomplete,
            "avg_duration":  avg_dur,
            "avg_dur_fmt":   _fmt_hours(avg_dur),
            "pct_present":   pct,
            "latest_status": latest,
        })

    return pd.DataFrame(rows).sort_values("emp_name").reset_index(drop=True)


def weekly_stats(merged: pd.DataFrame) -> dict:
    if merged.empty:
        return {}

    # Calculate all unique dates in the dataset
    merged["date_obj"] = pd.to_datetime(merged["date"]).dt.date
    window = sorted(merged["date_obj"].dropna().unique())
    merged.drop(columns=["date_obj"], inplace=True)
    
    # Create strictly formatted strings to guarantee matches
    merged["date_str"] = pd.to_datetime(merged["date"]).dt.strftime("%Y-%m-%d")

    window_strs = [d.strftime("%Y-%m-%d") for d in window]

    wkly = merged

    total_emp   = merged["emp_code"].nunique()
    total_slots = len(wkly)
    if total_slots == 0:
        return {}

    present_cnt = int(wkly["day_status"].str.contains("Present|Late|Short|Manual|Mobile", na=False).sum())
    absent_cnt  = int((wkly["day_status"] == "Absent").sum())
    late_cnt    = int((wkly["day_status"] == "Late").sum())
    leave_cnt   = int(wkly["day_status"].str.startswith("On Leave", na=False).sum())

    dur_vals = wkly["effective_hours"][wkly["effective_hours"] > 0]
    avg_dur  = round(float(dur_vals.mean()), 2) if not dur_vals.empty else 0.0
    pct      = round(present_cnt / total_slots * 100, 1) if total_slots else 0

    daily = []
    for d_str, d_obj in zip(window_strs, window):
        day_data = wkly[wkly["date_str"] == d_str]
        d_dur = day_data["effective_hours"][day_data["effective_hours"] > 0]
        daily.append({
            "date":        d_str,
            "day_name":    d_obj.strftime("%A"),
            "is_rest_day": d_obj.weekday() >= 5, # 5 is Saturday, 6 is Sunday
            "present":     int(day_data["day_status"].str.contains("Present|Late|Short|Manual|Mobile", na=False).sum()),
            "absent":      int((day_data["day_status"] == "Absent").sum()),
            "late":        int((day_data["day_status"] == "Late").sum()),
            "avg_dur":     round(float(d_dur.mean()), 2) if not d_dur.empty else 0,
        })
        
    merged.drop(columns=["date_str"], inplace=True)

    return {
        "total_employees": int(total_emp),
        "total_slots":     int(total_slots),
        "present_count":   present_cnt,
        "absent_count":    absent_cnt,
        "late_count":      late_cnt,
        "leave_count":     leave_cnt,
        "avg_duration":    avg_dur,
        "avg_dur_fmt":     _fmt_hours(avg_dur),
        "pct_present":     float(pct),
        "daily":           daily,
        "window_dates":    [str(d) for d in window],
    }
