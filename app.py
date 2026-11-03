import os
import html
import math
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import secrets
import uuid
from datetime import datetime, timedelta, timezone, date
from functools import wraps
from flask import Flask, request, redirect, url_for, session, flash, abort, send_file, render_template_string
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import generate_password_hash, check_password_hash
from io import BytesIO

app = Flask(__name__)

# Strict Fail-Fast Security Check for SECRET_KEY
secret_key = os.environ.get("SECRET_KEY")
if not secret_key:
    raise RuntimeError("CRITICAL SECURITY ERROR: SECRET_KEY environment variable is mandatory and missing!")

app.config.update(
    SECRET_KEY=secret_key,
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    MAX_CONTENT_LENGTH=8 * 1024 * 1024,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("RENDER", "") == "true",
)

# Production PostgreSQL Database URL Configuration
db_url = os.environ.get("DATABASE_URL", "sqlite:///clinical_hims.db")
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = db_url

db = SQLAlchemy(app)
migrate = Migrate(app, db)
csrf = CSRFProtect(app)

IST = timezone(timedelta(hours=5, minutes=30))

# --- SECURE SMTP EMAIL DISPATCH UTILITY WITH SOCKET SAFETY ---
def send_real_email_notification(recipient_email, subject, body_text):
    smtp_server = os.environ.get("SMTP_SERVER", "")
    smtp_port = int(os.environ.get("SMTP_PORT", 587))
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_password = os.environ.get("SMTP_PASSWORD", "")
    
    if not smtp_server or not smtp_user or not smtp_password:
        print("[SMTP WARNING] Credentials not configured. Email dispatch skipped.")
        return False
        
    server = None
    try:
        msg = MIMEMultipart()
        msg['From'] = smtp_user
        msg['To'] = recipient_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body_text, 'plain'))
        
        server = smtplib.SMTP(smtp_server, smtp_port, timeout=10)
        server.starttls()
        server.login(smtp_user, smtp_password)
        server.sendmail(smtp_user, recipient_email, msg.as_string())
        return True
    except Exception as e:
        print(f"[SMTP ERROR] Failed to send email notification.")
        return False
    finally:
        if server:
            try:
                server.quit()
            except Exception:
                pass

# --- ENTERPRISE DATABASE MODELS ---

class User(db.Model):
    __tablename__ = "user"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(30), nullable=False)
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Organization(db.Model):
    __tablename__ = "mh_organizations"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(140), nullable=False)
    org_type = db.Column(db.String(30), default="Hospital")
    active = db.Column(db.Boolean, default=True)

class Membership(db.Model):
    __tablename__ = "mh_memberships"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    org_id = db.Column(db.Integer, db.ForeignKey("mh_organizations.id"), nullable=False)
    role = db.Column(db.String(30), nullable=False)
    org = db.relationship("Organization")
    __table_args__ = (db.UniqueConstraint("user_id", "org_id", name="uq_mh_membership"),)

class Patient(db.Model):
    __tablename__ = "mh_patients"
    id = db.Column(db.Integer, primary_key=True)
    org_id = db.Column(db.Integer, db.ForeignKey("mh_organizations.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, unique=True)
    uhid = db.Column(db.String(40), nullable=False, unique=True, index=True)
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), default="")
    gender = db.Column(db.String(20), default="")
    dob = db.Column(db.String(10), default="")
    mobile = db.Column(db.String(20), default="")
    email = db.Column(db.String(140), default="")
    address = db.Column(db.String(300), default="")
    payer_type = db.Column(db.String(40), default="Self Pay")
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    org = db.relationship("Organization")

class Doctor(db.Model):
    __tablename__ = "mh_doctors"
    id = db.Column(db.Integer, primary_key=True)
    org_id = db.Column(db.Integer, db.ForeignKey("mh_organizations.id"), nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    department = db.Column(db.String(80), nullable=False)
    active = db.Column(db.Boolean, default=True)
    org = db.relationship("Organization")

class Bed(db.Model):
    __tablename__ = "mh_beds"
    id = db.Column(db.Integer, primary_key=True)
    org_id = db.Column(db.Integer, db.ForeignKey("mh_organizations.id"), nullable=False, index=True)
    ward = db.Column(db.String(80), nullable=False)
    category = db.Column(db.String(60), default="General")
    bed_no = db.Column(db.String(30), nullable=False)
    status = db.Column(db.String(30), default="Vacant")
    patient_id = db.Column(db.Integer, db.ForeignKey("mh_patients.id"), nullable=True)
    __table_args__ = (db.UniqueConstraint("org_id", "bed_no", name="uq_mh_bed"),)

class Admission(db.Model):
    __tablename__ = "mh_admissions"
    id = db.Column(db.Integer, primary_key=True)
    org_id = db.Column(db.Integer, db.ForeignKey("mh_organizations.id"), nullable=False, index=True)
    patient_id = db.Column(db.Integer, db.ForeignKey("mh_patients.id"), nullable=False)
    bed_id = db.Column(db.Integer, db.ForeignKey("mh_beds.id"), nullable=False)
    admitted_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    discharged_at = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(20), default="Admitted")
    patient = db.relationship("Patient")
    bed = db.relationship("Bed")
    __table_args__ = (
        db.Index('idx_unique_active_admission', 'org_id', 'patient_id', unique=True, 
                 postgresql_where=db.text("status = 'Admitted'"), 
                 sqlite_where=db.text("status = 'Admitted'")),
    )

class DepartmentTestCatalog(db.Model):
    __tablename__ = "mh_test_catalog"
    id = db.Column(db.Integer, primary_key=True)
    org_id = db.Column(db.Integer, db.ForeignKey("mh_organizations.id"), nullable=True, index=True)
    category = db.Column(db.String(30), nullable=False)
    sub_department = db.Column(db.String(50), nullable=False)
    test_name = db.Column(db.String(150), nullable=False)
    price = db.Column(db.Numeric(10, 2), default=Decimal('0.00'))

class DiagnosticOrder(db.Model):
    __tablename__ = "mh_diagnostic_orders"
    id = db.Column(db.Integer, primary_key=True)
    org_id = db.Column(db.Integer, db.ForeignKey("mh_organizations.id"), nullable=False, index=True)
    patient_id = db.Column(db.Integer, db.ForeignKey("mh_patients.id"), nullable=False)
    order_no = db.Column(db.String(40), unique=True, nullable=False)
    modality = db.Column(db.String(10), default="LIS")
    sub_department = db.Column(db.String(50), default="Biochemistry")
    service = db.Column(db.String(150), nullable=False)
    status = db.Column(db.String(40), default="Order Generated")
    result_text = db.Column(db.Text, default="")
    verified_by = db.Column(db.String(100), default="")
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    patient = db.relationship("Patient")

class Appointment(db.Model):
    __tablename__ = "mh_appointments"
    id = db.Column(db.Integer, primary_key=True)
    org_id = db.Column(db.Integer, db.ForeignKey("mh_organizations.id"), nullable=False, index=True)
    patient_id = db.Column(db.Integer, db.ForeignKey("mh_patients.id"), nullable=False)
    doctor_id = db.Column(db.Integer, db.ForeignKey("mh_doctors.id"), nullable=True)
    doctor_name = db.Column(db.String(120), default="General Physician")
    department = db.Column(db.String(100), default="General Medicine")
    visit_type = db.Column(db.String(30), default="Consultation")
    start_at = db.Column(db.DateTime(timezone=True), nullable=False)
    reason = db.Column(db.String(250), default="")
    status = db.Column(db.String(30), default="Booked")
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    patient = db.relationship("Patient")
    doctor = db.relationship("Doctor")

class Teleconsultation(db.Model):
    __tablename__ = "mh_teleconsultations"
    id = db.Column(db.Integer, primary_key=True)
    org_id = db.Column(db.Integer, db.ForeignKey("mh_organizations.id"), nullable=False, index=True)
    appointment_id = db.Column(db.Integer, db.ForeignKey("mh_appointments.id"), nullable=False)
    room_token = db.Column(db.String(100), nullable=False, unique=True)
    status = db.Column(db.String(30), default="Scheduled")
    appointment = db.relationship("Appointment", backref="teleconsultations")

class EmailOTP(db.Model):
    __tablename__ = "mh_email_otps"
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(140), nullable=False, index=True)
    ip_address = db.Column(db.String(50), default="")
    otp_hash = db.Column(db.String(255), nullable=False)
    attempts = db.Column(db.Integer, default=0)
    expires_at = db.Column(db.DateTime, nullable=False)
    verified = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

class LoginAttempt(db.Model):
    __tablename__ = "mh_login_attempts"
    id = db.Column(db.Integer, primary_key=True)
    identifier = db.Column(db.String(140), nullable=False, index=True)
    ip_address = db.Column(db.String(50), nullable=False, index=True)
    attempts = db.Column(db.Integer, default=1)
    lockout_until = db.Column(db.DateTime, nullable=True)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

class NotificationLog(db.Model):
    __tablename__ = "mh_notifications"
    id = db.Column(db.Integer, primary_key=True)
    org_id = db.Column(db.Integer, nullable=False, index=True)
    recipient = db.Column(db.String(140), nullable=False)
    channel = db.Column(db.String(20), nullable=False)
    message = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default="Sent")
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

class AIAssistantLog(db.Model):
    __tablename__ = "mh_ai_logs"
    id = db.Column(db.Integer, primary_key=True)
    org_id = db.Column(db.Integer, nullable=False, index=True)
    user_type = db.Column(db.String(30), default="Doctor")
    query = db.Column(db.Text, nullable=False)
    ai_response = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

class MedicalDocument(db.Model):
    __tablename__ = "mh_documents"
    id = db.Column(db.Integer, primary_key=True)
    org_id = db.Column(db.Integer, db.ForeignKey("mh_organizations.id"), nullable=False, index=True)
    patient_id = db.Column(db.ForeignKey("mh_patients.id"), nullable=False)
    original_name = db.Column(db.String(255), nullable=False)
    mime_type = db.Column(db.String(100), default="application/octet-stream")
    data = db.Column(db.LargeBinary, nullable=False)
    uploaded_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    patient = db.relationship("Patient")

class AuditEvent(db.Model):
    __tablename__ = "mh_audit_events"
    id = db.Column(db.Integer, primary_key=True)
    org_id = db.Column(db.Integer, nullable=False, index=True)
    user_id = db.Column(db.Integer, nullable=True)
    action = db.Column(db.String(100), nullable=False)
    resource = db.Column(db.String(100), default="")
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

class OPDBill(db.Model):
    __tablename__ = "mh_opd_bills"
    id = db.Column(db.Integer, primary_key=True)
    org_id = db.Column(db.Integer, db.ForeignKey("mh_organizations.id"), nullable=False, index=True)
    patient_id = db.Column(db.Integer, db.ForeignKey("mh_patients.id"), nullable=False)
    bill_no = db.Column(db.String(40), unique=True, nullable=False)
    consultation_fee = db.Column(db.Numeric(10, 2), default=Decimal('500.00'))
    tax_rate = db.Column(db.Numeric(5, 2), default=Decimal('5.00'))
    tax_amount = db.Column(db.Numeric(10, 2), default=Decimal('0.00'))
    total_amount = db.Column(db.Numeric(10, 2), default=Decimal('525.00'))
    payment_mode = db.Column(db.String(30), default="Cash")
    status = db.Column(db.String(30), default="Pending")
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    patient = db.relationship("Patient")

class PharmacyInventory(db.Model):
    __tablename__ = "mh_pharmacy_inventory"
    id = db.Column(db.Integer, primary_key=True)
    org_id = db.Column(db.Integer, db.ForeignKey("mh_organizations.id"), nullable=False, index=True)
    medicine_name = db.Column(db.String(150), nullable=False)
    batch_no = db.Column(db.String(50), nullable=False)
    expiry_date = db.Column(db.String(10), default="")
    stock_qty = db.Column(db.Integer, default=100)
    unit_price = db.Column(db.Numeric(10, 2), default=Decimal('0.00'))
    min_stock_alert = db.Column(db.Integer, default=10)

class PharmacyDispense(db.Model):
    __tablename__ = "mh_pharmacy_dispense"
    id = db.Column(db.Integer, primary_key=True)
    org_id = db.Column(db.Integer, db.ForeignKey("mh_organizations.id"), nullable=False, index=True)
    patient_id = db.Column(db.Integer, db.ForeignKey("mh_patients.id"), nullable=False)
    inventory_id = db.Column(db.Integer, db.ForeignKey("mh_pharmacy_inventory.id"), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    total_price = db.Column(db.Numeric(10, 2), nullable=False)
    dispensed_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    patient = db.relationship("Patient")
    inventory = db.relationship("PharmacyInventory")

MODULES = [
    ("Patient Registration & UHID", "Patient demographics, unique UHID generation and multi-tenant scoping.", "Core"),
    ("Appointment & Queue Scheduling", "Doctor diaries, department filtering, walk-in queue and time-window collision checks.", "Core"),
    ("OPD Billing", "Consultation charges, Decimal tax calculation, manual demo payment confirmation workflow.", "Foundation"),
    ("IPD ADT Module", "Admission, bed management, transfers and discharge workflow with housekeeping.", "Core"),
    ("IPD Billing", "Room rent, nursing, consumables and package billing workflow.", "Foundation"),
    ("Corporate & TPA Insurance Billing", "Payer packages, pre-authorisation and co-pay workflow.", "Foundation"),
    ("Referral & Marketing Management", "Referral sources, campaigns and follow-up tracking.", "Planned"),
    ("Helpdesk & Enquiry Desk", "Hospital directory, room locations and visitor enquiry workflow.", "Planned"),
    ("Patient Portal & Mobile App Integration", "Patient-facing appointment booking and medical records access.", "Foundation"),
    ("EMR & Database Blob Storage", "Longitudinal clinical record and secure database-backed file attachments.", "Core"),
    ("OP Clinical Management System", "Vitals, clinical assessments and diagnosis coding.", "Foundation"),
    ("CPOE", "Computerised lab, imaging and medication order entry.", "Foundation"),
    ("Nurse Workbench", "Vitals monitoring, intake/output logs and nursing task allocation.", "Planned"),
    ("A&E / Trauma", "Emergency triage, resus tracking and fast-track encounter workflow.", "Planned"),
    ("OT Management", "Operation theatre scheduling, surgical checklist and team assignment.", "Planned"),
    ("Electronic Prescription (eRx)", "Structured prescription workflow with drug database integration.", "Foundation"),
    ("CDSS", "Clinical alerts and decision-support rules engine.", "Planned"),
    ("Day Care Management", "Day-care visit, minor procedure and short-stay workflow.", "Planned"),
    ("Labour & Delivery Suite", "Maternal monitoring, partograph and neonatal care workflow.", "Planned"),
    ("Advanced LIS", "Biochemistry, Molecular, Immunology, Hematology strict workflow orders.", "Core"),
    ("RIS & PACS", "X-Ray, CT, MRI, USG radiology order and reporting workflow.", "Core"),
    ("Blood Bank", "Donor screening, component separation and cross-match workflow.", "Planned"),
    ("Pharmacy (Retail & IPD)", "Dispensing, batch tracking, expiry validation, alerts and stock inventory workflow.", "Foundation"),
    ("MRD", "Medical records archiving, ICD coding and release workflow.", "Planned"),
    ("Dietetics & Kitchen", "Therapeutic diet orders and kitchen meal delivery workflow.", "Planned"),
    ("Physiotherapy & Rehabilitation", "Therapy session scheduling and progress notes.", "Planned"),
    ("Purchase Management", "Vendor management, quotation comparison and purchase orders.", "Planned"),
    ("Store & Department Inventory", "Stock indents, issues and reorder level alerts.", "Planned"),
    ("Asset & Equipment Maintenance", "Biomedical equipment register and preventive maintenance schedule.", "Planned"),
    ("CSSD", "Sterilisation batch tracking and instrument kit sterilisation.", "Planned"),
    ("Housekeeping & Facility Management", "Cleaning schedules, infection control audits and maintenance tickets.", "Core"),
    ("Laundry & Linen", "Linen issue, return, washing and disinfection workflow.", "Planned"),
    ("Top Management MIS & Dashboard", "Operational KPIs, occupancy rates, and revenue analytics dashboard.", "Core"),
    ("Mobility Solutions & Enterprise Portals", "Responsive staff portal and secure internal messaging.", "Foundation"),
    ("Enterprise Integration Engine (HL7/FHIR)", "Standardized health data exchange interface design.", "Planned"),
    ("Health IoT & Medical Device Integration", "Direct medical device and monitor feed integration.", "Planned"),
    ("Quality Management & NABH Compliance", "Quality indicators, incident reporting and audit checklists.", "Planned"),
    ("HR & Payroll", "Staff roster, attendance, leave management and payroll processing.", "Planned"),
    ("Financial Accounting & General Ledger", "Chart of accounts, vouchers, ledger and financial statements.", "Planned"),
    ("Security, RBAC & Audit Trails", "Role-based access control, organization scoping and tamper-evident audit logs.", "Core"),
    ("Telehealth & Virtual Consultation", "Unique Jitsi Room Link – Demo (External Redirect).", "Core"),
]

def who():
    uid = session.get("uid")
    return db.session.get(User, uid) if uid else None

def membership():
    u = who()
    if not u:
        return None
    active_org_id = session.get("active_org_id")
    if active_org_id:
        m = Membership.query.join(Organization).filter(
            Membership.user_id == u.id, 
            Membership.org_id == active_org_id, 
            Organization.active == True
        ).first()
        if m:
            return m
    return None

def org_id():
    m = membership()
    return m.org_id if m else None

@app.before_request
def enforce_org_status():
    u = who()
    active_org_id = session.get("active_org_id")
    if u and active_org_id:
        org = db.session.get(Organization, active_org_id)
        if not org or not org.active:
            session.clear()
            flash("Your organization account has been deactivated by administrator.")
            return redirect(url_for("login"))

def log_action(action, resource=""):
    m = membership()
    u = who()
    if m and u:
        db.session.add(AuditEvent(org_id=m.org_id, user_id=u.id, action=action, resource=resource))

def login_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not who():
            return redirect(url_for("login"))
        if not membership():
            abort(403)
        return fn(*args, **kwargs)
    return wrapped

def staff_required(fn):
    @wraps(fn)
    @login_required
    def wrapped(*args, **kwargs):
        if membership().role not in ("clinic", "admin", "lab", "doctor", "nurse", "pharmacist"):
            abort(403)
        return fn(*args, **kwargs)
    return wrapped

def doctor_required(fn):
    @wraps(fn)
    @login_required
    def wrapped(*args, **kwargs):
        if membership().role not in ("doctor", "admin"):
            abort(403)
        return fn(*args, **kwargs)
    return wrapped

def lab_required(fn):
    @wraps(fn)
    @login_required
    def wrapped(*args, **kwargs):
        if membership().role not in ("lab", "admin"):
            abort(403)
        return fn(*args, **kwargs)
    return wrapped

def pharmacist_required(fn):
    @wraps(fn)
    @login_required
    def wrapped(*args, **kwargs):
        if membership().role not in ("pharmacist", "admin"):
            abort(403)
        return fn(*args, **kwargs)
    return wrapped

def billing_staff_required(fn):
    @wraps(fn)
    @login_required
    def wrapped(*args, **kwargs):
        if membership().role not in ("admin", "clinic"):
            abort(403)
        return fn(*args, **kwargs)
    return wrapped

def allowed_file_with_signature(file_storage):
    if not file_storage or not file_storage.filename:
        return False
    filename = file_storage.filename
    if '.' not in filename:
        return False
    ext = filename.rsplit('.', 1)[1].lower()
    if ext not in {'png', 'jpg', 'jpeg', 'pdf'}:
        return False
    
    header = file_storage.read(12)
    file_storage.seek(0)
    
    is_pdf = header.startswith(b'%PDF')
    is_png = header.startswith(b'\x89PNG\r\n\x1a\n')
    is_jpeg = header.startswith(b'\xff\xd8\xff')
    
    if ext == 'pdf' and not is_pdf:
        return False
    if ext == 'png' and not is_png:
        return False
    if ext in {'jpg', 'jpeg'} and not is_jpeg:
        return False
    return True

def page(body, **context):
    u = who()
    user_memberships = Membership.query.join(Organization).filter(
        Membership.user_id == u.id, 
        Organization.active == True
    ).all() if u else []
    current_org = Organization.query.get(org_id()) if org_id() else None
    return render_template_string(BASE, body=render_template_string(body, **context), user=u, role=membership().role if membership() else "", user_memberships=user_memberships, current_org=current_org)

BASE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>MIRACLE HIMS - Enterprise Edition</title><style>
:root{--teal:#087e8b;--ink:#173344;--muted:#637783;--line:#dce7eb;--bg:#f8fafc;--card-bg:#ffffff;--accent:#20b2aa}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 Arial,sans-serif}
nav{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;padding:14px 4%;background:#fff;border-bottom:1px solid var(--line);box-shadow:0 1px 3px rgba(0,0,0,0.05)}
nav a{color:var(--ink);text-decoration:none;margin:0 6px;font-weight:500;transition:color 0.2s}
nav a:hover{color:var(--teal)}.brand{font-size:1.3rem;font-weight:800;color:var(--teal)}
main{width:min(1280px,94%);margin:28px auto;min-height:75vh}.hero,.card,.formcard{background:var(--card-bg);border:1px solid var(--line);border-radius:14px;padding:24px;margin-bottom:18px;box-shadow:0 2px 4px rgba(0,0,0,0.02)}
.hero{background:linear-gradient(135deg,#e0f7fa,#e8efff)}h1{font-size:clamp(1.8rem,4vw,2.4rem);line-height:1.15;color:var(--ink)}
p,small{color:var(--muted)}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:16px}
button,.btn{background:var(--teal);color:#fff;border:0;border-radius:8px;padding:10px 16px;text-decoration:none;font-weight:bold;cursor:pointer;transition:background 0.2s}
button:hover,.btn:hover{background:#065a63}
input,select,textarea{width:100%;padding:10px 12px;border:1px solid var(--line);border-radius:8px;margin:6px 0 14px;font:inherit;background:#fff}
label{font-weight:600;font-size:0.9rem;color:var(--ink)}.tablewrap{overflow-x:auto}table{width:100%;border-collapse:collapse;min-width:700px}th,td{text-align:left;padding:12px 10px;border-bottom:1px solid var(--line)}
th{background:#f1f5f9;font-weight:700;color:var(--ink)}.notice{padding:12px;background:#fef3c7;border-left:4px solid #f59e0b;border-radius:6px;margin:14px 0;color:#92400e}
.muted{color:var(--muted)}.pill{display:inline-block;padding:4px 10px;border-radius:20px;background:#e0f2fe;color:#0369a1;font-size:.75rem;font-weight:700}
footer{text-align:center;padding:24px;color:var(--muted);font-size:0.9rem;border-top:1px solid var(--line);margin-top:40px}.search{max-width:440px}
@media(max-width:768px){nav{flex-direction:column;align-items:flex-start}nav div{display:flex;flex-wrap:wrap;margin-top:8px}main{width:96%}}
</style></head><body>
<nav><a class="brand" href="/">MIRACLE HIMS</a><div>
{% if user %}
<a href="/dashboard">Dashboard</a>
<a href="/patients">Patients</a>
<a href="/appointments">Appointments</a>
<a href="/atd/beds">IPD Beds</a>
<a href="/diagnostics">LIS &amp; RIS</a>
<a href="/opd-billing">OPD Billing</a>
<a href="/pharmacy">Pharmacy</a>
<a href="/teleconsult">Teleconsult</a>
<a href="/ai-assistant">Miracle AI</a>
<a href="/notifications">Audit Logs</a>
<a href="/emr">EMR</a>
<a href="/modules">41 Modules</a>
{% if user_memberships|length > 1 %}
<span style="margin-left:10px;font-size:0.85rem;">Org: 
  <form action="/org/switch" method="POST" style="display:inline-block;margin:0;">
    <input type="hidden" name="csrf_token" value="{{csrf_token()}}">
    <select name="org_id" onchange="this.form.submit()" style="padding:2px 6px;margin:0;width:auto;display:inline-block;">
      {% for m in user_memberships %}
      <option value="{{m.org_id}}" {% if m.org_id == current_org.id %}selected{% endif %}>{{m.org.name}}</option>
      {% endfor %}
    </select>
  </form>
</span>
{% endif %}
<form action="/logout" method="POST" style="display:inline-block;margin:0 0 0 10px;">
  <input type="hidden" name="csrf_token" value="{{csrf_token()}}">
  <button type="submit" style="background:none;border:none;color:var(--ink);font-weight:500;cursor:pointer;padding:0;font:inherit;">Logout</button>
</form>
{% else %}
<a href="/login">Staff Login</a>
<a href="/auth/otp-login">Email OTP Login</a>
{% endif %}
</div></nav>
<main>{% with msgs=get_flashed_messages() %}{% for m in msgs %}<div class="notice">{{m}}</div>{% endfor %}{% endwith %}{{body|safe}}</main>
<footer>MIRACLE HIMS Enterprise Edition &bull; Multi-Tenant Healthcare Platform &bull; All Rights Reserved</footer></body></html>"""

@app.route("/")
def home():
    return page("""<section class="hero"><small>ENTERPRISE HEALTHCARE SUITE</small><h1>MIRACLE <span style="color:#087e8b">HIMS</span></h1>
    <p>Unified hospital information management platform with multi-tenant organization scoping, LIS/RIS diagnostics, Decimal-precise billing, pharmacy batch inventory, and verified Jitsi demo teleconsultations.</p><a class="btn" href="/login">Access Enterprise Portal</a></section>
    <section class="grid">{% for title,desc,level in modules[:6] %}<article class="card"><span class="pill">{{level}}</span><h3>{{title}}</h3><p>{{desc}}</p></article>{% endfor %}</section>""", modules=MODULES)

@app.route("/org/switch", methods=["POST"])
@login_required
def switch_org():
    org_id_val = request.form.get("org_id", type=int)
    u = who()
    m = Membership.query.join(Organization).filter(
        Membership.user_id == u.id, 
        Membership.org_id == org_id_val, 
        Organization.active == True
    ).first()
    if m:
        session["active_org_id"] = org_id_val
        flash(f"Switched organization to {m.org.name}")
    else:
        flash("Invalid or inactive organization selection.")
    return redirect(url_for("dashboard"))

@app.route("/login", methods=["GET","POST"])
def login():
    client_ip = request.remote_addr or "unknown"
    if request.method == "POST":
        username = request.form.get("username","").strip()
        password = request.form.get("password","")
        
        ip_attempt = LoginAttempt.query.filter_by(identifier=client_ip, ip_address=client_ip).first()
        now_utc = datetime.now(timezone.utc)
        if ip_attempt and ip_attempt.lockout_until and now_utc < ip_attempt.lockout_until.replace(tzinfo=timezone.utc):
            flash("Too many failed login attempts from your IP address. Please try again after 15 minutes.")
            return redirect(url_for("login"))
            
        user_attempt = LoginAttempt.query.filter_by(identifier=username, ip_address=client_ip).first()
        if user_attempt and user_attempt.lockout_until:
            if now_utc >= user_attempt.lockout_until.replace(tzinfo=timezone.utc):
                db.session.delete(user_attempt)
                db.session.commit()
                user_attempt = None
            else:
                flash("Account temporarily locked due to multiple failed login attempts.")
                return redirect(url_for("login"))
            
        u = User.query.filter_by(username=username).first()
        if u and u.check_password(password):
            LoginAttempt.query.filter_by(identifier=username, ip_address=client_ip).delete()
            LoginAttempt.query.filter_by(identifier=client_ip, ip_address=client_ip).delete()
            db.session.commit()
                
            m = Membership.query.join(Organization).filter(
                Membership.user_id == u.id, 
                Organization.active == True
            ).first()
            if m:
                session.clear()
                session["uid"] = u.id
                session["active_org_id"] = m.org_id
                db.session.add(AuditEvent(org_id=m.org_id, user_id=u.id, action="USER_LOGIN", resource=u.username))
                db.session.commit()
                return redirect(url_for("dashboard"))
        
        if user_attempt:
            user_attempt.attempts += 1
            if user_attempt.attempts >= 5:
                user_attempt.lockout_until = datetime.now(timezone.utc) + timedelta(minutes=15)
                flash("Too many failed attempts. Account locked for 15 minutes.")
            else:
                flash(f"Invalid credentials. Attempt {user_attempt.attempts} of 5.")
        else:
            db.session.add(LoginAttempt(identifier=username, ip_address=client_ip, attempts=1))
            
        if not ip_attempt:
            db.session.add(LoginAttempt(identifier=client_ip, ip_address=client_ip, attempts=1))
        else:
            ip_attempt.attempts += 1
            if ip_attempt.attempts >= 10:
                ip_attempt.lockout_until = datetime.now(timezone.utc) + timedelta(minutes=15)
                
        db.session.commit()
        flash("Login failed or organization inactive.")
    return page("""<h1>Staff &amp; User Login</h1>
    <section class="formcard" style="max-width:440px;margin:30px auto">
    <form method="post"><input type="hidden" name="csrf_token" value="{{csrf_token()}}">
    <label>Username</label><input name="username" autocomplete="username" required>
    <label>Password</label><input type="password" name="password" autocomplete="current-password" required>
    <button>Sign In</button></form>
    <p style="margin-top:15px;text-align:center;"><a href="/auth/otp-login" style="color:var(--teal);text-decoration:none;font-weight:600;">Or login via secure Email OTP</a></p></section>""")

@app.route("/auth/otp-login", methods=["GET", "POST"])
def otp_login():
    client_ip = request.remote_addr or "unknown"
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        if not email:
            flash("Please enter a valid email address.")
            return redirect(url_for("otp_login"))
        
        authorized_user = User.query.filter_by(username=email).first()
        if not authorized_user:
            flash("Error: No authorized staff account found for this email address.")
            return redirect(url_for("otp_login"))
        
        EmailOTP.query.filter(EmailOTP.expires_at < datetime.now(timezone.utc)).delete()
        db.session.commit()
        
        recent_email_otp = EmailOTP.query.filter_by(email=email, verified=False).order_by(EmailOTP.id.desc()).first()
        now_utc = datetime.now(timezone.utc)
        if recent_email_otp and (now_utc - recent_email_otp.created_at.replace(tzinfo=timezone.utc)) < timedelta(seconds=60):
            flash("Rate limit active for this email: Please wait 60 seconds.")
            return redirect(url_for("otp_login"))
            
        recent_ip_otp = EmailOTP.query.filter_by(ip_address=client_ip, verified=False).order_by(EmailOTP.id.desc()).first()
        if recent_ip_otp and (now_utc - recent_ip_otp.created_at.replace(tzinfo=timezone.utc)) < timedelta(seconds=30):
            flash("Rate limit active for your network: Please wait 30 seconds.")
            return redirect(url_for("otp_login"))
            
        code = f"{secrets.randbelow(900000) + 100000}"
        expires = datetime.now(timezone.utc) + timedelta(minutes=10)
        
        email_sent = send_real_email_notification(email, "MIRACLE HIMS - Secure Login OTP", f"Your secure verification OTP is: {code}. Valid for 10 minutes.")
        
        if not email_sent:
            flash("Failed to dispatch email OTP via SMTP gateway. Please check server settings and try again.")
            return redirect(url_for("otp_login"))
            
        otp_entry = EmailOTP(email=email, ip_address=client_ip, otp_hash=generate_password_hash(code), attempts=0, expires_at=expires, verified=False)
        db.session.add(otp_entry)
        
        org = Organization.query.first()
        if org:
            db.session.add(NotificationLog(org_id=org.id, recipient="[MASKED]", channel="Email OTP", message="Verification OTP dispatched securely.", status="Sent"))
        db.session.commit()
        
        session["otp_email"] = email
        flash(f"OTP verification code successfully sent via email to {email}.")
        return redirect(url_for("verify_otp"))
    
    return page("""<section class="formcard" style="max-width:440px;margin:30px auto"><h1>Secure Email OTP Verification</h1>
    <form method="post"><input type="hidden" name="csrf_token" value="{{csrf_token()}}">
    <label>Registered Email Address</label><input type="email" name="email" required placeholder="doctor@miraclehims.org">
    <button>Send Verification OTP</button></form></section>""")

@app.route("/auth/verify-otp", methods=["GET", "POST"])
def verify_otp():
    email = session.get("otp_email")
    if not email:
        return redirect(url_for("otp_login"))
    
    if request.method == "POST":
        entered_code = request.form.get("otp_code", "").strip()
        otp_record = EmailOTP.query.filter_by(email=email, verified=False).order_by(EmailOTP.id.desc()).first()
        
        now_utc = datetime.now(timezone.utc)
        if not otp_record or now_utc > otp_record.expires_at.replace(tzinfo=timezone.utc):
            flash("OTP has expired. Please request a new code.")
            return redirect(url_for("otp_login"))
            
        if otp_record.attempts >= 3:
            flash("Maximum verification attempts exceeded. Please request a new OTP.")
            return redirect(url_for("otp_login"))
            
        if check_password_hash(otp_record.otp_hash, entered_code):
            otp_record.verified = True
            db.session.commit()
            
            user = User.query.filter_by(username=email).first()
            if not user:
                flash("No authorized staff account found for this email address.")
                return redirect(url_for("login"))
            
            m = Membership.query.join(Organization).filter(
                Membership.user_id == user.id, 
                Organization.active == True
            ).first()
            if m:
                session.clear()
                session["uid"] = user.id
                session["active_org_id"] = m.org_id
                db.session.add(AuditEvent(org_id=m.org_id, user_id=user.id, action="OTP_LOGIN_SUCCESS", resource=user.username))
                db.session.commit()
                flash("Email verified successfully! Welcome.")
                return redirect(url_for("dashboard"))
        else:
            otp_record.attempts += 1
            db.session.commit()
            flash(f"Invalid OTP code. Attempt {otp_record.attempts} of 3.")
            
    return page("""<h1>Enter OTP Code</h1>
    <p>We sent a 6-digit verification code to <b>{{email}}</b>.</p>
    <form method="post"><input type="hidden" name="csrf_token" value="{{csrf_token()}}">
    <label>6-Digit OTP</label><input name="otp_code" required maxlength="6" style="letter-spacing:4px;font-size:1.2rem;text-align:center;">
    <button>Verify &amp; Sign In</button></form></section>""", email=email)

@app.route("/logout", methods=["POST"])
@login_required
def logout():
    session.clear()
    return redirect(url_for("home"))

@app.route("/dashboard")
@staff_required
def dashboard():
    oid = org_id()
    patients_count = Patient.query.filter_by(org_id=oid).count()
    appts_count = Appointment.query.filter_by(org_id=oid).count()
    vacant_beds = Bed.query.filter_by(org_id=oid, status="Vacant").count()
    total_beds = Bed.query.filter_by(org_id=oid).count()
    orders_count = DiagnosticOrder.query.filter_by(org_id=oid).count()
    patients = Patient.query.filter_by(org_id=oid).order_by(Patient.created_at.desc()).limit(8).all()
    return page("""<h1>Enterprise Dashboard</h1><p>Welcome, <b>{{user.username}}</b> &bull; Role: <b>{{role}}</b> &bull; Organization: <b>{{org.name}}</b></p>
    <div class="grid">
      <article class="card"><h3>Registered Patients</h3><h1>{{patients_count}}</h1><a class="btn" href="/patients">Manage Patients</a></article>
      <article class="card"><h3>Bed Occupancy</h3><h1>{{vacant_beds}} / {{total_beds}} Vacant</h1><a class="btn" href="/atd/beds">Manage IPD Beds</a></article>
      <article class="card"><h3>Diagnostics Orders</h3><h1>{{orders_count}}</h1><a class="btn" href="/diagnostics">Open LIS / RIS</a></article>
      <article class="card"><h3>OPD Billing</h3><p>Manage Invoices</p><a class="btn" href="/opd-billing">Open Billing</a></article>
    </div>
    <section class="card"><h2>Recent Patients Directory</h2><div class="tablewrap"><table><tr><th>UHID</th><th>Patient Name</th><th>Mobile</th><th>Payer</th><th>Registered</th></tr>{% for p in patients %}<tr><td>{{p.uhid}}</td><td>{{p.first_name}} {{p.last_name}}</td><td>{{p.mobile}}</td><td>{{p.payer_type}}</td><td>{{p.created_at.strftime('%d-%m-%Y')}}</td></tr>{% else %}<tr><td colspan="5">No patients recorded yet.</td></tr>{% endfor %}</table></div></section>""",
        user=who(), role=membership().role, org=Organization.query.get(oid),
        patients_count=patients_count, appts_count=appts_count, vacant_beds=vacant_beds, total_beds=total_beds, orders_count=orders_count, patients=patients)

@app.route("/patients", methods=["GET","POST"])
@staff_required
def patients():
    oid = org_id()
    if request.method == "POST":
        first = request.form.get("first_name","").strip()
        mobile = request.form.get("mobile","").strip()
        email = request.form.get("email","").strip().lower()
        if not first or not mobile:
            flash("First name and mobile number are required.")
            return redirect(url_for("patients"))
        
        random_suffix = uuid.uuid4().hex[:6].upper()
        uhid_val = f"MH-{datetime.now(timezone.utc):%y%m%d}-{random_suffix}"
        
        p = Patient(org_id=oid, uhid=uhid_val, first_name=first,
                    last_name=request.form.get("last_name","").strip(),
                    gender=request.form.get("gender",""), dob=request.form.get("dob",""),
                    mobile=mobile, email=email,
                    address=request.form.get("address","").strip(),
                    payer_type=request.form.get("payer_type","Self Pay"))
        db.session.add(p)
        log_action("PATIENT_REGISTERED", p.uhid)
        if email:
            sent = send_real_email_notification(email, "Welcome to MIRACLE HIMS", f"Dear {first}, your registration is complete. UHID: {uhid_val}")
            db.session.add(NotificationLog(org_id=oid, recipient="[MASKED]", channel="Email", message=f"Registration email dispatched. UHID: {uhid_val}", status="Sent" if sent else "Failed"))
        db.session.commit()
        flash("Patient registered successfully! UHID: " + p.uhid)
        return redirect(url_for("patients"))
        
    q = request.args.get("q","").strip()
    query = Patient.query.filter_by(org_id=oid)
    if q:
        like = f"%{q}%"
        query = query.filter(db.or_(Patient.first_name.ilike(like), Patient.last_name.ilike(like), Patient.uhid.ilike(like), Patient.mobile.ilike(like)))
    rows = query.order_by(Patient.created_at.desc()).limit(100).all()
    return page("""<h1>Patient Registration &amp; UHID Management</h1><section class="formcard"><h3>Register New Patient</h3><form method="post"><input type="hidden" name="csrf_token" value="{{csrf_token()}}">
    <div class="grid">
      <div><label>First Name *</label><input name="first_name" required></div>
      <div><label>Last Name</label><input name="last_name"></div>
      <div><label>Mobile No *</label><input name="mobile" required></div>
      <div><label>Email Address</label><input type="email" name="email" placeholder="patient@example.com"></div>
      <div><label>Date of Birth</label><input type="date" name="dob"></div>
      <div><label>Gender</label><select name="gender"><option value="">Select Gender</option><option>Female</option><option>Male</option><option>Other</option></select></div>
      <div><label>Payer Type</label><select name="payer_type"><option>Self Pay</option><option>Insurance</option><option>Corporate / TPA</option></select></div>
    </div>
    <label>Residential Address</label><textarea name="address" rows="2"></textarea>
    <button>Save Patient &amp; Generate UHID</button></form></section>
    <section class="card"><h2>Patient Directory</h2><form method="get"><input class="search" name="q" value="{{q}}" placeholder="Search by name, UHID or mobile"><button>Search</button></form>
    <div class="tablewrap"><table><tr><th>UHID</th><th>Name</th><th>Mobile</th><th>Email</th><th>Payer</th></tr>{% for p in rows %}<tr><td>{{p.uhid}}</td><td>{{p.first_name}} {{p.last_name}}</td><td>{{p.mobile}}</td><td>{{p.email}}</td><td>{{p.payer_type}}</td></tr>{% else %}<tr><td colspan="5">No matching patients found.</td></tr>{% endfor %}</table></div></section>""", rows=rows, q=q)

# --- APPOINTMENT SCHEDULING (FAIL-CLOSED ERROR HANDLING & DUAL OVERLAP PROTECTION) ---
@app.route("/appointments", methods=["GET","POST"])
@staff_required
def appointments():
    oid = org_id()
    if request.method == "POST":
        p = Patient.query.filter_by(id=request.form.get("patient_id", type=int), org_id=oid).first_or_404()
        doc_id = request.form.get("doctor_id", type=int)
        
        doc = Doctor.query.filter_by(id=doc_id, org_id=oid, active=True).first()
        if not doc:
            flash("Invalid or inactive doctor selected.")
            return redirect(url_for("appointments"))
            
        start_at_str = request.form.get("start_at", "").strip()
        try:
            naive_dt = datetime.fromisoformat(start_at_str)
            appt_dt_ist = naive_dt.astimezone(IST) if naive_dt.tzinfo else naive_dt.replace(tzinfo=IST)
            appt_dt_utc = appt_dt_ist.astimezone(timezone.utc)
        except ValueError:
            flash("Invalid appointment date and time format.")
            return redirect(url_for("appointments"))
            
        now_utc = datetime.now(timezone.utc)
        if appt_dt_utc < now_utc:
            flash("Cannot schedule appointments for past dates and times.")
            return redirect(url_for("appointments"))
            
        slot_end_utc = appt_dt_utc + timedelta(minutes=30)
        
        with db.session.no_autoflush:
            existing_appts = Appointment.query.filter_by(org_id=oid, status="Booked").with_for_update().all()
            for ea in existing_appts:
                ea_start_utc = ea.start_at.astimezone(timezone.utc)
                ea_end_utc = ea_start_utc + timedelta(minutes=30)
                if appt_dt_utc < ea_end_utc and slot_end_utc > ea_start_utc:
                    if ea.doctor_id == doc.id:
                        flash(f"Doctor {doc.name} has a conflicting overlapping appointment during this 30-minute window.")
                        return redirect(url_for("appointments"))
                    if ea.patient_id == p.id:
                        flash(f"Patient {p.first_name} already has a conflicting overlapping appointment with another doctor at this time.")
                        return redirect(url_for("appointments"))
                
        visit_type = request.form.get("visit_type", "Consultation")
        
        try:
            a = Appointment(org_id=oid, patient_id=p.id, doctor_id=doc.id,
                            doctor_name=doc.name, department=doc.department, visit_type=visit_type,
                            start_at=appt_dt_utc, reason=request.form.get("reason", ""))
            db.session.add(a)
            db.session.flush()
            if visit_type == "Teleconsultation":
                room_token = uuid.uuid4().hex
                db.session.add(Teleconsultation(org_id=oid, appointment_id=a.id, room_token=room_token))
            log_action("APPOINTMENT_CREATED", p.uhid)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            flash("Database constraint error: This time slot conflicts with an existing appointment.")
            return redirect(url_for("appointments"))

        flash("Appointment successfully scheduled!")
        return redirect(url_for("appointments"))
        
    patients = Patient.query.filter_by(org_id=oid).order_by(Patient.first_name).all()
    doctors = Doctor.query.filter_by(org_id=oid, active=True).all()
    rows = Appointment.query.filter_by(org_id=oid).order_by(Appointment.created_at.desc()).limit(150).all()
    return page("""<h1>Appointments &amp; Teleconsultation Scheduling</h1><section class="card"><form method="post"><input type="hidden" name="csrf_token" value="{{csrf_token()}}">
    <div class="grid">
      <div><label>Patient</label><select name="patient_id" required>{% for p in patients %}<option value="{{p.id}}">{{p.first_name}} {{p.last_name}} &bull; {{p.uhid}}</option>{% endfor %}</select></div>
      <div><label>Doctor &amp; Department</label><select name="doctor_id" required>{% for d in doctors %}<option value="{{d.id}}">{{d.name}} - {{d.department}}</option>{% endfor %}</select></div>
      <div><label>Visit Type</label><select name="visit_type"><option>Consultation</option><option>Teleconsultation</option><option>Follow-up</option></select></div>
      <div><label>Date &amp; Time (IST)</label><input type="datetime-local" name="start_at" required></div>
    </div>
    <label>Reason for Visit</label><input name="reason" placeholder="e.g. Persistent fever, routine checkup">
    <button>Schedule Appointment</button></form></section>
    <section class="card"><h2>Appointments Register</h2><div class="tablewrap"><table><tr><th>Patient</th><th>Doctor</th><th>Department</th><th>Type</th><th>Date/Time (IST)</th><th>Status</th></tr>
    {% for a in rows %}
    {% set ist_time = a.start_at.astimezone(IST) if a.start_at else None %}
    <tr><td>{{a.patient.first_name}} ({{a.patient.uhid}})</td><td>{{a.doctor_name}}</td><td>{{a.department}}</td><td>{{a.visit_type}}</td><td>{{ist_time.strftime('%d-%m-%Y %H:%M') if ist_time else ''}}</td><td><b>{{a.status}}</b></td></tr>
    {% else %}<tr><td colspan="6">No appointments recorded yet.</td></tr>{% endfor %}</table></div></section>""", patients=patients, doctors=doctors, rows=rows, IST=IST)

# --- OPD BILLING WITH FINITE/RANGE VALIDATION & ROLE-RESTRICTED MANUAL CONFIRMATION ---
@app.route("/opd-billing", methods=["GET","POST"])
@staff_required
def opd_billing():
    oid = org_id()
    if request.method == "POST":
        p = Patient.query.filter_by(id=request.form.get("patient_id", type=int), org_id=oid).first_or_404()
        try:
            fee_raw = request.form.get("consultation_fee", "500.00")
            tax_raw = request.form.get("tax_rate", "5.0")
            fee_float = float(fee_raw)
            tax_float = float(tax_raw)
            
            if not math.isfinite(fee_float) or not math.isfinite(tax_float):
                raise ValueError("Non-finite numeric values not allowed.")
            if fee_float < 0 or fee_float > 10000000 or tax_float < 0 or tax_float > 100:
                raise ValueError("Values out of acceptable financial range.")
                
            fee = Decimal(str(fee_float)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            tax_rate = Decimal(str(tax_float)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        except (InvalidOperation, ValueError, TypeError):
            flash("Invalid amount or tax rate provided. Values must be finite and within valid ranges.")
            return redirect(url_for("opd_billing"))
            
        tax_amount = (fee * (tax_rate / Decimal('100.00'))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        total = (fee + tax_amount).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        
        payment_mode = request.form.get("payment_mode", "Cash")
        if payment_mode not in {"Cash", "UPI", "Card", "Insurance"}:
            payment_mode = "Cash"
            
        status = "Pending"
        
        bill = OPDBill(
            org_id=oid, patient_id=p.id,
            bill_no=f"BILL-OPD-{datetime.now(timezone.utc):%y%m%d%H%M%S}-{uuid.uuid4().hex[:4].upper()}",
            consultation_fee=fee, tax_rate=tax_rate, tax_amount=tax_amount, total_amount=total,
            payment_mode=payment_mode, status=status
        )
        db.session.add(bill); log_action("OPD_BILL_CREATED", bill.bill_no); db.session.commit()
        flash("OPD Bill generated in Pending status. Manual cashier verification required to mark Paid.")
        return redirect(url_for("opd_billing"))
        
    patients = Patient.query.filter_by(org_id=oid).order_by(Patient.first_name).all()
    bills = OPDBill.query.filter_by(org_id=oid).order_by(OPDBill.created_at.desc()).limit(100).all()
    user_role = membership().role if membership() else ""
    return page("""<h1>OPD Billing &amp; Verified Invoices</h1>
    <section class="card"><h3>Generate OPD Consultation Invoice (Default: Pending)</h3>
    <form method="post"><input type="hidden" name="csrf_token" value="{{csrf_token()}}">
    <div class="grid">
      <div><label>Patient</label><select name="patient_id" required>{% for p in patients %}<option value="{{p.id}}">{{p.first_name}} &bull; {{p.uhid}}</option>{% endfor %}</select></div>
      <div><label>Consultation Fee (INR)</label><input type="number" step="0.01" name="consultation_fee" value="500.00" min="0" max="10000000" required></div>
      <div><label>Tax Rate (%)</label><input type="number" step="0.1" name="tax_rate" value="5.0" min="0" max="100" required></div>
      <div><label>Payment Mode</label><select name="payment_mode"><option>Cash</option><option>UPI</option><option>Card</option><option>Insurance</option></select></div>
    </div>
    <button>Generate Invoice</button></form></section>
    
    <section class="card"><h2>Generated OPD Bills &amp; Manual Demo Payment Confirmation</h2><div class="tablewrap"><table><tr><th>Bill No</th><th>Patient</th><th>Fee</th><th>Tax</th><th>Total</th><th>Mode</th><th>Status</th><th>Action / Manual Cashier Confirmation</th></tr>
    {% for b in bills %}
    <tr>
      <td>{{b.bill_no}}</td>
      <td>{{b.patient.first_name}} ({{b.patient.uhid}})</td>
      <td>₹{{b.consultation_fee}}</td>
      <td>₹{{b.tax_amount}} ({{b.tax_rate}}%)</td>
      <td><b>₹{{b.total_amount}}</b></td>
      <td>{{b.payment_mode}}</td>
      <td><span class="pill" {% if 'Paid' in b.status %}style="background:#d1fae5;color:#065f46;"{% endif %}>{{b.status}}</span></td>
      <td>
        <a class="btn" href="/opd-billing/print/{{b.id}}" style="padding:4px 8px;font-size:0.8rem;background:#087e8b;">Print</a>
        {% if 'Paid' not in b.status and user_role in ['admin', 'clinic'] %}
        <form action="/opd-billing/pay/{{b.id}}" method="POST" style="display:inline-block;margin-left:6px;">
          <input type="hidden" name="csrf_token" value="{{csrf_token()}}">
          <button type="submit" style="padding:4px 8px;font-size:0.8rem;background:#2e7d32;">Confirm Payment (Demo)</button>
        </form>
        {% endif %}
      </td>
    </tr>
    {% else %}<tr><td colspan="8">No bills generated yet.</td></tr>{% endfor %}</table></div></section>""", patients=patients, bills=bills, user_role=user_role)

@app.route("/opd-billing/pay/<int:bill_id>", methods=["POST"])
@billing_staff_required
def confirm_opd_payment(bill_id):
    oid = org_id()
    bill = OPDBill.query.filter_by(id=bill_id, org_id=oid).first_or_404()
    if 'Paid' in bill.status:
        flash("Bill is already marked as Paid.")
        return redirect(url_for("opd_billing"))
        
    bill.status = 'Paid (Manual Demo Confirmed)'
    log_action("OPD_BILL_PAYMENT_VERIFIED", bill.bill_no)
    db.session.commit()
    flash(f"Payment manually verified and confirmed for bill {bill.bill_no}!")
    return redirect(url_for("opd_billing"))

@app.route("/opd-billing/print/<int:bill_id>")
@staff_required
def print_opd_bill(bill_id):
    b = OPDBill.query.filter_by(id=bill_id, org_id=org_id()).first_or_404()
    log_action("OPD_BILL_PRINTED", b.bill_no); db.session.commit()
    
    safe_bill_no = html.escape(str(b.bill_no))
    safe_fname = html.escape(str(b.patient.first_name))
    safe_lname = html.escape(str(b.patient.last_name))
    safe_uhid = html.escape(str(b.patient.uhid))
    safe_mode = html.escape(str(b.payment_mode))
    safe_status = html.escape(str(b.status))
    
    invoice_html = f"""<!doctype html><html><head><title>Invoice {safe_bill_no}</title><style>body{{font-family:Arial;padding:30px;color:#173344}}h2{{color:#087e8b}}</style></head>
    <body><h2>MIRACLE HIMS &bull; OPD INVOICE</h2><hr>
    <p><b>Bill No:</b> {safe_bill_no}</p><p><b>Patient:</b> {safe_fname} {safe_lname} ({safe_uhid})</p>
    <p><b>Consultation Fee:</b> ₹{b.consultation_fee}</p><p><b>Tax ({b.tax_rate}%):</b> ₹{b.tax_amount}</p>
    <h3>Total Amount: ₹{b.total_amount}</h3><p><b>Payment Mode:</b> {safe_mode} | <b>Status:</b> {safe_status}</p>
    <p><small>Generated at {b.created_at.strftime('%Y-%m-%d %H:%M:%S')} UTC</small></p>
    <script>window.print();</script></body></html>"""
    return invoice_html

@app.route("/pharmacy", methods=["GET","POST"])
@pharmacist_required
def pharmacy():
    oid = org_id()
    if request.method == "POST":
        med = request.form.get("medicine_name","").strip()
        batch = request.form.get("batch_no","").strip()
        expiry_str = request.form.get("expiry_date","").strip()
        
        try:
            exp_date = datetime.strptime(expiry_str, "%Y-%m-%d").date()
            local_today = datetime.now(IST).date()
            if exp_date < local_today:
                flash("Error: Expiry date cannot be in the past when adding new inventory batch.")
                return redirect(url_for("pharmacy"))
        except ValueError:
            flash("Invalid or missing expiry date format. Please use YYYY-MM-DD.")
            return redirect(url_for("pharmacy"))
            
        try:
            qty = int(request.form.get("stock_qty", 100))
            price_raw = request.form.get("unit_price", "0.00")
            min_alert = int(request.form.get("min_stock_alert", 10))
            if qty < 0 or min_alert < 0:
                raise ValueError("Negative values not allowed")
            price = Decimal(price_raw).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            if price < 0:
                raise ValueError("Negative price not allowed")
        except (InvalidOperation, ValueError, TypeError):
            flash("Invalid quantity, unit price, or alert threshold.")
            return redirect(url_for("pharmacy"))
            
        if med and batch:
            item = PharmacyInventory(org_id=oid, medicine_name=med, batch_no=batch, expiry_date=expiry_str, stock_qty=qty, unit_price=price, min_stock_alert=min_alert)
            db.session.add(item); log_action("PHARMACY_STOCK_ADDED", med); db.session.commit()
            flash("Pharmacy inventory added successfully!")
        else:
            flash("Medicine name and batch number are required.")
        return redirect(url_for("pharmacy"))
        
    items = PharmacyInventory.query.filter_by(org_id=oid).all()
    dispenses = PharmacyDispense.query.filter_by(org_id=oid).order_by(PharmacyDispense.dispensed_at.desc()).limit(50).all()
    patients = Patient.query.filter_by(org_id=oid).all()
    return page("""<h1>Pharmacy (Retail &amp; IPD Dispensing)</h1>
    <section class="card"><h3>Add Medicine Inventory &amp; Batch</h3>
    <form method="post"><input type="hidden" name="csrf_token" value="{{csrf_token()}}">
    <div class="grid">
      <div><label>Medicine Name</label><input name="medicine_name" required placeholder="e.g. Paracetamol 650mg"></div>
      <div><label>Batch No</label><input name="batch_no" required placeholder="e.g. BT-9921"></div>
      <div><label>Expiry Date (YYYY-MM-DD)</label><input type="date" name="expiry_date" required></div>
      <div><label>Stock Quantity</label><input type="number" name="stock_qty" value="100" min="0" required></div>
      <div><label>Unit Price (INR)</label><input type="number" step="0.5" name="unit_price" value="10.0" min="0" required></div>
      <div><label>Low Stock Alert Limit</label><input type="number" name="min_stock_alert" value="10" min="0" required></div>
    </div>
    <button>Add Inventory Item</button></form></section>
    
    <section class="card"><h3>Dispense Medication to Patient</h3>
    <form method="post" action="/pharmacy/dispense"><input type="hidden" name="csrf_token" value="{{csrf_token()}}">
    <div class="grid">
      <div><label>Patient</label><select name="patient_id" required>{% for p in patients %}<option value="{{p.id}}">{{p.first_name}} &bull; {{p.uhid}}</option>{% endfor %}</select></div>
      <div><label>Select Medicine &amp; Batch</label><select name="inventory_id" required>{% for i in items %}<option value="{{i.id}}">{{i.medicine_name}} (Batch: {{i.batch_no}} - Exp: {{i.expiry_date}}) - Stock: {{i.stock_qty}} - ₹{{i.unit_price}}</option>{% endfor %}</select></div>
      <div><label>Dispense Quantity</label><input type="number" name="quantity" value="1" min="1" required></div>
    </div>
    <button style="background:#ed6c02;">Dispense &amp; Deduct Stock</button></form></section>

    <section class="card"><h2>Current Pharmacy Inventory</h2><div class="tablewrap"><table><tr><th>Medicine Name</th><th>Batch No</th><th>Expiry</th><th>Available Stock</th><th>Unit Price</th><th>Status</th></tr>
    {% for i in items %}
    <tr><td>{{i.medicine_name}}</td><td>{{i.batch_no}}</td><td>{{i.expiry_date}}</td><td><b>{{i.stock_qty}} units</b></td><td>₹{{i.unit_price}}</td>
    <td>{% if i.stock_qty <= i.min_stock_alert %}<span class="pill" style="background:#fef3c7;color:#92400e;">Low Stock</span>{% else %}<span class="pill" style="background:#e0f2fe;color:#0369a1;">Normal</span>{% endif %}</td></tr>
    {% else %}<tr><td colspan="6">No pharmacy inventory recorded.</td></tr>{% endfor %}</table></div></section>""", items=items, dispenses=dispenses, patients=patients)

@app.route("/pharmacy/dispense", methods=["POST"])
@pharmacist_required
def dispense_medicine():
    oid = org_id()
    patient_id = request.form.get("patient_id", type=int)
    inventory_id = request.form.get("inventory_id", type=int)
    qty = request.form.get("quantity", type=int)
    
    if not qty or qty <= 0:
        flash("Invalid quantity specified.")
        return redirect(url_for("pharmacy"))
        
    patient = Patient.query.filter_by(id=patient_id, org_id=oid).first()
    if not patient:
        flash("Error: Selected patient does not belong to the active organization.")
        return redirect(url_for("pharmacy"))
        
    with db.session.no_autoflush:
        inv = PharmacyInventory.query.filter_by(id=inventory_id, org_id=oid).with_for_update().first_or_404()
        
        if inv.expiry_date:
            try:
                exp_date = datetime.strptime(inv.expiry_date, "%Y-%m-%d").date()
                local_today = datetime.now(IST).date()
                if exp_date < local_today:
                    flash(f"CRITICAL SAFETY ERROR: Cannot dispense expired medicine '{inv.medicine_name}' (Batch: {inv.batch_no}).")
                    return redirect(url_for("pharmacy"))
            except ValueError:
                flash("Error: Invalid stored expiry date format for inventory item.")
                return redirect(url_for("pharmacy"))
                
        if inv.stock_qty < qty:
            flash(f"Error: Insufficient stock! Only {inv.stock_qty} units available for {inv.medicine_name}.")
            return redirect(url_for("pharmacy"))
            
        inv.stock_qty -= qty
        total_cost = (Decimal(str(qty)) * inv.unit_price).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        
        disp = PharmacyDispense(org_id=oid, patient_id=patient.id, inventory_id=inv.id, quantity=qty, total_price=total_cost)
        db.session.add(disp)
        log_action("MEDICATION_DISPENSED", f"{qty}x {inv.medicine_name}")
        db.session.commit()
        
    flash(f"Successfully dispensed {qty} units of {inv.medicine_name} to {patient.first_name}. Total cost: ₹{total_cost}")
    return redirect(url_for("pharmacy"))

@app.route("/teleconsult", methods=["GET"])
@staff_required
def teleconsult_view():
    oid = org_id()
    rooms = Teleconsultation.query.filter_by(org_id=oid).all()
    return page("""<h1>Unique Jitsi Room Link – Demo</h1>
    <section class="card"><div class="notice" style="background:#e0f7fa;border-left:4px solid var(--teal);color:var(--ink);"><b>Notice:</b> This module provides a Unique Jitsi Room Link for demonstration purposes. External Jitsi rooms do not independently authenticate users against HIMS database accounts.</div>
    <h3>Active Virtual Consultation Rooms</h3>
    <div class="tablewrap"><table><tr><th>Room ID</th><th>Appointment ID</th><th>Patient</th><th>Jitsi Room Link</th><th>Status</th></tr>
    {% for r in rooms %}
    <tr><td>ROOM-{{r.id}}</td><td>APT-{{r.appointment_id}}</td><td>{{r.appointment.patient.first_name if r.appointment and r.appointment.patient else 'N/A'}}</td><td><a class="btn" href="/teleconsult/join/{{r.id}}" style="padding:6px 12px;font-size:0.85rem;" target="_blank">Join Jitsi Demo Room</a></td><td><b>{{r.status}}</b></td></tr>
    {% else %}<tr><td colspan="5">No active teleconsultation rooms found.</td></tr>{% endfor %}</table></div></section>""", rooms=rooms)

@app.route("/teleconsult/join/<int:room_id>", methods=["GET"])
@staff_required
def join_teleconsult(room_id):
    oid = org_id()
    room = Teleconsultation.query.filter_by(id=room_id, org_id=oid).first_or_404()
    secure_jitsi_url = f"https://meet.jit.si/SecureMiracleHIMS_Org{oid}_Room{room.id}_{room.room_token}"
    log_action("TELECONSULT_JOINED", f"Room-{room.id}")
    db.session.commit()
    return redirect(secure_jitsi_url)

@app.route("/ai-assistant", methods=["GET", "POST"])
@doctor_required
def ai_assistant_view():
    oid = org_id()
    response_text = ""
    query = ""
    user_type = "Doctor"
    if request.method == "POST":
        query = request.form.get("query", "").strip()
        user_type = request.form.get("user_type", "Doctor")
        if query:
            response_text = f"[SIMULATED AI CLINICAL SUPPORT - DEMO MODE] Analysis for query '{query}': Recommended differential assessment includes checking complete blood count (CBC), inflammatory markers (CRP), vital signs stability, and targeted radiology imaging. Always verify clinical findings independently."
            db.session.add(AIAssistantLog(org_id=oid, user_type=user_type, query=query, ai_response=response_text))
            db.session.commit()
    logs = AIAssistantLog.query.filter_by(org_id=oid).order_by(AIAssistantLog.created_at.desc()).limit(10).all()
    return page("""<h1>Simulated Clinical AI Assistant (Demo Mode)</h1>
    <section class="formcard"><div class="notice" style="background:#e0f7fa;border-left:4px solid var(--teal);color:var(--ink);"><b>Notice:</b> This is a simulated clinical decision support module for demonstration purposes. All outputs must be validated by licensed medical professionals.</div>
    <form method="post">
      <input type="hidden" name="csrf_token" value="{{csrf_token()}}">
      <div class="grid">
        <div><label>User Mode</label><select name="user_type"><option value="Doctor">Doctor Clinical Support</option></select></div>
      </div>
      <label>Enter Clinical Query or Symptoms</label>
      <textarea name="query" rows="3" required placeholder="e.g. Patient presents with acute chest discomfort...">{{query}}</textarea>
      <button>Generate Simulated Insights</button>
    </form>
    {% if response_text %}<div class="notice" style="margin-top:15px;background:#f1f5f9;border-left:4px solid var(--teal);color:var(--ink);"><p>{{response_text}}</p></div>{% endif %}
    </section>
    <section class="card"><h3>Recent AI Queries &amp; Audit Logs</h3>
    <div class="tablewrap"><table><tr><th>Timestamp</th><th>Mode</th><th>Query</th><th>Simulated Response</th></tr>
    {% for l in logs %}
    <tr><td>{{l.created_at.strftime('%Y-%m-%d %H:%M')}}</td><td><span class="pill">{{l.user_type}}</span></td><td>{{l.query}}</td><td>{{l.ai_response}}</td></tr>
    {% else %}<tr><td colspan="4">No AI queries logged yet.</td></tr>{% endfor %}</table></div></section>""", response_text=response_text, query=query, user_type=user_type, logs=logs)

@app.route("/notifications", methods=["GET"])
@staff_required
def notifications_view():
    oid = org_id()
    logs = NotificationLog.query.filter_by(org_id=oid).order_by(NotificationLog.created_at.desc()).limit(25).all()
    return page("""<h1>Email, SMS &amp; Notification Audit Logs</h1>
    <section class="card"><h3>Communication Gateway Dispatch Logs</h3>
    <div class="tablewrap"><table><tr><th>ID</th><th>Recipient</th><th>Channel</th><th>Message</th><th>Status</th><th>Timestamp</th></tr>
    {% for l in logs %}
    <tr><td>#{{l.id}}</td><td>{{l.recipient}}</td><td><span class="pill">{{l.channel}}</span></td><td>{{l.message}}</td><td><b>{{l.status}}</b></td><td>{{l.created_at.strftime('%Y-%m-%d %H:%M')}}</td></tr>
    {% else %}<tr><td colspan="6">No notification logs recorded.</td></tr>{% endfor %}</table></div></section>""", logs=logs)

@app.route("/atd/beds", methods=["GET","POST"])
@staff_required
def beds():
    oid = org_id()
    if request.method == "POST":
        bedno = request.form.get("bed_no","").strip()
        if bedno and not Bed.query.filter_by(org_id=oid, bed_no=bedno).first():
            db.session.add(Bed(org_id=oid, ward=request.form.get("ward","General"), category=request.form.get("category","General"), bed_no=bedno))
            log_action("BED_CREATED", bedno); db.session.commit(); flash("Bed added successfully.")
        else:
            flash("Enter a unique bed number.")
        return redirect(url_for("beds"))
    rows = Bed.query.filter_by(org_id=oid).order_by(Bed.ward, Bed.bed_no).all()
    patients = Patient.query.filter_by(org_id=oid).order_by(Patient.first_name).all()
    return page("""<h1>IPD ADT &amp; Bed Management</h1><section class="card"><h3>Add New Bed</h3><form method="post"><input type="hidden" name="csrf_token" value="{{csrf_token()}}"><div class="grid"><input name="ward" placeholder="Ward Name (e.g. ICU, General)" required><input name="category" placeholder="Category (e.g. Deluxe, Isolation)"><input name="bed_no" placeholder="Bed Number (e.g. 405-A)" required></div><button>Add Bed</button></form></section>
    <section class="grid">{% for b in rows %}<article class="card" style="border-top:4px solid {% if b.status=='Vacant' %}#2e7d32{% elif b.status=='Occupied' %}#ed6c02{% else %}#d32f2f{% endif %}">
    <h3>{{b.bed_no}}</h3><p>{{b.ward}} &bull; {{b.category}}<br>Status: <span class="pill">{{b.status}}</span></p>
    {% if b.status=="Vacant" %}
    <form method="post" action="/atd/admit/{{b.id}}"><input type="hidden" name="csrf_token" value="{{csrf_token()}}"><select name="patient_id" required>{% for p in patients %}<option value="{{p.id}}">{{p.first_name}} &bull; {{p.uhid}}</option>{% endfor %}</select><button style="margin-top:6px;width:100%;">Admit Patient</button></form>
    {% elif b.status=="Occupied" %}
    <form method="post" action="/atd/discharge/{{b.id}}"><input type="hidden" name="csrf_token" value="{{csrf_token()}}"><button style="background:#ed6c02;margin-top:6px;width:100%;">Discharge Patient</button></form>
    {% else %}
    <form method="post" action="/atd/clean/{{b.id}}"><input type="hidden" name="csrf_token" value="{{csrf_token()}}"><button style="background:#2e7d32;margin-top:6px;width:100%;">Confirm Housekeeping Cleaned</button></form>
    {% endif %}</article>{% else %}<p>No beds configured in organization.</p>{% endfor %}</section>""", rows=rows, patients=patients)

# --- IPD ADMISSION WITH DATABASE-LEVEL ACTIVE ADMISSION CONSTRAINT ---
@app.route("/atd/admit/<int:bed_id>", methods=["POST"])
@staff_required
def admit(bed_id):
    oid = org_id()
    with db.session.no_autoflush:
        b = Bed.query.filter_by(id=bed_id, org_id=oid, status="Vacant").with_for_update().first_or_404()
        patient_id = request.form.get("patient_id", type=int)
        
        p = Patient.query.filter_by(id=patient_id, org_id=oid).with_for_update().first_or_404()
        
        existing_admission = Admission.query.filter_by(org_id=oid, patient_id=p.id, status="Admitted").first()
        if existing_admission:
            flash(f"Error: Patient {p.first_name} ({p.uhid}) is already admitted in bed #{existing_admission.bed_id}.")
            return redirect(url_for("beds"))
            
        b.status = "Occupied"
        b.patient_id = p.id
        
        try:
            db.session.add(Admission(org_id=oid, patient_id=p.id, bed_id=b.id))
            log_action("PATIENT_ADMITTED", p.uhid)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            flash("Database constraint error: Patient already has an active admission.")
            return redirect(url_for("beds"))
            
    flash(f"Patient successfully admitted to bed {b.bed_no}.")
    return redirect(url_for("beds"))

@app.route("/atd/discharge/<int:bed_id>", methods=["POST"])
@staff_required
def discharge(bed_id):
    oid = org_id()
    b = Bed.query.filter_by(id=bed_id, org_id=oid, status="Occupied").first_or_404()
    
    adm = Admission.query.filter_by(org_id=oid, bed_id=b.id, status="Admitted").first()
    if not adm:
        flash("Error: No active admission record found for this occupied bed.")
        return redirect(url_for("beds"))
        
    adm.status = "Discharged"
    adm.discharged_at = datetime.now(timezone.utc)
    b.status = "Housekeeping"
    b.patient_id = None
    log_action("PATIENT_DISCHARGED", b.bed_no)
    db.session.commit()
    flash(f"Patient discharged. Bed {b.bed_no} moved to Housekeeping status.")
    return redirect(url_for("beds"))

@app.route("/atd/clean/<int:bed_id>", methods=["POST"])
@staff_required
def clean_bed(bed_id):
    oid = org_id()
    b = Bed.query.filter_by(id=bed_id, org_id=oid, status="Housekeeping").first_or_404()
    b.status = "Vacant"
    log_action("BED_CLEANED", b.bed_no); db.session.commit()
    flash(f"Bed {b.bed_no} cleaned and marked Vacant.")
    return redirect(url_for("beds"))

@app.route("/diagnostics", methods=["GET","POST"])
@lab_required
def diagnostics():
    oid = org_id()
    if request.method == "POST":
        p = Patient.query.filter_by(id=request.form.get("patient_id", type=int), org_id=oid).first_or_404()
        cat_id = request.form.get("catalog_id", type=int)
        
        test_item = DepartmentTestCatalog.query.filter(
            DepartmentTestCatalog.id == cat_id,
            db.or_(DepartmentTestCatalog.org_id == oid, DepartmentTestCatalog.org_id.is_(None))
        ).first_or_404()
        
        if test_item:
            order = DiagnosticOrder(
                org_id=oid, patient_id=p.id,
                order_no=f"DX-{datetime.now(timezone.utc):%y%m%d%H%M%S}-{uuid.uuid4().hex[:6].upper()}",
                modality=test_item.category, sub_department=test_item.sub_department,
                service=test_item.test_name, status="Order Generated"
            )
            db.session.add(order); log_action("DIAGNOSTIC_ORDER_CREATED", order.order_no)
            db.session.commit(); flash(f"{test_item.category} test order created successfully!")
        else:
            flash("Please select a valid test from the catalog.")
        return redirect(url_for("diagnostics"))
        
    patients = Patient.query.filter_by(org_id=oid).order_by(Patient.first_name).all()
    catalog_tests = DepartmentTestCatalog.query.filter(
        db.or_(DepartmentTestCatalog.org_id == oid, DepartmentTestCatalog.org_id.is_(None))
    ).all()
    rows = DiagnosticOrder.query.filter_by(org_id=oid).order_by(DiagnosticOrder.created_at.desc()).limit(150).all()
    
    return page("""<h1>Advanced Diagnostics (Separate LIS &amp; RIS Workflows)</h1>
    <section class="card"><h3>Order Laboratory or Radiology Test</h3>
    <form method="post"><input type="hidden" name="csrf_token" value="{{csrf_token()}}"><div class="grid">
    <div><label>Patient</label><select name="patient_id" required>{% for p in patients %}<option value="{{p.id}}">{{p.first_name}} &bull; {{p.uhid}}</option>{% endfor %}</select></div>
    <div><label>Select LIS or RIS Test</label><select name="catalog_id" required>{% for t in catalog_tests %}<option value="{{t.id}}">[{{t.category}}] {{t.sub_department}} - {{t.test_name}} (₹{{t.price}})</option>{% endfor %}</select></div></div><button>Place Order</button></form></section>
    <section class="card"><h2>Diagnostic Queue &amp; Workflow Status</h2><div class="tablewrap"><table><tr><th>Order No</th><th>Patient</th><th>Modality</th><th>Sub-Dept</th><th>Service</th><th>Status</th><th>Verified By</th><th>Update Status &amp; Findings</th></tr>
    {% for x in rows %}<tr><td>{{x.order_no}}</td><td>{{x.patient.first_name}} &bull; {{x.patient.uhid}}</td><td><span class="pill">{{x.modality}}</span></td><td>{{x.sub_department}}</td><td>{{x.service}}</td><td><b>{{x.status}}</b></td><td>{{x.verified_by or 'Pending'}}</td><td>
    <form method="post" action="/diagnostics/{{x.id}}/status"><input type="hidden" name="csrf_token" value="{{csrf_token()}}">
    <select name="status" style="margin:0 0 6px 0;">
      {% if x.modality == 'LIS' %}
        <option {% if x.status=='Order Generated' %}selected{% endif %}>Order Generated</option>
        <option {% if x.status=='Sample Collected' %}selected{% endif %}>Sample Collected</option>
        <option {% if x.status=='Lab Acknowledged' %}selected{% endif %}>Lab Acknowledged</option>
        <option {% if x.status=='Result Entered' %}selected{% endif %}>Result Entered</option>
        <option {% if x.status=='Pathologist Review' %}selected{% endif %}>Pathologist Review</option>
        <option {% if x.status=='Finalized' %}selected{% endif %}>Finalized</option>
      {% else %}
        <option {% if x.status=='Order Generated' %}selected{% endif %}>Order Generated</option>
        <option {% if x.status=='Imaging Scheduled' %}selected{% endif %}>Imaging Scheduled</option>
        <option {% if x.status=='Scan Performed' %}selected{% endif %}>Scan Performed</option>
        <option {% if x.status=='Result Entered' %}selected{% endif %}>Result Entered</option>
        <option {% if x.status=='Radiologist Reporting' %}selected{% endif %}>Radiologist Reporting</option>
        <option {% if x.status=='Finalized' %}selected{% endif %}>Finalized</option>
      {% endif %}
    </select>
    <input name="result_text" value="{{x.result_text}}" placeholder="Test findings / reporting" style="margin:0 0 6px 0;">
    <button style="padding:4px 10px;font-size:0.8rem;">Save</button></form></td></tr>{% else %}<tr><td colspan="8">No diagnostic orders found.</td></tr>{% endfor %}</table></div></section>""", patients=patients, catalog_tests=catalog_tests, rows=rows)

@app.route("/diagnostics/<int:order_id>/status", methods=["POST"])
@lab_required
def diagnostic_status(order_id):
    x = DiagnosticOrder.query.filter_by(id=order_id, org_id=org_id()).first_or_404()
    
    lis_sequence = {"Order Generated": 1, "Sample Collected": 2, "Lab Acknowledged": 3, "Result Entered": 4, "Pathologist Review": 5, "Finalized": 6}
    ris_sequence = {"Order Generated": 1, "Imaging Scheduled": 2, "Scan Performed": 3, "Result Entered": 4, "Radiologist Reporting": 5, "Finalized": 6}
    
    seq = lis_sequence if x.modality == "LIS" else ris_sequence
    new_status = request.form.get("status")
    if new_status not in seq:
        abort(400)
        
    current_level = seq.get(x.status, 1)
    target_level = seq.get(new_status, 1)
    
    if target_level <= current_level:
        flash(f"Invalid workflow transition! Cannot move backward from '{x.status}' to '{new_status}'.")
        return redirect(url_for("diagnostics"))
        
    if target_level > current_level + 1:
        flash(f"Invalid workflow transition! Cannot jump directly from '{x.status}' to '{new_status}'.")
        return redirect(url_for("diagnostics"))
        
    res_text = request.form.get("result_text","").strip()
    if target_level >= 4 and not res_text and not x.result_text:
        flash("Test findings and clinical results are mandatory when entering the Result Entered stage.")
        return redirect(url_for("diagnostics"))
        
    x.status = new_status
    if res_text:
        x.result_text = res_text
    if target_level == 6:
        x.verified_by = who().username
        
    log_action("DIAGNOSTIC_STATUS_UPDATED", x.order_no); db.session.commit()
    flash("Diagnostic workflow status updated successfully.")
    return redirect(url_for("diagnostics"))

# --- EMR WITH ROLE RESTRICTIONS & SAFE MIME-TYPE DOWNLOAD ---
@app.route("/emr", methods=["GET","POST"])
@login_required
def emr():
    oid = org_id()
    u = who()
    m = membership()
    
    if request.method == "POST":
        if m.role not in ("admin", "doctor", "nurse"):
            abort(403)
            
        p = Patient.query.filter_by(id=request.form.get("patient_id", type=int), org_id=oid).first_or_404()
        f = request.files.get("file")
        if not f or not f.filename:
            flash("Please choose a file or capture via camera.")
        else:
            if not allowed_file_with_signature(f):
                flash("Invalid file type or header signature mismatch! Only verified PNG, JPG, JPEG, and PDF are allowed.")
                return redirect(url_for("emr"))
            data = f.read()
            if len(data) > 8*1024*1024:
                abort(413)
            name = os.path.basename(f.filename).replace("\\","_")[:250]
            doc = MedicalDocument(org_id=oid, patient_id=p.id, original_name=name, mime_type=f.mimetype or "application/octet-stream", data=data)
            db.session.add(doc); log_action("EMR_DOCUMENT_UPLOADED", p.uhid); db.session.commit()
            flash("Document stored securely in database blob storage with header signature verification (Note: header checks complement but do not replace dedicated malware scanning).")
        return redirect(url_for("emr"))
        
    query = MedicalDocument.query.filter_by(org_id=oid)
    if m.role == "patient":
        patient_record = Patient.query.filter_by(user_id=u.id, org_id=oid).first()
        if patient_record:
            query = query.filter_by(patient_id=patient_record.id)
        else:
            query = query.filter_by(id=-1)
    elif m.role not in ("admin", "doctor", "nurse"):
        query = query.filter_by(id=-1)
            
    docs = query.order_by(MedicalDocument.uploaded_at.desc()).limit(100).all()
    patients = Patient.query.filter_by(org_id=oid).order_by(Patient.first_name).all() if m.role in ("admin", "doctor", "nurse") else []
    return page("""<h1>EMR &amp; Longitudinal Clinical Documents</h1>
    {% if role in ['admin', 'doctor', 'nurse'] %}
    <section class="card"><p>Files are stored in database binary blob storage with header signature validation (Note: does not replace enterprise malware scanning).</p><form method="post" enctype="multipart/form-data"><input type="hidden" name="csrf_token" value="{{csrf_token()}}">
    <label>Patient</label><select name="patient_id" required>{% for p in patients %}<option value="{{p.id}}">{{p.first_name}} &bull; {{p.uhid}}</option>{% endfor %}</select>
    <label>Upload Document or Capture via Camera</label><input type="file" name="file" accept="image/*,application/pdf" capture="environment" required><button>Upload to EMR</button></form></section>
    {% endif %}
    <section class="card"><h2>Stored Patient Documents</h2><div class="tablewrap"><table><tr><th>Patient</th><th>File Name</th><th>Uploaded At</th><th>Action</th></tr>{% for d in docs %}<tr><td>{{d.patient.first_name}} &bull; {{d.patient.uhid}}</td><td>{{d.original_name}}</td><td>{{d.uploaded_at.strftime('%d-%m-%Y %H:%M')}}</td><td><a class="btn" href="/emr/document/{{d.id}}" style="padding:4px 10px;font-size:0.85rem;">Download Document</a></td></tr>{% else %}<tr><td colspan="4">No documents available or unauthorized role access.</td></tr>{% endfor %}</table></div></section>""", patients=patients, docs=docs, role=m.role)

@app.route("/emr/document/<int:doc_id>")
@login_required
def document_download(doc_id):
    oid = org_id()
    u = who()
    m = membership()
    d = MedicalDocument.query.filter_by(id=doc_id, org_id=oid).first_or_404()
    
    if m.role == "patient":
        patient_record = Patient.query.filter_by(user_id=u.id, org_id=oid).first()
        if not patient_record or d.patient_id != patient_record.id:
            abort(403)
    elif m.role not in ("admin", "doctor", "nurse"):
        abort(403)
            
    log_action("EMR_DOCUMENT_DOWNLOADED", d.original_name)
    db.session.commit()
    return send_file(BytesIO(d.data), mimetype="application/octet-stream", as_attachment=True, download_name=d.original_name)

@app.route("/modules")
@login_required
def modules():
    return page("""<h1>MIRACLE HIMS &bull; Complete 41-Module Catalogue</h1><p>Comprehensive enterprise healthcare modules overview with Core, Foundation, and Planned implementation statuses.</p>
    <div class="tablewrap card"><table><tr><th>#</th><th>Module Name</th><th>Scope &amp; Description</th><th>Status</th></tr>{% for m in modules %}<tr><td><b>{{loop.index}}</b></td><td>{{m[0]}}</td><td>{{m[1]}}</td><td><span class="pill">{{m[2]}}</span></td></tr>{% endfor %}</table></div>""", modules=MODULES)

@app.cli.command("init-demo")
def init_demo():
    for uname, pwd, role in [
        ("demo_clinic", os.environ.get("DEMO_CLINIC_PASSWORD"), "clinic"),
        ("demo_lab", os.environ.get("DEMO_LAB_PASSWORD"), "lab"),
        ("demo_pharmacist", os.environ.get("DEMO_PHARM_PASSWORD"), "pharmacist"),
        ("admin@miraclehims.org", os.environ.get("ADMIN_PASSWORD"), "admin"),
        ("doctor@miraclehims.org", os.environ.get("DOCTOR_PASSWORD"), "doctor"),
    ]:
        if not pwd:
            raise RuntimeError(f"CRITICAL ERROR: Environment variable for password of {uname} is missing. Set demo credentials securely.")
        u = User.query.filter_by(username=uname).first()
        if not u:
            u = User(username=uname, role=role, password_hash=generate_password_hash(pwd))
            db.session.add(u)
        else:
            u.role = role
            u.password_hash = generate_password_hash(pwd)
        db.session.flush()

    org = Organization.query.first()
    if not org:
        org_name = os.environ.get("DEMO_ORG_NAME", "MIRACLE Super Speciality Hospital")
        org = Organization(name=org_name, org_type="Hospital", active=True)
        db.session.add(org); db.session.flush()

    for uname, role in [("demo_clinic", "clinic"), ("demo_lab", "lab"), ("demo_pharmacist", "pharmacist"), ("admin@miraclehims.org", "admin"), ("doctor@miraclehims.org", "doctor")]:
        u = User.query.filter_by(username=uname).first()
        if u:
            mem = Membership.query.filter_by(user_id=u.id, org_id=org.id).first()
            if not mem:
                db.session.add(Membership(user_id=u.id, org_id=org.id, role=role))
            else:
                mem.role = role

    if Bed.query.filter_by(org_id=org.id).count() == 0:
        for ward, cat, no in [("Fourth Floor", "DELUXE", "405-A"), ("Fourth Floor", "DELUXE", "405-B"), ("Basement 2", "ISOLATION", "ISOLATION-1"), ("First Floor", "CCU", "CCU-01"), ("First Floor", "MICU", "MICU-01")]:
            db.session.add(Bed(org_id=org.id, ward=ward, category=cat, bed_no=no))

    if Doctor.query.filter_by(org_id=org.id).count() == 0:
        for dname, dept in [("Dr. Rajesh Sharma", "General Medicine"), ("Dr. Anita Verma", "Cardiology"), ("Dr. Vikram Gupta", "Orthopedics"), ("Dr. Priya Sen", "Neurology")]:
            db.session.add(Doctor(org_id=org.id, name=dname, department=dept, active=True))

    if PharmacyInventory.query.filter_by(org_id=org.id).count() == 0:
        for med, batch, exp, qty, price, alert in [
            ("Paracetamol 650mg", "BT-8812", "2027-12-31", 250, Decimal('10.00'), 20),
            ("Amoxicillin 500mg", "BT-9921", "2026-10-15", 120, Decimal('25.00'), 15),
            ("Ibuprofen 400mg", "BT-4410", "2028-05-20", 300, Decimal('12.50'), 25),
        ]:
            db.session.add(PharmacyInventory(org_id=org.id, medicine_name=med, batch_no=batch, expiry_date=exp, stock_qty=qty, unit_price=price, min_stock_alert=alert))

    if DepartmentTestCatalog.query.filter_by(org_id=org.id).count() == 0:
        catalog_data = [
            ("LIS", "Biochemistry", "Liver Function Test (LFT)", Decimal('650.00')),
            ("LIS", "Biochemistry", "Kidney Function Test (KFT)", Decimal('700.00')),
            ("LIS", "Biochemistry", "Lipid Profile", Decimal('550.00')),
            ("LIS", "Biochemistry", "Fasting Blood Sugar (FBS)", Decimal('150.00')),
            ("LIS", "Biochemistry", "HbA1c", Decimal('400.00')),
            ("LIS", "Molecular", "RT-PCR Viral Panel", Decimal('1200.00')),
            ("LIS", "Molecular", "HPV DNA Test", Decimal('2500.00')),
            ("LIS", "Immunology", "Thyroid Profile (T3, T4, TSH)", Decimal('600.00')),
            ("LIS", "Immunology", "Dengue NS1 & IgM", Decimal('800.00')),
            ("LIS", "Immunology", "Widal Test", Decimal('300.00')),
            ("LIS", "Hematology", "Complete Blood Count (CBC)", Decimal('350.00')),
            ("LIS", "Hematology", "ESR & PT/INR", Decimal('400.00')),
            ("RIS", "X-Ray", "X-Ray Chest PA View", Decimal('500.00')),
            ("RIS", "X-Ray", "X-Ray KUB", Decimal('600.00')),
            ("RIS", "CT Scan", "CT Brain Plain/Contrast", Decimal('2800.00')),
            ("RIS", "CT Scan", "CT Thorax", Decimal('3500.00')),
            ("RIS", "MRI", "MRI Brain with Contrast", Decimal('5500.00')),
            ("RIS", "MRI", "MRI Knee Joint", Decimal('4500.00')),
            ("RIS", "Ultrasound", "USG Abdomen & Pelvis", Decimal('1100.00')),
            ("RIS", "Ultrasound", "USG Obstetric Anomaly Scan", Decimal('1500.00')),
        ]
        for cat, sub, tname, price in catalog_data:
            db.session.add(DepartmentTestCatalog(category=cat, sub_department=sub, test_name=tname, price=price, org_id=org.id))

    db.session.commit()
    print("MIRACLE HIMS V2 Production Initialized successfully with all security safeguards and constraints.")

if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG","0")=="1")
