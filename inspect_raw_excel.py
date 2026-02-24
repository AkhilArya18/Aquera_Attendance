
import pandas as pd
import os
import sys

# Add project root to path
sys.path.append('/Users/akhil/.gemini/antigravity/scratch/attendance_website')

from data_loader.load_login import _detect_header_row, _find_col, COLUMN_MAP

UPLOAD_FOLDER = '/Users/akhil/.gemini/antigravity/scratch/attendance_website/uploads'
login_path = os.path.join(UPLOAD_FOLDER, "login_logout.xls")

print(f"Reading {login_path}")
raw = pd.read_excel(login_path, dtype=str, header=None)
hdr_idx = _detect_header_row(raw)
df = raw.iloc[hdr_idx + 1:].copy()
df.columns = [str(c).strip() for c in raw.iloc[hdr_idx].values]

emp_code = "IND00313"
target_date_val = "2026-02-20"

# Find row for IND00313 on 2026-02-20
# Note: employee no might be in a column named "Employee No"
emp_col = _find_col(df.columns, COLUMN_MAP["empcode"])
date_col = _find_col(df.columns, COLUMN_MAP["date"])

# Filter rows
target_rows = df[df[emp_col].astype(str).str.upper() == emp_code]

print(f"\n--- Raw Rows for {emp_code} ---")
for idx, row in target_rows.iterrows():
    # Convert date to string for comparison
    d = str(row[date_col]).strip()
    if target_date_val in d:
        print(f"Row {idx} (Date found: {d}):")
        for col in df.columns:
            print(f"  {col}: {row[col]}")
