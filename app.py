"""
app.py – Flask application for the Attendance Website.
Run: python app.py
"""

import os, json
import pandas as pd
from flask import (Flask, render_template, request, redirect,
                   url_for, flash, jsonify)
from werkzeug.utils import secure_filename

import config
from blob_api import upload_blob, fetch_blob, list_blobs, delete_blob_by_pathname
from data_loader.load_essl  import load_essl
from data_loader.load_login import load_login
from processor.attendance_engine import process_attendance, employee_summary, weekly_stats
from processor.abnormal_engine   import detect_abnormal

app = Flask(__name__)
app.secret_key = config.SECRET_KEY
app.config["UPLOAD_FOLDER"] = config.UPLOAD_FOLDER
os.makedirs(config.UPLOAD_FOLDER, exist_ok=True)

if os.environ.get("VERCEL") == "1":
    SETTINGS_FILE = "/tmp/settings.json"
else:
    SETTINGS_FILE = "settings.json"

def _load_settings():
    default_settings = {
        "categories": {"1500": "Series 1500", "IND": "India Series", "US": "US Series", "OTHER": "Other"},
        "shifts": {
            "global": "09:30",
            "departments": {},
            "employees": {}
        }
    }
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r") as f:
                data = json.load(f)
                # Merge with defaults to ensure keys exist
                for k, v in data.items():
                    if isinstance(v, dict) and k in default_settings:
                        default_settings[k].update(v)
                    else:
                        default_settings[k] = v
                return default_settings
        except:
            pass
    return default_settings

def _save_settings(data):
    with open(SETTINGS_FILE, "w") as f:
        json.dump(data, f, indent=4)

# ── helpers ────────────────────────────────────────────────────────────────────

def _allowed(filename):
    return ("." in filename and
            filename.rsplit(".", 1)[1].lower() in config.ALLOWED_EXTENSIONS)


def _resolve_path(upload_name: str, default_path: str) -> str:
    """Return uploaded file path (if exists) else default Downloads path."""
    up = os.path.join(config.UPLOAD_FOLDER, upload_name)
    if os.path.exists(up):
        return up
    return default_path


def _use_blob():
    """Return True when Vercel Blob should be used (token must be set)."""
    return bool(os.environ.get("BLOB_READ_WRITE_TOKEN"))


def _load_all():
    """Load & process both data sources. Returns (merged_df, summary_df, abnormal_df, stats, settings)."""
    # ── Prefer uploads folder; if on Vercel, try to pull from Blob first ─────
    essl_path = None
    login_path = None
    
    use_blob = _use_blob()
    print(f"[Debug] _load_all start. use_blob={use_blob}")

    if use_blob:
        blobs = list_blobs()
        blob_names = {b["pathname"] for b in blobs}
        print(f"[Debug] Blobs in store: {list(blob_names)}")
        tmp = "/tmp"
        os.makedirs(tmp, exist_ok=True)
        
        # ESSL
        for candidate in ["essl_punch.csv", "essl_punch.xlsx", "essl_punch.xls"]:
            if candidate in blob_names:
                dest = os.path.join(tmp, candidate)
                if fetch_blob(candidate, dest):
                    essl_path = dest
                    print(f"[Debug] Picked ESSL from Blob: {candidate}")
                    break
        
        # Login
        for candidate in ["login_logout.xlsx", "login_logout.xls"]:
            if candidate in blob_names:
                dest = os.path.join(tmp, candidate)
                if fetch_blob(candidate, dest):
                    login_path = dest
                    print(f"[Debug] Picked Login from Blob: {candidate}")
                    break
    
    if not essl_path:
        # Fall back to the local uploads folder or Downloads dir
        for ext in [".csv", ".xlsx", ".xls"]:
            alt = os.path.join(config.UPLOAD_FOLDER, "essl_punch" + ext)
            if os.path.exists(alt):
                essl_path = alt
                print(f"[Debug] Fallback: ESSL local path found: {essl_path}")
                break
        if not essl_path:
            essl_path = config.ESSL_FILE_PATH
            print(f"[Debug] Default ESSL path: {essl_path}")

    if not login_path:
        for ext in [".xlsx", ".xls"]:
            alt = os.path.join(config.UPLOAD_FOLDER, "login_logout" + ext)
            if os.path.exists(alt):
                login_path = alt
                print(f"[Debug] Fallback: Login local path found: {login_path}")
                break
        if not login_path:
            login_path = config.LOGIN_FILE_PATH
            print(f"[Debug] Default Login path: {login_path}")

    settings = _load_settings()
    cats = settings.get("categories", {})
    shifts = settings.get("shifts", {})
    essl_df  = load_essl(essl_path)
    login_df = load_login(login_path)
    merged   = process_attendance(essl_df, login_df, categories=cats, shifts=shifts)
    summary  = employee_summary(merged)
    abnormal = detect_abnormal(merged)
    stats    = weekly_stats(merged)
    return merged, summary, abnormal, stats, settings


def _uploaded_files():
    """Return dict of which uploaded files exist (checks Blob OR local disk)."""
    res = {}
    if _use_blob():
        blobs = list_blobs()
        blob_names = {b["pathname"] for b in blobs}
        for name in ["essl_punch.csv", "essl_punch.xlsx", "login_logout.xlsx", "login_logout.xls"]:
            res[name] = name in blob_names
    else:
        for name in ["essl_punch.csv", "essl_punch.xlsx", "login_logout.xlsx", "login_logout.xls"]:
            res[name] = os.path.exists(os.path.join(config.UPLOAD_FOLDER, name))
    return res


# ── routes ─────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return redirect(url_for("dashboard"))


@app.route("/dashboard")
def dashboard():
    merged, summary, abnormal, stats, cats = _load_all()
    # Augment stats with abnormal vs normal total counts for the pie chart
    if stats and not abnormal.empty:
        stats["abnormal_count"] = int((abnormal["risk_level"] != "Normal").sum())
        stats["normal_count"]   = int((abnormal["risk_level"] == "Normal").sum())
    else:
        stats["abnormal_count"] = 0
        stats["normal_count"]   = 0

    return render_template("dashboard.html", stats=stats,
                           uploaded=_uploaded_files(), stats_json=json.dumps(stats))


@app.route("/employees")
def employees():
    merged, summary, abnormal, stats, cats = _load_all()
    employees_list = summary.to_dict(orient="records") if not summary.empty else []
    return render_template("employees.html", employees=employees_list,
                           uploaded=_uploaded_files())


@app.route("/details")
def details():
    merged, summary, abnormal, stats, cats = _load_all()
    if merged.empty:
        flash("No data loaded yet.", "warning")
        return redirect(url_for("dashboard"))
        
    date_filter = request.args.get('date')
    status_filter = request.args.get('status')
    leave_filter = request.args.get('leave')
    
    df = merged.copy()
    
    # Convert dates to string for safe comparison with URL params
    df['date_str'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')
    
    title = "Attendance Details"
    if date_filter:
        df = df[df['date_str'] == date_filter]
        title += f" for {date_filter}"
    if status_filter:
        df = df[df['day_status'] == status_filter]
        title += f" ({status_filter})"
    if leave_filter:
        df = df[df['day_status'].str.startswith('On Leave', na=False)]
        title = "Employees On Leave"
        
    df = df.drop(columns=['date_str'])
    records = df.to_dict(orient="records")
    return render_template("details.html", records=records, title=title, uploaded=_uploaded_files())

@app.route("/employee/<emp_code>")
def employee_detail(emp_code):
    merged, summary, abnormal, stats, cats = _load_all()
    if merged.empty:
        flash("No data loaded yet.", "warning")
        return redirect(url_for("employees"))

    emp_data = merged[merged["emp_code"] == emp_code.upper()].copy()
    if emp_data.empty:
        flash(f"Employee {emp_code} not found.", "danger")
        return redirect(url_for("employees"))

    emp_data["date"] = emp_data["date"].astype(str)
    records   = emp_data.sort_values("date", ascending=False).to_dict(orient="records")
    emp_name  = records[0]["emp_name"] if records else emp_code

    # Summary row
    emp_sum  = summary[summary["emp_code"] == emp_code.upper()]
    emp_info = emp_sum.to_dict(orient="records")[0] if not emp_sum.empty else {}

    # Abnormal info
    ab_row  = abnormal[abnormal["emp_code"] == emp_code.upper()]
    ab_info = ab_row.to_dict(orient="records")[0] if not ab_row.empty else {}

    return render_template("employee_detail.html",
                           emp_code=emp_code, emp_name=emp_name,
                           records=records, emp_info=emp_info,
                           ab_info=ab_info, uploaded=_uploaded_files())


@app.route("/abnormal")
def abnormal():
    merged, summary, ab_df, stats, cats = _load_all()
    ab_list = ab_df.fillna("").to_dict(orient="records") if not ab_df.empty else []
    return render_template("abnormal.html", employees=ab_list,
                           uploaded=_uploaded_files())


@app.route("/upload", methods=["GET", "POST"])
def upload():
    if request.method == "POST":
        file_type = request.form.get("file_type", "")
        f = request.files.get("file")

        if not f or f.filename == "":
            flash("No file selected.", "danger")
            return redirect(url_for("upload"))

        if not _allowed(f.filename):
            flash("Invalid file type. Use CSV, XLS, or XLSX.", "danger")
            return redirect(url_for("upload"))

        ext = f.filename.rsplit(".", 1)[1].lower()

        if file_type == "essl":
            save_name = f"essl_punch.{ext}"
        elif file_type == "login":
            save_name = f"login_logout.{ext}"
        else:
            flash("Unknown file type selection.", "danger")
            return redirect(url_for("upload"))

        save_path = os.path.join(config.UPLOAD_FOLDER, save_name)
        file_bytes = f.read()
        
        if _use_blob():
            # Push to Vercel Blob for persistence
            ext_lower = ext.lower()
            ct_map = {"csv": "text/csv", "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "xls": "application/vnd.ms-excel"}
            result = upload_blob(save_name, file_bytes, content_type=ct_map.get(ext_lower, "application/octet-stream"))
            if result:
                flash(f"Successfully uploaded '{save_name}' to persistent Vercel Blob storage.", "success")
                return redirect(url_for("dashboard"))
            else:
                flash("CRITICAL: Failed to upload to Vercel Blob (Persistence will NOT work). Falling back to temporary storage.", "danger")
                with open(save_path, "wb") as fh:
                    fh.write(file_bytes)
        else:
            with open(save_path, "wb") as fh:
                fh.write(file_bytes)
            flash(f"File uploaded locally to '{save_name}' (Temporary storage ONLY).", "warning")
        return redirect(url_for("dashboard"))

    return render_template("upload.html", uploaded=_uploaded_files())


@app.route("/api/stats")
def api_stats():
    _, _, _, stats = _load_all()
    return jsonify(stats)


@app.route("/api/employee/<emp_code>/week")
def api_employee_week(emp_code):
    merged, summary, abnormal, _, cats = _load_all()
    if merged.empty:
        return jsonify({"error": "No data loaded"}), 404
        
    emp_data = merged[merged["emp_code"] == emp_code.upper()].copy()
    if emp_data.empty:
        return jsonify({"error": "Employee not found"}), 404

    # Get last 7 records
    emp_data["date_str"] = emp_data["date"].astype(str)
    recent = emp_data.sort_values("date", ascending=False).head(7).fillna("").to_dict(orient="records")
    
    # Get employee info
    emp_sum = summary[summary["emp_code"] == emp_code.upper()]
    info = emp_sum.fillna("").to_dict(orient="records")[0] if not emp_sum.empty else {}
    
    return jsonify({
        "info": info,
        "records": recent
    })


@app.route("/settings", methods=["GET", "POST"])
def settings():
    user_settings = _load_settings()
    cats = user_settings.get("categories", {})
    shifts = user_settings.get("shifts", {"global": "09:30", "departments": {}, "employees": {}})

    if request.method == "POST":
        # Handle Categories
        new_cats = {}
        for k in cats.keys():
            new_cats[k] = request.form.get(f"cat_{k}", cats[k])
        
        # Handle Shifts
        shifts["global"] = request.form.get("global_shift", shifts.get("global", "09:30"))
        
        # Parse departments (format: Dept1:09:30, Dept2:10:00)
        dept_str = request.form.get("department_shifts", "")
        shifts["departments"] = {}
        if dept_str.strip():
            for pair in dept_str.split(","):
                if ":" in pair:
                    parts = pair.split(":")
                    if len(parts) >= 2:
                        dept = parts[0].strip().upper()
                        time_val = ":".join(parts[1:]).strip()
                        if dept and time_val:
                            shifts["departments"][dept] = time_val

        # Parse employees (format: EMP001:09:30, EMP002:10:00)
        emp_str = request.form.get("employee_shifts", "")
        shifts["employees"] = {}
        if emp_str.strip():
            for pair in emp_str.split(","):
                if ":" in pair:
                    parts = pair.split(":")
                    if len(parts) >= 2:
                        emp = parts[0].strip().upper()
                        time_val = ":".join(parts[1:]).strip()
                        if emp and time_val:
                            shifts["employees"][emp] = time_val

        user_settings["categories"] = new_cats
        user_settings["shifts"] = shifts
        _save_settings(user_settings)
        flash("Settings updated successfully!", "success")
        return redirect(url_for("settings"))
        
    # Format department shifts for display
    dept_disp = ", ".join([f"{k}:{v}" for k, v in shifts.get("departments", {}).items()])
    emp_disp = ", ".join([f"{k}:{v}" for k, v in shifts.get("employees", {}).items()])
    
    return render_template("settings.html", categories=cats, shifts=shifts, 
                           dept_disp=dept_disp, emp_disp=emp_disp, uploaded=_uploaded_files())


@app.route("/clear/<file_type>")
def clear_upload(file_type):
    if _use_blob():
        for name in ["essl_punch.csv", "essl_punch.xlsx", "essl_punch.xls"] if file_type == "essl" \
                 else ["login_logout.xlsx", "login_logout.xls"]:
            delete_blob_by_pathname(name)
    else:
        for name in os.listdir(config.UPLOAD_FOLDER):
            if (file_type == "essl"  and name.startswith("essl_punch")) or \
               (file_type == "login" and name.startswith("login_logout")):
                os.remove(os.path.join(config.UPLOAD_FOLDER, name))
    flash(f"Cleared {file_type} upload.", "info")
    return redirect(url_for("upload"))


@app.route("/export_excel/<report_type>")
def export_excel(report_type):
    import io
    from flask import make_response

    merged, summary, abnormal, stats, cats = _load_all()
    
    if report_type == "employees":
        if summary.empty:
            flash("No employee data to export.", "warning")
            return redirect(url_for("employees"))
        df = summary.copy()
        filename = "Aquera_Employee_List.xlsx"
    elif report_type == "abnormal":
        if abnormal.empty:
            flash("No abnormal data to export.", "warning")
            return redirect(url_for("abnormal"))
            
        risks_filter = request.args.get("risks", "")
        if risks_filter:
            risk_list = risks_filter.split(",")
            df = abnormal[abnormal["risk_level"].isin(risk_list)].copy()
        else:
            df = abnormal.copy()
        filename = "Aquera_Abnormal_Report.xlsx"
    else:
        flash("Invalid report type.", "danger")
        return redirect(url_for("dashboard"))

    # Format Data
    if "department" in df.columns:
        df["department"] = df["department"].astype(str).str.upper()
    df.columns = [str(col).capitalize() for col in df.columns]

    # Generate Excel
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Report')
    
    response = make_response(output.getvalue())
    response.headers["Content-Disposition"] = f"attachment; filename={filename}"
    response.headers["Content-Type"] = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return response

@app.route("/debug/blob")
def debug_blob():
    """Diagnostic endpoint - shows Blob token status and store contents."""
    from blob_api import _token
    token_val = _token()
    has_env_token = bool(os.environ.get("BLOB_READ_WRITE_TOKEN"))

    # Try a live upload test
    test_result = upload_blob("debug_test.txt", b"token_test", "text/plain")

    blobs = list_blobs()
    return jsonify({
        "env_BLOB_READ_WRITE_TOKEN_set": has_env_token,
        "token_prefix": token_val[:30] + "..." if token_val else None,
        "test_upload_ok": test_result is not None,
        "test_upload_pathname": test_result.get("pathname") if test_result else None,
        "blobs": [{"pathname": b.get("pathname"), "size": b.get("size")} for b in blobs],
        "vercel": os.environ.get("VERCEL"),
    })


if __name__ == "__main__":
    print("=" * 55)
    print(f"  Attendance Website  →  http://127.0.0.1:{config.PORT}")
    print("=" * 55)
    app.run(debug=config.DEBUG, port=config.PORT)
