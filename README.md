# Clinical Hospital Information Management System (HIMS)

An enterprise-grade clinical workflow and patient management prototype built with Flask, SQLAlchemy, and a modern responsive frontend.

## 🚀 Key Modules Integrated
- **Patient Registration & UHID:** Fast patient intake, demographic data mapping, and unique hospital identification generation.
- **ATD Bed Management:** Real-time ward bed status tracking (Vacant, Occupied, Housekeeping) for ICU, CCU, Isolation, and Double Bedded wards.
- **LIS & RIS Diagnostics:** Laboratory test and radiology scan ordering, sample acknowledgement, and result status workflows.
- **EMR & Camera Uploads:** Direct mobile/desktop camera capture or document uploads (PDF/Images) for prescriptions and lab reports attached directly to electronic medical records.
- **Hospital Recruitment Portal:** Manage active department job openings, vacancies, and staff applications.

## 🛠️ Tech Stack
- **Backend:** Python, Flask, Flask-SQLAlchemy, Flask-WTF, Gunicorn
- **Database:** SQLite (Local) / PostgreSQL (Render Production)
- **Frontend:** HTML5, CSS3, Responsive Grid Layout
- **Deployment:** Render (via GitHub `hims` branch)

## 📌 Demo Accounts
- **Patient Portal:** `demo_patient` / `PatientDemo-ChangeMe!`
- **Clinic Staff:** `demo_clinic` / `ClinicDemo-ChangeMe!`
- **Lab Department:** `demo_lab` / `LabDemo-ChangeMe!`
