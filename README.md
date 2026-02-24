# Aquera Attendance System

A powerful, intuitive internal web application designed to track employee attendance, calculate precise working hours by merging **ESSL** (punch machine) and **Login-Logout** (portal) data, and flag any abnormal attendance patterns automatically.

---

## 🚀 Quick Start / How to Use

### 1. Uploading Data
The very first step is to feed the application your raw attendance data.

1. Navigate to the **Upload** page from the top navigation bar.
2. Select **ESSL Punch Data (.csv, .xlsx, or .xls)** from the dropdown and upload your biometric punch file.
3. Next, select **Login/Logout Data (.xlsx or .xls)** and upload the portal login sheet.
4. Once both are uploaded, the system will instantly process the data and redirect you to the Dashboard.

> **Note:** If no data is uploaded, the app will automatically try to pull files named `essl_punch.csv` and `login_logout.xlsx` from your computer's `Downloads` folder!

![Upload Page Screenshot](./screenshots/upload_page.png) *(Placeholder: add an image of the upload page here)*

---

### 2. The Dashboard Overview
Once data is loaded, the **Dashboard** is your primary command center.

- **KPI Cards:** At the top, you'll see quick metrics like Total Employees, Average Present %, Absent Count, and Late Count.
- **Visual Charts:** Three charts provide a visual breakdown of your last 7 working days:
  - **Attendance Split:** A doughnut chart showing Present vs Absent vs Late.
  - **Daily Attendance:** A bar graph showing the exact number of people present and absent day by day.
  - **Late Trend:** A line graph demonstrating if tardiness is increasing or decreasing.
- **Daily Breakdown Table:** A simple table at the bottom showing exact numbers for each day of the configured window, including nicely formatted "**Rest Day**" badges for weekends.

![Dashboard Screenshot](./screenshots/dashboard.png) *(Placeholder: add an image of the dashboard here)*

---

### 3. Reviewing All Employees
To see a summary of everyone's performance, head to the **Employees** page.

1. The table outlines every individual's summary over the processing window.
2. It includes their **Present Days**, **Absent Days**, **Late Count**, **Short Hrs**, and **Average Duration**.
3. **Filtering:** You can use the search bar or column dropdowns to filter by Department, Category, or Status.
4. **Export Data:** Click the green "**Export Excel**" button in the top right to instantly download the table data as a formatted `.xlsx` file.

![Employees List Screenshot](./screenshots/employees_list.png) *(Placeholder: add an image of the employee list here)*

---

### 4. Viewing Individual Weekly Reports (The Modal)
If you want to understand *why* an employee is marked late or short on hours, click deeply into their data:

1. On either the Employees page or Abnormal page, simply **click on an employee's name (in blue)**.
2. A fast, animated popup overlay (Modal) will appear without needing to leave the page.
3. This popup breaks down the employee's **exact In-Times, Out-Times, and Hours Worked** for the last 7 working days so you can verify the status given to them.

![Employee Detail Modal Screenshot](./screenshots/employee_modal.png) *(Placeholder: add an image of the modal pop-up here)*

---

### 5. Managing Abnormal / High-Risk Employees
The **Abnormal** page is designed to save HR time by automatically bubbling up troublesome attendance patterns based on predefined rules.

- Employees are assigned a **Risk Level** (Normal, Warning, High Risk, Critical) based on factors like consecutive absences, extreme tardiness, or missing punch-outs.
- **Selective Exporting:** Want to only send "Critical" and "High Risk" individuals to management? 
  1. Click the **Selective Export** button.
  2. The options panel will slide out.
  3. Uncheck "Normal" and "Warning".
  4. Click the smaller **Export Excel** button to download a customized report.

![Selective Export Feature](./screenshots/selective_export.png) *(Placeholder: add an image of the selective export animation open)*

---

## ⚙️ Settings & Configuration
The system allows you to manage mappings. Navigate to the **Settings** page to define how category abbreviations (like "IND" or "1500") map to human-readable names (e.g., "India Series").

> **Hosting on Vercel?**
> The application is pre-configured with a `vercel.json` file. The backend automatically switches to using Vercel's temporary serverless storage (`/tmp`) for file uploads seamlessly when it detects the `VERCEL=1` environment variable.

---

### Technical Stack
- **Backend:** Python, Flask, Pandas (for heavy data merging/processing)
- **Frontend:** HTML5, Bootstrap 5, Vanilla JS, Chart.js, DataTables
- **Exporting Engine:** OpenPyXL (Excel integration)
