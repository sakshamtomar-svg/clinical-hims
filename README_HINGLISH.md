# Clinical HIMS — Online Website Starter
This starter includes a responsive website, login system, patient registration (UHID), appointment booking, ATD bed status tracking, LIS/RIS lab diagnostics, EMR camera/file uploads, a recruitment portal, a database, and audit events. It features a responsive layout designed for laptops, smart boards, and mobile browsers.


## Public URL kaise milega
Main yahan se tumhare hosting account mein deploy karke live URL create nahi kar sakta. Is ZIP ko apne GitHub repository mein upload karke Render par deploy karna hoga. `render.yaml` deployment blueprint ke roop mein diya hai. Hosting/database ki current free-tier availability aur charges deploy karne se pehle confirm karna.

## Local run (Windows)
1. Python 3.11+ install karo.
2. ZIP extract karo, folder mein PowerShell kholo.
3. `py -m venv .venv`
4. `.venv\\Scripts\\activate`
5. `pip install -r requirements.txt`
6. `flask --app app init-demo`
7. `flask --app app run`
8. Browser mein `http://127.0.0.1:5000` kholo.

## Demo login (local starter defaults)
Patient: `demo_patient` / `PatientDemo-ChangeMe!`
Clinic: `demo_clinic` / `ClinicDemo-ChangeMe!`

First local run par demo users banane ke liye `flask --app app init-demo` chalao. Public website par deploy karne se pehle passwords change karo; public judges ke liye superuser/admin account share mat karo. Environment variables `DEMO_PATIENT_PASSWORD` aur `DEMO_CLINIC_PASSWORD` set karke init-demo users ke passwords override kiye ja sakte hain.

## Main workflows
- Patient login → appointment book
- Clinic login → appointment appears in same database → update status
- Patient login → updated status visible
- FHIR-style endpoints: `/api/fhir/Patient` and `/api/fhir/Appointment` (login required)
- ATD Management: Monitor ward bed availability (Vacant, Occupied, Housekeeping) and manage patient admissions and discharges.
​- LIS/RIS Diagnostics: Place lab investigation and radiology scan orders, and track sample/result statuses.
- EMR & Camera Uploads: Use your mobile or desktop camera to directly capture prescriptions or lab reports and attach them to the EMR.
- Recruitment Portal: Manage active hospital job openings, department vacancies, and staff applications 

## Important security limits
CSRF protection is enabled for web forms. This is an early NEEEV demo, NOT production healthcare software. Do not enter real patient data. FHIR-style JSON is not full HL7 FHIR conformance or certification. Before exposing publicly, implement and test patient ownership and clinic/organization isolation, rate limiting, rate limiting, account lockout, stronger session/cookie configuration, database backup/restore, monitoring, consent controls, and independent security review. Demo accounts use default passwords until you change them. Do not use this starter for real clinical decisions or real patients.
