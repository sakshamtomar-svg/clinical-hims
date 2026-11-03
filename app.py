import os
from datetime import datetime
from functools import wraps
from flask import Flask, request, redirect, url_for, session, flash, jsonify, render_template_string
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "LOCAL-DEMO-ONLY-change-before-deploy")
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'pdf'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

url = os.environ.get("DATABASE_URL", "sqlite:///clinical_hims.db")
if url.startswith("postgres://"): url = url.replace("postgres://", "postgresql://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)
CSRFProtect(app)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    def set_password(self, p): self.password_hash = generate_password_hash(p)
    def check_password(self, p): return check_password_hash(self.password_hash, p)

class Patient(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), unique=True)
    identifier = db.Column(db.String(40), unique=True, nullable=False)
    given_name = db.Column(db.String(100), nullable=False)
    family_name = db.Column(db.String(100), default="")
    appointments = db.relationship("Appointment", backref="patient", lazy=True)

class PatientProfile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey("patient.id"), unique=True, nullable=False)
    gender = db.Column(db.String(20), default="")
    dob = db.Column(db.String(10), default="")
    mobile = db.Column(db.String(20), default="")
    address = db.Column(db.String(300), default="")
    payer_type = db.Column(db.String(30), default="Direct Patient")
    nationality = db.Column(db.String(50), default="Indian")

class Doctor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    department = db.Column(db.String(80), nullable=False)
    active = db.Column(db.Boolean, default=True)

class Bed(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ward_name = db.Column(db.String(50), nullable=False)
    bed_category = db.Column(db.String(50), nullable=False)
    bed_no = db.Column(db.String(20), unique=True, nullable=False)
    status = db.Column(db.String(30), default="Vacant")
    patient_id = db.Column(db.Integer, db.ForeignKey("patient.id"), nullable=True)

class LabInvestigation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey("patient.id"), nullable=False)
    lab_no = db.Column(db.String(30), unique=True, nullable=False)
    modality = db.Column(db.String(20), default="LIS")
    service_name = db.Column(db.String(150), nullable=False)
    sample_status = db.Column(db.String(40), default="Not Collected")
    result_value = db.Column(db.Text, default="")
    report_status = db.Column(db.String(30), default="Pending")

class MedicalDocument(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey("patient.id"), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    original_name = db.Column(db.String(255), nullable=False)
    doc_type = db.Column(db.String(50), default="Lab Report")
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    patient = db.relationship("Patient", backref="documents")

class Appointment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey("patient.id"), nullable=False)
    start = db.Column(db.String(30), nullable=False)
    reason = db.Column(db.String(250), default="")
    status = db.Column(db.String(20), default="booked")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class AppointmentDetail(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    appointment_id = db.Column(db.Integer, db.ForeignKey("appointment.id"), unique=True, nullable=False)
    doctor_id = db.Column(db.Integer, db.ForeignKey("doctor.id"))
    department = db.Column(db.String(80), default="General Medicine")
    visit_type = db.Column(db.String(30), default="Consultation")
    appointment = db.relationship("Appointment", backref=db.backref("detail", uselist=False))
    doctor = db.relationship("Doctor")

class AuditEvent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80))
    action = db.Column(db.String(100))
    resource = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

def current_user():
    return db.session.get(User, session["uid"]) if "uid" in session else None

def login_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not current_user():
            flash("Please sign in first.")
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapped

BASE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Clinical HIMS - Enterprise Edition</title><style>
:root{--teal:#087e8b;--ink:#173344;--muted:#637783;--line:#dce7eb;--green:#2e7d32;--orange:#ed6c02;--red:#d32f2f}*{box-sizing:border-box}
body{margin:0;background:#f2f8fa;color:var(--ink);font:16px/1.5 Arial}nav{display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;padding:15px 5%;background:#fff;border-bottom:1px solid var(--line)}
nav a{color:var(--ink);margin-right:12px;text-decoration:none;font-weight:500}.brand{font-weight:bold;color:var(--teal);font-size:1.2rem}
main{width:min(1200px,94%);margin:28px auto;min-height:72vh}.hero,.card,.formcard{background:white;border:1px solid var(--line);border-radius:16px;padding:24px;margin-bottom:18px}
.hero{background:linear-gradient(135deg,#e0f5f3,#fff 65%,#e8efff);padding:clamp(25px,5vw,45px)}h1{font-size:clamp(1.8rem,4vw,2.6rem);line-height:1.1}h1 span{color:var(--teal)}p,small{color:var(--muted)}
button,.btn{background:var(--teal);color:#fff;border:0;border-radius:8px;padding:10px 14px;display:inline-block;text-decoration:none;font-weight:bold;cursor:pointer}
input,select,textarea{width:100%;padding:10px;border:1px solid var(--line);border-radius:8px;font:inherit;margin:4px 0 12px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px}.notice{padding:12px;background:#fff4d6;border-radius:8px;margin:12px 0}
.tablewrap{overflow-x:auto}table{width:100%;border-collapse:collapse;min-width:700px}td,th{text-align:left;padding:10px;border-bottom:1px solid var(--line)}
.badge{padding:4px 8px;border-radius:6px;font-size:.8rem;font-weight:bold;color:#fff}
.bg-vacant{background:var(--green)}.bg-occupied{background:var(--orange)}.bg-repair{background:var(--red)}
footer{text-align:center;padding:22px;color:var(--muted);font-size:.85rem}
@media print{nav,footer,.no-print,button{display:none!important}body{background:#fff}main{width:100%;margin:0}.card{border:1px solid #aaa}}
</style></head><body>
<nav><a class="brand" href="/">Clinical HIMS</a>
<div>{% if user %}
<a href="/dashboard">Dashboard</a>
<a href="/register-patient">Registration</a>
<a href="/atd/beds">ATD Beds</a>
<a href="/lis/queue">LIS / RIS Lab</a>
<a href="/emr/records">EMR &amp; Reports</a>
<a href="/logout">Log out</a>
{% else %}<a href="/login">Log in</a>{% endif %}</div></nav>
<main>{% with msgs=get_flashed_messages() %}{% for m in msgs %}<div class="notice">{{m}}</div>{% endfor %}{% endwith %}{{body|safe}}</main>
<footer>NEEEV Project Prototype • Hospital Information Management System</footer></body></html>"""

def page(body, **kwargs):
    return render_template_string(BASE, body=render_template_string(body, **kwargs), user=current_user())

def ensure_patient(u):
    p = Patient.query.filter_by(user_id=u.id).first()
    if not p:
        p = Patient(user_id=u.id, identifier=f"UHID-{datetime.utcnow():%y%m%d}-{u.id:04d}", given_name=u.username)
        db.session.add(p); db.session.flush()
    return p

@app.route("/")
def home():
    return page("""<section class="hero"><small>HOSPITAL INFORMATION MANAGEMENT SYSTEM</small><h1>Integrated Clinical Workflow &amp;<br><span>Patient Management</span></h1>
    <p>Modules integrated: Patient Registration, UHID, ATD Bed Status, LIS/RIS Diagnostics, &amp; EMR Camera Uploads.</p><a class="btn" href="/login">Access System Portal</a></section>
    <section class="grid"><article class="card"><h3>Registration &amp; UHID</h3><p>Fast patient intake, demographic details, payer &amp; insurance mapping.</p></article>
    <article class="card"><h3>ATD Module</h3><p>Bed status monitoring, direct admission, bed transfers, and billing estimates.</p></article>
    <article class="card"><h3>LIS &amp; RIS Labs</h3><p>Sample acknowledgement, result entry, and result finalization workflows.</p></article>
    <article class="card"><h3>EMR &amp; Camera Upload</h3><p>Capture and attach clinical photographs, lab reports, and prescriptions directly.</p></article></section>""")

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        u = User.query.filter_by(username=request.form.get("username","").strip()).first()
        if u and u.check_password(request.form.get("password","")):
            session.clear(); session["uid"] = u.id
            return redirect(url_for("dashboard"))
        flash("Login failed. Check credentials.")
    return page("""<section class="formcard" style="max-width:450px;margin:auto"><h1>Staff &amp; Patient Login</h1><form method="post">
    <input type="hidden" name="csrf_token" value="{{csrf_token()}}">
    <label>Username</label><input name="username" required>
    <label>Password</label><input name="password" type="password" required><button>Sign In</button></form></section>""")

@app.route("/logout")
def logout():
    session.clear(); return redirect(url_for("home"))

@app.route("/dashboard")
@login_required
def dashboard():
    u = current_user()
    p = Patient.query.filter_by(user_id=u.id).first() if u.role == "patient" else None
    appointments = Appointment.query.all() if u.role in ("clinic","admin","lab") else (Appointment.query.filter_by(patient_id=p.id).all() if p else [])
    beds_count = Bed.query.count()
    vacant_count = Bed.query.filter_by(status="Vacant").count()
    labs = LabInvestigation.query.all() if u.role in ("clinic","admin","lab") else (LabInvestigation.query.filter_by(patient_id=p.id).all() if p else [])
    docs_count = MedicalDocument.query.count()
    return page("""<h1>Dashboard</h1><p>Welcome, <b>{{u.username}}</b> (Role: <b>{{u.role}}</b>)</p>
    <div class="grid">
      <article class="card"><h3>Bed Occupancy</h3><p><b>{{vacant_count}}</b> Vacant / <b>{{beds_count}}</b> Total Beds</p><a class="btn" href="/atd/beds">View Bed Status</a></article>
      <article class="card"><h3>Diagnostics (LIS/RIS)</h3><p><b>{{labs|length}}</b> Lab/Radiology Orders</p><a class="btn" href="/lis/queue">Open LIS Queue</a></article>
      <article class="card"><h3>EMR Documents</h3><p><b>{{docs_count}}</b> Uploaded Reports/Scans</p><a class="btn" href="/emr/records">Open EMR Portal</a></article>
    </div>
    <section class="card"><h2>Recent Appointments / Encounters</h2>
    <div class="tablewrap"><table><tr><th>ID</th><th>Patient</th><th>Department</th><th>Date/Time</th><th>Status</th></tr>
    {% for a in appointments %}<tr><td>CH-APT-{{a.id}}</td><td>{{a.patient.given_name}} ({{a.patient.identifier}})</td>
    <td>{{a.detail.department if a.detail else 'General'}}</td><td>{{a.start}}</td><td>{{a.status}}</td></tr>{% endfor %}</table></div></section>""", u=u, vacant_count=vacant_count, beds_count=beds_count, appointments=appointments, labs=labs, docs_count=docs_count)

@app.route("/register-patient", methods=["GET","POST"])
@login_required
def register_patient():
    u = current_user()
    target = u
    if request.method == "POST" and u.role in ("clinic","admin"):
        target = db.session.get(User, request.form.get("user_id", type=int))
    p = Patient.query.filter_by(user_id=target.id).first() if target else None
    profile = PatientProfile.query.filter_by(patient_id=p.id).first() if p else None
    if request.method == "POST":
        if not p: p = ensure_patient(target)
        p.given_name = request.form.get("given_name","").strip()
        p.family_name = request.form.get("family_name","").strip()
        if not profile:
            profile = PatientProfile(patient_id=p.id); db.session.add(profile)
        profile.gender = request.form.get("gender","")
        profile.dob = request.form.get("dob","")
        profile.mobile = request.form.get("mobile","")
        profile.address = request.form.get("address","")
        profile.payer_type = request.form.get("payer_type","Direct Patient")
        profile.nationality = request.form.get("nationality","Indian")
        db.session.commit()
        flash(f"Patient registered successfully! UHID Generated: {p.identifier}")
        return redirect(url_for("dashboard"))
    patients = User.query.filter_by(role="patient").all() if u.role in ("clinic","admin") else []
    return page("""<section class="formcard"><h1>Patient Registration &amp; Demographics</h1>
    <form method="post"><input type="hidden" name="csrf_token" value="{{csrf_token()}}">
    {% if u.role in ['clinic','admin'] %}<label>Select Patient Account</label><select name="user_id">{% for x in patients %}<option value="{{x.id}}">{{x.username}}</option>{% endfor %}</select>{% endif %}
    <div class="grid">
      <div><label>First Name *</label><input name="given_name" value="{{p.given_name if p else ''}}" required></div>
      <div><label>Last Name</label><input name="family_name" value="{{p.family_name if p else ''}}"></div>
      <div><label>Gender</label><select name="gender"><option>Female</option><option>Male</option><option>Other</option></select></div>
      <div><label>Date of Birth</label><input type="date" name="dob" value="{{profile.dob if profile else ''}}"></div>
      <div><label>Mobile No. *</label><input name="mobile" value="{{profile.mobile if profile else ''}}" required></div>
      <div><label>Nationality</label><input name="nationality" value="{{profile.nationality if profile else 'Indian'}}"></div>
      <div><label>Payer Type</label><select name="payer_type"><option>Direct Patient</option><option>Company (Credit)</option><option>Insurance</option></select></div>
    </div>
    <label>Address</label><textarea name="address" rows="2">{{profile.address if profile else ''}}</textarea>
    <button>Save &amp; Generate UHID</button></form>
    {% if p %}<p class="notice"><b>Active UHID:</b> {{p.identifier}}</p>{% endif %}</section>""", u=u, p=p, profile=profile, patients=patients)

@app.route("/atd/beds")
@login_required
def atd_beds():
    beds = Bed.query.all()
    patients = Patient.query.all()
    return page("""<h1>ATD - Bed Status &amp; Management</h1>
    <div class="grid">
      {% for b in beds %}
      <article class="card" style="border-top:5px solid {% if b.status=='Vacant' %}var(--green){% elif b.status=='Occupied' %}var(--orange){% else %}var(--red){% endif %}">
        <h3>{{b.bed_no}}</h3>
        <p><b>Ward:</b> {{b.ward_name}}<br><b>Category:</b> {{b.bed_category}}<br><b>Status:</b> <span class="badge {% if b.status=='Vacant' %}bg-vacant{% elif b.status=='Occupied' %}bg-occupied{% else %}bg-repair{% endif %}">{{b.status}}</span></p>
        {% if b.status=='Vacant' %}
        <form method="post" action="/atd/admit">
          <input type="hidden" name="csrf_token" value="{{csrf_token()}}">
          <input type="hidden" name="bed_id" value="{{b.id}}">
          <select name="patient_id" required>{% for pat in patients %}<option value="{{pat.id}}">{{pat.given_name}} ({{pat.identifier}})</option>{% endfor %}</select>
          <button style="padding:6px 10px;font-size:.9rem;">Admit Patient</button>
        </form>
        {% else %}
        <form method="post" action="/atd/discharge">
          <input type="hidden" name="csrf_token" value="{{csrf_token()}}">
          <input type="hidden" name="bed_id" value="{{b.id}}">
          <button style="background:var(--orange);padding:6px 10px;font-size:.9rem;">Discharge / Release</button>
        </form>
        {% endif %}
      </article>
      {% endfor %}
    </div>""", beds=beds, patients=patients)

@app.route("/atd/admit", methods=["POST"])
@login_required
def atd_admit():
    bed = db.session.get(Bed, request.form.get("bed_id", type=int))
    pat_id = request.form.get("patient_id", type=int)
    if bed and bed.status == "Vacant":
        bed.status = "Occupied"
        bed.patient_id = pat_id
        db.session.commit()
        flash(f"Patient successfully admitted to bed {bed.bed_no}!")
    return redirect(url_for("atd_beds"))

@app.route("/atd/discharge", methods=["POST"])
@login_required
def atd_discharge():
    bed = db.session.get(Bed, request.form.get("bed_id", type=int))
    if bed:
        bed.status = "House Keeping"
        bed.patient_id = None
        db.session.commit()
        flash(f"Patient discharged. Bed {bed.bed_no} moved to Housekeeping.")
    return redirect(url_for("atd_beds"))

@app.route("/lis/queue")
@login_required
def lis_queue():
    investigations = LabInvestigation.query.all()
    patients = Patient.query.all()
    return page("""<h1>Diagnostics Management (LIS / RIS)</h1>
    <section class="card"><h3>Order New Investigation</h3>
    <form method="post" action="/lis/order">
      <input type="hidden" name="csrf_token" value="{{csrf_token()}}">
      <div class="grid">
        <div><label>Patient</label><select name="patient_id">{% for p in patients %}<option value="{{p.id}}">{{p.given_name}} - {{p.identifier}}</option>{% endfor %}</select></div>
        <div><label>Modality</label><select name="modality"><option value="LIS">LIS (Laboratory Test)</option><option value="RIS">RIS (Radiology/X-Ray)</option></select></div>
        <div><label>Service Name</label><input name="service_name" placeholder="e.g. CBC or X-Ray Chest" required></div>
      </div><button>Place Lab Order</button>
    </form></section>
    <section class="card"><h3>Sample &amp; Result Status Queue</h3>
    <div class="tablewrap"><table><tr><th>Lab No</th><th>Patient</th><th>Modality</th><th>Test / Service</th><th>Status</th><th>Action</th></tr>
    {% for l in investigations %}
    <tr><td>{{l.lab_no}}</td><td>{{l.patient.given_name}}</td><td>{{l.modality}}</td><td>{{l.service_name}}</td>
    <td><b>{{l.sample_status}}</b></td>
    <td>
      <form method="post" action="/lis/update-status" style="display:flex;gap:6px;">
        <input type="hidden" name="csrf_token" value="{{csrf_token()}}">
        <input type="hidden" name="lab_id" value="{{l.id}}">
        <select name="status" style="margin:0;"><option>Dept. Acknowledged</option><option>Result Entered</option><option>Result Finalized</option></select>
        <button style="padding:5px 10px;font-size:.85rem;">Update</button>
      </form>
    </td></tr>
    {% endfor %}</table></div></section>""", investigations=investigations, patients=patients)

@app.route("/lis/order", methods=["POST"])
@login_required
def lis_order():
    pat_id = request.form.get("patient_id", type=int)
    mod = request.form.get("modality","LIS")
    srv = request.form.get("service_name","")
    lab_no = f"LAB-{datetime.utcnow():%y%m%d}-{int(datetime.utcnow().timestamp())%10000}"
    db.session.add(LabInvestigation(patient_id=pat_id, lab_no=lab_no, modality=mod, service_name=srv, sample_status="Collected"))
    db.session.commit()
    flash(f"Investigation order created with Lab No: {lab_no}")
    return redirect(url_for("lis_queue"))

@app.route("/lis/update-status", methods=["POST"])
@login_required
def lis_update_status():
    lab = db.session.get(LabInvestigation, request.form.get("lab_id", type=int))
    status = request.form.get("status")
    if lab and status in ("Dept. Acknowledged", "Result Entered", "Result Finalized"):
        lab.sample_status = status
        db.session.commit()
        flash(f"Lab status updated to {status}!")
    return redirect(url_for("lis_queue"))

@app.route("/emr/records", methods=["GET","POST"])
@login_required
def emr_records():
    u = current_user()
    patients = Patient.query.all()
    if request.method == "POST":
        pat_id = request.form.get("patient_id", type=int)
        doc_type = request.form.get("doc_type", "Lab Report")
        if 'file' not in request.files:
            flash("No file part provided.")
            return redirect(url_for('emr_records'))
        file = request.files['file']
        if file and file.filename != '':
            filename = secure_filename(file.filename)
            unique_filename = f"{datetime.utcnow():%Y%m%d%H%M%S}_{filename}"
            os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_filename))
            db.session.add(MedicalDocument(patient_id=pat_id, filename=unique_filename, original_name=filename, doc_type=doc_type))
            db.session.commit()
            flash("Document / Lab Report / Camera capture uploaded successfully into EMR!")
            return redirect(url_for('emr_records'))
        else:
            flash("Please capture or select a valid file.")
    documents = MedicalDocument.query.all()
    return page("""<h1>EMR &amp; Clinical Document Upload (Camera / Reports)</h1>
    <section class="card"><h3>Upload Lab Report, Prescription, or Capture via Camera</h3>
    <form method="post" enctype="multipart/form-data">
      <input type="hidden" name="csrf_token" value="{{csrf_token()}}">
      <div class="grid">
        <div><label>Select Patient</label><select name="patient_id" required>{% for p in patients %}<option value="{{p.id}}">{{p.given_name}} ({{p.identifier}})</option>{% endfor %}</select></div>
        <div><label>Document Type</label><select name="doc_type"><option>Lab Report</option><option>X-Ray / Scan</option><option>Prescription</option><option>Discharge Summary</option></select></div>
        <div>
          <label><b>Choose File or Camera Capture:</b></label>
          <input type="file" name="file" accept="image/*,application/pdf" capture="environment" required>
        </div>
      </div><button>Upload to EMR</button>
    </form></section>
    <section class="card"><h3>Uploaded EMR Files &amp; Reports</h3>
    <div class="tablewrap"><table><tr><th>ID</th><th>Patient</th><th>Type</th><th>File Name</th><th>Date</th><th>Action</th></tr>
    {% for d in documents %}
    <tr><td>#{{d.id}}</td><td>{{d.patient.given_name}} ({{d.patient.identifier}})</td><td>{{d.doc_type}}</td><td>{{d.original_name}}</td><td>{{d.uploaded_at.strftime('%Y-%m-%d %H:%M')}}</td>
    <td><a class="btn" style="padding:4px 8px;font-size:0.85rem;" href="{{ url_for('static', filename='uploads/' + d.filename) }}" target="_blank">View / Download</a></td></tr>
    {% endfor %}</table></div></section>""", patients=patients, documents=documents)

@app.cli.command("init-demo")
def init_demo():
    db.create_all()

    for uname, pwd, role in [
        ("demo_patient", "PatientDemo-ChangeMe!", "patient"),
        ("demo_clinic", "ClinicDemo-ChangeMe!", "clinic"),
        ("demo_lab", "LabDemo-ChangeMe!", "lab"),
    ]:
        u = User.query.filter_by(username=uname).first()

        if not u:
            u = User(username=uname, role=role)

        u.role = role
        u.set_password(pwd)
        db.session.add(u)

    if Bed.query.count() == 0:
        for ward, cat, bno in [
            ("Fourth Floor", "DOUBLE BEDED", "405-A"),
            ("Fourth Floor", "DOUBLE BEDED", "405-B"),
            ("Basement 2", "ISOLATION", "ISOLATION-1"),
            ("Basement 2", "ISOLATION", "ISOLATION-2"),
            ("First Floor", "CCU", "CCU-01"),
            ("First Floor", "MICU", "MICU-01"),
        ]:
            db.session.add(
                Bed(ward_name=ward, bed_category=cat, bed_no=bno, status="Vacant")
            )

    db.session.commit()
    print("Database initialized with demo users and ATD beds.")

with app.app_context():
    db.create_all()

if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG","0")=="1")
