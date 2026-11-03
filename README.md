MIRACLE HIMS V2 — Clinical Hospital Information Management System

MIRACLE HIMS V2 is a multi-tenant Hospital Information Management System prototype built using Python, Flask, Flask-SQLAlchemy, and PostgreSQL-compatible database architecture.

The project demonstrates integrated clinical, administrative, diagnostic, billing, pharmacy, and patient-document workflows.

Project status: Educational and innovation prototype. It is not certified or approved for production healthcare use.

1. Technology Stack

- Backend: Python and Flask
- ORM: Flask-SQLAlchemy
- Database migrations: Flask-Migrate
- Database: SQLite for local development; PostgreSQL for hosted deployment
- Authentication: Password hashing, session management, CSRF protection
- Frontend: HTML5, CSS3, responsive layouts
- Production server: Gunicorn
- Hosting: Render

2. Implemented Application Features

Organization and Access Management

- Multi-organization data structure
- Organization membership
- Role-based access restrictions
- Organization switching

Patient Management

- Patient registration
- UHID generation
- Patient records and demographic information

Appointment Management

- Appointment scheduling
- Doctor selection
- Patient and doctor overlap checks
- Consultation and follow-up visit types
- Teleconsultation appointment type

OPD Billing

- OPD billing records
- Decimal-based financial calculations
- Payment confirmation workflow
- Bill printing

IPD / ADT

- Bed availability management
- Patient admission
- Patient discharge
- Bed cleaning and housekeeping status

Laboratory and Radiology

- LIS investigation catalogue
- RIS investigation catalogue
- Diagnostic order tracking
- Investigation status updates

Pharmacy

- Medicine inventory
- Batch and expiry information
- Low-stock alerts
- Medicine dispensing records

Electronic Medical Records

- Patient document uploads
- PDF and image file support
- Database binary document storage
- Role-based document access

Teleconsultation

- Appointment-linked demonstration consultation rooms
- External Jitsi meeting links

External meeting links are demonstration functionality and do not independently authenticate users against HIMS accounts.

Email OTP and Notifications

- Email OTP workflow
- SMTP-based email notification utility
- Notification records

Actual email delivery requires valid SMTP configuration.

Simulated AI Assistant

- Clinical query demonstration interface
- Query and response logging

The AI assistant currently generates simulated demonstration responses. It is not a medical diagnostic system.

3. Module Catalogue

The application contains a catalogue of 41 healthcare modules.

The catalogue describes Core, Foundation, and Planned implementation scopes.

Important: A module appearing in the catalogue does not mean that its complete enterprise workflow has already been implemented.

HL7/FHIR enterprise integration is a planned area. This version should not be described as a certified HL7 FHIR implementation.

4. Demo Staff Accounts

The "flask init-demo" command initializes these accounts:

Role| Username
Hospital Admin| admin@miraclehims.org
Doctor| doctor@miraclehims.org
Clinic Staff| demo_clinic
Laboratory Staff| demo_lab
Pharmacist| demo_pharmacist

Passwords must be configured through environment variables:

- "ADMIN_PASSWORD"
- "DOCTOR_PASSWORD"
- "DEMO_CLINIC_PASSWORD"
- "DEMO_LAB_PASSWORD"
- "DEMO_PHARM_PASSWORD"

The application does not provide default passwords.

Warning: The current initialization command resets the passwords of these accounts when run again. Run it only when intentionally initializing or resetting demo accounts.

5. Local Development Setup

Install Python 3.12 and clone the repository.

Install dependencies:

pip install -r requirements.txt

Configure the required environment variables before importing the application:

SECRET_KEY=replace-with-a-long-random-secret

For a new local SQLite database, initialize the database tables:

python -c "from app import app, db; app.app_context().push(); db.create_all()"

This command creates missing tables. It does not migrate or modify existing table structures.

Configure the five demo password environment variables before running the initialization command.

Initialize demo accounts:

flask --app app init-demo

Start the application:

gunicorn app:app

Alternatively, for local development:

flask --app app run

Open:

http://127.0.0.1:5000

6. Render Deployment

The Render Blueprint is configured for:

- Service: "clinical-hims-demo"
- Branch: "hims-v2-development"
- Runtime: Python
- Server: Gunicorn

The existing Render service must retain its correct "DATABASE_URL" and "SECRET_KEY" environment variables.

Before deploying a new application schema to an existing database, prepare and verify database migrations.

The current repository does not yet include a verified migration history. Do not assume that "db.create_all()" can upgrade an existing database.

7. Environment Variables

Variable| Purpose
"SECRET_KEY"| Flask session security
"DATABASE_URL"| Database connection
"SMTP_SERVER"| SMTP host
"SMTP_PORT"| SMTP port
"SMTP_USER"| SMTP username
"SMTP_PASSWORD"| SMTP password
"DEMO_CLINIC_PASSWORD"| Clinic demo account
"DEMO_LAB_PASSWORD"| Laboratory demo account
"DEMO_PHARM_PASSWORD"| Pharmacy demo account
"ADMIN_PASSWORD"| Admin demo account
"DOCTOR_PASSWORD"| Doctor demo account
"DEMO_ORG_NAME"| Demo organization name

Never commit secret values to GitHub.

8. Security and Data Protection Limitations

This is an educational prototype.

- Do not enter real patient information.
- Use synthetic demonstration records only.
- File signature checks do not replace malware scanning.
- External Jitsi meeting links are not equivalent to authenticated healthcare video infrastructure.
- Simulated AI responses must not be used for medical decisions.
- Database migrations, backups, monitoring, privacy controls, and independent security testing are required before any real-world deployment.

9. Repository

GitHub repository:

https://github.com/sakshamtomar-svg/clinical-hims

Development branch:

"hims-v2-development"