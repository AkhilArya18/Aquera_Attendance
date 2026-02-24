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
from data_loader.load_essl  import load_essl
from data_loader.load_login import load_login
from processor.attendance_engine import process_attendance, employee_summary, weekly_stats
from processor.abnormal_engine   import detect_abnormal

app = Flask(__name__)
app.secret_key = config.SECRET_KEY
app.config["UPLOAD_FOLDER"] = config.UPLOAD_FOLDER
os.makedirs(config.UPLOAD_FOLDER, exist_ok=True)

if os.environ.get("VERCEL") == "1":
    CATEGORIES_FILE = "/tmp/categories.json"
else:
    CATEGORIES_FILE = "categories.json"

def _load_categories():
    if os.path.exists(CATEGORIES_FILE):
        try:
            with open(CATEGORIES_FILE, "r") as f:
                return json.load(f)
        except:
            pass
    return {"1500": "Series 1500", "IND": "India Series", "US": "US Series", "OTHER": "Other"}

def _save_categories(data):
    with open(CATEGORIES_FILE, "w") as f:
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


def _load_all():
    """Load & process both data sources. Returns (merged_df, summary_df, abnormal_df, stats)."""
    # Resolve ESSL path (prefer .csv, then .xlsx, then .xls)
    essl_path = os.path.join(config.UPLOAD_FOLDER, "essl_punch.csv")
    if not os.path.exists(essl_path):
        for ext in [".xlsx", ".xls"]:
            alt = os.path.join(config.UPLOAD_FOLDER, "essl_punch" + ext)
            if os.path.exists(alt):
                essl_path = alt
                break
    if not os.path.exists(essl_path):
        essl_path = config.ESSL_FILE_PATH

    # Resolve Login path (prefer .xlsx, then .xls)
    login_path = os.path.join(config.UPLOAD_FOLDER, "login_logout.xlsx")
    if not os.path.exists(login_path):
        alt = os.path.join(config.UPLOAD_FOLDER, "login_logout.xls")
        if os.path.exists(alt):
            login_path = alt
    if not os.path.exists(login_path):
        login_path = config.LOGIN_FILE_PATH

    cats = _load_categories()
    essl_df  = load_essl(essl_path)
    login_df = load_login(login_path)
    merged   = process_attendance(essl_df, login_df, categories=cats)
    summary  = employee_summary(merged)
    abnormal = detect_abnormal(merged)
    stats    = weekly_stats(merged)
    return merged, summary, abnormal, stats, cats


def _uploaded_files():
    """Return dict of which uploaded files exist."""
    res = {}
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
    return render_template("dashboard.html", stats=stats,
                           uploaded=_uploaded_files(), stats_json=json.dumps(stats))


@app.route("/employees")
def employees():
    merged, summary, abnormal, stats, cats = _load_all()
    employees_list = summary.to_dict(orient="records") if not summary.empty else []
    return render_template("employees.html", employees=employees_list,
                           uploaded=_uploaded_files())


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
        f.save(save_path)
        flash(f"File uploaded successfully as '{save_name}'!", "success")
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
    cats = _load_categories()
    if request.method == "POST":
        new_cats = {}
        for k in cats.keys():
            new_cats[k] = request.form.get(f"cat_{k}", cats[k])
        _save_categories(new_cats)
        flash("Categories updated successfully!", "success")
        return redirect(url_for("settings"))
    return render_template("settings.html", categories=cats, uploaded=_uploaded_files())


@app.route("/clear/<file_type>")
def clear_upload(file_type):
    for name in os.listdir(config.UPLOAD_FOLDER):
        if (file_type == "essl"  and name.startswith("essl_punch")) or \
           (file_type == "login" and name.startswith("login_logout")):
            os.remove(os.path.join(config.UPLOAD_FOLDER, name))
    flash(f"Cleared {file_type} upload. Will use default Downloads path.", "info")
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

if __name__ == "__main__":
    print("=" * 55)
    print(f"  Attendance Website  →  http://127.0.0.1:{config.PORT}")
    print("=" * 55)
    app.run(debug=config.DEBUG, port=config.PORT)
