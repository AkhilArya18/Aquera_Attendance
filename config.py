import os

# ─── FILE PATHS ───────────────────────────────────────────────────────────────
# Default paths for auto-loading from Downloads folder
DOWNLOADS_DIR = "/Users/akhil/Downloads"

ESSL_FILE_PATH   = os.path.join(DOWNLOADS_DIR, "essl_punch.csv")
LOGIN_FILE_PATH  = os.path.join(DOWNLOADS_DIR, "login_logout.xlsx")

# ─── UPLOAD FOLDER ────────────────────────────────────────────────────────────
# Uploaded files are stored here and override the default paths above
if os.environ.get("VERCEL") == "1":
    UPLOAD_FOLDER = "/tmp"
else:
    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "uploads")
ALLOWED_EXTENSIONS = {"csv", "xls", "xlsx"}

# ─── ATTENDANCE RULES ─────────────────────────────────────────────────────────
MIN_HOURS_PRESENT       = 6      # hours — below this → Short Hours
LATE_THRESHOLD_MINUTES  = 30     # minutes — beyond this → Late
OFFICE_START_TIME       = "09:30"  # HH:MM  (used for late calculation if missing)

# ─── ABNORMAL DETECTION ───────────────────────────────────────────────────────
ABNORMAL_WINDOW_DAYS    = 7      # how many past working days to evaluate

THRESHOLDS = {
    "irregular_present_days": 3,    # present < 3 → Irregular
    "absentee_days":          2,    # absent ≥ 2
    "habitual_late_days":     3,    # late ≥ 3
    "low_productivity_days":  3,    # short hours ≥ 3
    "punch_avoidance_count":  2,    # missing punches ≥ 2
}

SCORES = {
    "absenteeism":        30,
    "irregular_presence": 25,
    "late":               15,
    "short_hours":        15,
    "missing_punches":    10,
}

RISK_LEVELS = [
    (20,  "Normal",    "success"),
    (40,  "Warning",   "warning"),
    (60,  "High Risk", "danger"),
    (9999,"Critical",  "dark"),
]

# ─── FLASK ────────────────────────────────────────────────────────────────────
SECRET_KEY = "attendance-secret-2024"
DEBUG      = True
PORT       = 5050
