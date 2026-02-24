
import pandas as pd
import os
import sys

# Add project root to path to import config and loaders
sys.path.append('/Users/akhil/.gemini/antigravity/scratch/attendance_website')

from data_loader.load_essl import load_essl
from data_loader.load_login import load_login
import config

UPLOAD_FOLDER = '/Users/akhil/.gemini/antigravity/scratch/attendance_website/uploads'
essl_path = os.path.join(UPLOAD_FOLDER, "essl_punch.csv")
login_path = os.path.join(UPLOAD_FOLDER, "login_logout.xls")

print(f"Checking ESSL at {essl_path} (exists: {os.path.exists(essl_path)})")
print(f"Checking Login at {login_path} (exists: {os.path.exists(login_path)})")

essl_df = load_essl(essl_path)
login_df = load_login(login_path)

emp_code = "IND00313"
target_date = "2026-02-20"

print(f"\n--- ESSL Data for {emp_code} ---")
if not essl_df.empty:
    target_essl = essl_df[(essl_df['emp_code'] == emp_code) & (essl_df['date'].astype(str) == target_date)]
    print(target_essl[['date', 'in_time', 'out_time', 'duration_hours']])
else:
    print("ESSL DataFrame is empty")

print(f"\n--- Login Data for {emp_code} ---")
if not login_df.empty:
    target_login = login_df[(login_df['emp_code'] == emp_code) & (login_df['date'].astype(str) == target_date)]
    print(target_login[['date', 'login_time', 'logout_time', 'work_hours']])
else:
    print("Login DataFrame is empty")

print("\n--- Any other dates for this employee in Login? ---")
if not login_df.empty:
    print(login_df[login_df['emp_code'] == emp_code]['date'].value_counts())
