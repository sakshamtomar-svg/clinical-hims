MIRACLE HIMS V2 — Hinglish Setup Guide

MIRACLE HIMS V2 ek multi-tenant Hospital Information Management System prototype hai, jo Python, Flask, Flask-SQLAlchemy aur PostgreSQL-compatible database architecture par based hai.

Iska objective hospital ke different departments ke clinical aur administrative workflows ko ek integrated system mein demonstrate karna hai.

Project status: Educational innovation prototype. Ye certified production healthcare software nahi hai.

1. Technology Stack

- Backend: Python + Flask
- Database ORM: Flask-SQLAlchemy
- Database migration support: Flask-Migrate
- Local database: SQLite
- Hosted database: PostgreSQL
- Frontend: HTML, CSS aur responsive interface
- Security: Password hashing, session management aur CSRF protection
- Hosting: Render
- Production server: Gunicorn

2. Implemented Modules

Organization Management

- Multiple organization structure
- Organization membership
- Role-based access
- Organization switching

Patient Management

- Patient registration
- UHID generation
- Patient demographic records

Appointment Management

- Doctor selection
- Patient selection
- Appointment scheduling
- Appointment overlap checks
- Consultation aur follow-up visit types

OPD Billing

- OPD bills
- Decimal-based calculations
- Payment confirmation
- Bill printing

IPD / ADT

- Bed management
- Patient admission
- Patient discharge
- Bed cleaning status

LIS / RIS

- Laboratory investigations
- Radiology investigations
- Diagnostic order tracking
- Investigation status updates

Pharmacy

- Medicine inventory
- Batch details
- Expiry tracking
- Low-stock alerts
- Medicine dispensing records

EMR

- Patient document uploads
- PDF aur image support
- Database binary storage
- Role-based document access

Teleconsultation

- Appointment-linked Jitsi demo rooms
- External meeting links

Dhyan rahe: External Jitsi link HIMS ke login system se independently authenticate nahi hota.

Email OTP

- Email OTP workflow
- SMTP email utility
- Notification records

Email delivery ke liye valid SMTP credentials configure karne honge.

AI Assistant

- Clinical query demonstration
- Simulated responses
- Query aur response logging

Ye actual AI diagnostic engine nahi hai. Iska output medical decision-making ke liye use nahi karna hai.

3. 41-Module Catalogue

Application mein 41 healthcare modules ka catalogue hai.

Modules ko Core, Foundation aur Planned implementation scopes mein organize kiya gaya hai.

Catalogue mein module listed hone ka matlab ye nahi hai ki uska complete workflow implement ho chuka hai.

HL7/FHIR enterprise integration future development scope hai. Current version ko certified FHIR implementation nahi kehna chahiye.

4. Demo Accounts

"flask init-demo" command ye demo accounts initialize karta hai:

Role| Username
Admin| admin@miraclehims.org
Doctor| doctor@miraclehims.org
Clinic| demo_clinic
Lab| demo_lab
Pharmacist| demo_pharmacist

Passwords environment variables se set karne honge:

ADMIN_PASSWORD
DOCTOR_PASSWORD
DEMO_CLINIC_PASSWORD
DEMO_LAB_PASSWORD
DEMO_PHARM_PASSWORD

Application mein default demo passwords available nahi hain.

Important: "init-demo" dobara chalane par existing demo accounts ke passwords reset ho sakte hain. Isliye ise sirf intentional initialization ya password reset ke waqt run karein.

5. Local Setup — Windows

Python 3.12 install karein.

Repository clone/download karein.

PowerShell mein project folder open karein.

Virtual environment banayein:

py -m venv .venv

Activate karein:

.venv\Scripts\activate

Dependencies install karein:

pip install -r requirements.txt

Application run karne se pehle "SECRET_KEY" configure karein:

$env:SECRET_KEY="replace-with-a-long-random-secret"

Fresh local SQLite database ke tables create karein:

python -c "from app import app, db; app.app_context().push(); db.create_all()"

Ye command missing tables create karti hai. Existing tables ka schema upgrade nahi karti.

Ab demo passwords ke five environment variables configure karein.

Demo accounts initialize karein:

flask --app app init-demo

Application start karein:

flask --app app run

Browser mein open karein:

http://127.0.0.1:5000

6. Render Deployment

Render configuration:

- Service name: "clinical-hims-demo"
- Deployment branch: "hims-v2-development"
- Runtime: Python
- Server: Gunicorn

Render dashboard mein existing "DATABASE_URL" aur "SECRET_KEY" verify karein.

Existing database par new application schema deploy karne se pehle migration plan banana zaroori hai.

Current repository mein verified migration history available nahi hai. Sirf "db.create_all()" se existing database schema upgrade nahi hota.

7. Environment Variables

Variable| Purpose
"SECRET_KEY"| Session security
"DATABASE_URL"| Database connection
"SMTP_SERVER"| Email server
"SMTP_PORT"| Email server port
"SMTP_USER"| SMTP username
"SMTP_PASSWORD"| SMTP password
"DEMO_CLINIC_PASSWORD"| Clinic account
"DEMO_LAB_PASSWORD"| Lab account
"DEMO_PHARM_PASSWORD"| Pharmacist account
"ADMIN_PASSWORD"| Admin account
"DOCTOR_PASSWORD"| Doctor account
"DEMO_ORG_NAME"| Organization name

Kisi bhi password ya secret ko GitHub par upload na karein.

8. Security Limitations

Ye educational prototype hai.

- Real patient data use na karein.
- Sirf synthetic demo records use karein.
- File signature verification malware scanning ka replacement nahi hai.
- External Jitsi links fully authenticated healthcare video infrastructure nahi hain.
- Simulated AI responses medical advice nahi hain.
- Real-world use se pehle database migrations, backups, monitoring, privacy controls aur independent security testing zaroori hai.

9. GitHub Repository

https://github.com/sakshamtomar-svg/clinical-hims

Development branch:

"hims-v2-development"