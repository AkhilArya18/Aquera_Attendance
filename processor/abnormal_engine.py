"""
abnormal_engine.py – Detects employees with abnormal attendance patterns
based on the last N working days.
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
        if d.weekday() < 6:
            days.append(d)
        d -= timedelta(days=1)
    return sorted(days)


def compute_risk(score: int) -> tuple:
    """Return (level_label, bootstrap_class) for a given score."""
    for threshold, label, cls in config.RISK_LEVELS:
        if score <= threshold:
            return label, cls
    return "Critical", "dark"


def detect_abnormal(merged: pd.DataFrame) -> pd.DataFrame:
    """
    Evaluate each employee's attendance over the last ABNORMAL_WINDOW_DAYS
    working days and compute an abnormal score + risk level.

    Returns DataFrame sorted by score descending.
    """
    if merged.empty:
        return pd.DataFrame()

    merged["date_obj"] = pd.to_datetime(merged["date"]).dt.date
    window = sorted(merged["date_obj"].dropna().unique())
    merged.drop(columns=["date_obj"], inplace=True)
    
    wkly = merged.copy()

    T = config.THRESHOLDS
    S = config.SCORES
    rows = []

    for emp_code, grp in wkly.groupby("emp_code"):
        emp_name = grp["emp_name"].dropna().iloc[0] if not grp["emp_name"].dropna().empty else emp_code
        
        dept = grp["department"].dropna()
        dept = dept[dept != ""].iloc[0] if not dept[dept != ""].empty else ""

        category = grp["category"].iloc[0] if "category" in grp.columns else "Other"
        total    = len(grp)

        present_days = int(grp["day_status"].str.contains("Present|Late|Short|Manual|Mobile", na=False).sum())
        absent_days  = int((grp["day_status"] == "Absent").sum())
        late_days    = int((grp["day_status"] == "Late").sum())
        short_days   = int((grp["day_status"] == "Short Hours").sum())
        incomplete   = int((grp["day_status"] == "Incomplete").sum())
        on_leave     = int(grp["day_status"].str.startswith("On Leave").sum())
        avg_dur      = grp[grp["duration_hours"] > 0]["duration_hours"].mean()
        avg_dur      = round(float(avg_dur), 2) if not pd.isna(avg_dur) else 0.0
        pct_present  = round(present_days / total * 100, 1) if total else 0

        # ── score ────────────────────────────────────────────────────────────
        score  = 0
        flags  = []

        if absent_days >= T["absentee_days"]:
            score += S["absenteeism"]
            flags.append(f"Absent ≥ {T['absentee_days']} days")

        if present_days < T["irregular_present_days"]:
            score += S["irregular_presence"]
            flags.append(f"Present < {T['irregular_present_days']} days")

        if late_days >= T["habitual_late_days"]:
            score += S["late"]
            flags.append(f"Late ≥ {T['habitual_late_days']} days")

        if short_days >= T["low_productivity_days"]:
            score += S["short_hours"]
            flags.append(f"Short hours ≥ {T['low_productivity_days']} days")

        if incomplete >= T["punch_avoidance_count"]:
            score += S["missing_punches"]
            flags.append(f"Incomplete punches ≥ {T['punch_avoidance_count']}")

        risk_label, risk_cls = compute_risk(score)

        rows.append({
            "emp_code":     emp_code,
            "emp_name":     emp_name,
            "department":   dept,
            "category":     category,
            "total_days":   total,
            "present_days": present_days,
            "absent_days":  absent_days,
            "late_days":    late_days,
            "short_days":   short_days,
            "incomplete":   incomplete,
            "on_leave":     on_leave,
            "avg_duration": avg_dur,
            "pct_present":  pct_present,
            "score":        score,
            "risk_level":   risk_label,
            "risk_class":   risk_cls,
            "flags":        ", ".join(flags) if flags else "—",
        })

    df = pd.DataFrame(rows).sort_values("score", ascending=False).reset_index(drop=True)
    return df
