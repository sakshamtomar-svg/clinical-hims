import os
from datetime import datetime
from functools import wraps
from flask import Flask, request, redirect, url_for, session, flash, jsonify, render_template_string
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
CSRFProtect(app)
app.secret_key = os.environ.get("SECRET_KEY", "LOCAL-DEMO-ONLY-change-before-deploy")
db_url = os.environ.get("DATABASE_URL", "sqlite:///clinical_hims.db")
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # patient, clinic, admin
    def set_password(self, password): self.password_hash = generate_password_hash(password)
    def check_password(self, password): return check_password_hash(self.password_hash, password)

class Patient(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), unique=True)
    identifier = db.Column(db.String(40), unique=True, nullable=False)
    given_name = db.Column(db.String(100), nullable=False)
    family_name = db.Column(db.String(100), default="")
    appointments = db.relationship("Appointment", backref="patient", lazy=True)

class Appointment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey("patient.id"), nullable=False)
    start = db.Column(db.String(30), nullable=False)
    reason = db.Column(db.String(250), default="")
    status = db.Column(db.String(20), default="booked")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class AuditEvent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80))
    action = db.Column(db.String(100))
    resource = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

def current_user():
    if "uid" not in session: return None
    return db.session.get(User, session["uid"])

def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_user():
            flash("Please sign in first.")
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper

BASE = """
<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Clinical HIMS</title><style>
:root{--teal:#087e8b;--ink:#173344;--muted:#637783;--line:#dce7eb}
*{box-sizing:border-box}body{margin:0;background:#f2f8fa;color:var(--ink);font:16px/1.5 Arial,sans-serif}
nav{display:flex;justify-content:space-between;align-items:center;padding:15px 5%;background:white;border-bottom:1px solid var(--line)}
nav a{color:var(--ink);text-decoration:none;margin-left:14px}.brand{font-weight:800;color:var(--teal);font-size:1.15rem}
main{width:min(1050px,92%);margin:28px auto;min-height:72vh}.hero,.card,.formcard,.stat{background:white;border:1px solid var(--line);border-radius:18px;padding:24px;margin-bottom:18px}
.hero{padding:clamp(28px,6vw,64px);background:linear-gradient(135deg,#e0f5f3,#fff 65%,#e8efff)}
h1{font-size:clamp(2rem,5vw,3.6rem);line-height:1.08;margin:10px 0}h1 span{color:var(--teal)}p,.muted{color:var(--muted)}
button,.btn{background:var(--teal);color:white;border:0;border-radius:9px;padding:11px 16px;text-decoration:none;display:inline-block;font-weight:bold;cursor:pointer}
input,select{width:100%;padding:11px;border:1px solid var(--line);border-radius:8px;font:inherit;margin:4px 0 12px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:14px}.notice{padding:12px 15px;border-radius:9px;background:#fff4d6;margin:12px 0}
table{width:100%;border-collapse:collapse;min-width:650px}td,th{text-align:left;padding:11px;border-bottom:1px solid var(--line)}th{color:var(--muted);font-size:.82rem}.tablewrap{overflow-x:auto}
small{color:var(--muted)}footer{text-align:center;color:var(--muted);padding:22px;font-size:.85rem}
</style></head><body><nav><a class="brand" href="/">Clinical HIMS</a><div>{% if user %}<a href="/dashboard">Dashboard</a><a href="/logout">Log out</a>{% else %}<a href="/login">Log in</a>{% endif %}</div></nav>
<main>{% with msgs=get_flashed_messages() %}{% for m in msgs %}<div class="notice">{{m}}</div>{% endfor %}{% endwith %}{{body|safe}}</main><footer>NEEEV demo prototype • Fictional data only • Not for clinical decisions</footer></body></html>
"""

def page(body, **kwargs):
    return render_template_string(BASE, body=render_template_string(body, **kwargs), user=current_user())

@app.route("/")
def home():
    return page("""
    <section class="hero"><small>CONNECTED CARE • INTEROPERABILITY-READY DESIGN</small>
    <h1>One Patient.<br><span>One Health Journey.</span></h1>
    <p>Responsive healthcare workflow demo for laptop, smart board and phones.</p>
    <a class="btn" href="/login">Open demo login</a>
    <a class="btn" style="background:white;color:#087e8b;border:1px solid #087e8b" href="/api/fhir/Appointment">FHIR-style API</a></section>
    <section class="grid"><article class="card"><h3>Patient portal</h3><p>Book appointments and track status.</p></article><article class="card"><h3>Clinic dashboard</h3><p>View bookings and update status.</p></article><article class="card"><h3>Shared database</h3><p>Updates appear for authorized users.</p></article></section>
    <div class="notice">Prototype only. Do not enter real patient information. FHIR-style output is not full FHIR compliance.</div>""
    @app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        given_name = request.form.get("given_name", "").strip()
        family_name = request.form.get("family_name", "").strip()

        if not username or not password or not given_name:
            flash("Please fill all required fields.")
            return redirect(url_for("register"))

        if len(password) < 8:
            flash("Password must be at least 8 characters.")
            return redirect(url_for("register"))

        if User.query.filter_by(username=username).first():
            flash("Username already exists. Choose another.")
            return redirect(url_for("register"))

        import secrets
        user = User(username=username, role="patient")
        user.set_password(password)
        db.session.add(user)
        db.session.flush()

        patient = Patient(
            user_id=user.id,
            identifier="CH-" + secrets.token_hex(4).upper(),
            given_name=given_name,
            family_name=family_name
        )
        db.session.add(patient)
        db.session.add(AuditEvent(
            username=username,
            action="register",
            resource="Patient:" + patient.identifier
        ))
        db.session.commit()

        session.clear()
        session["uid"] = user.id
        flash("Registration successful! Your demo Patient ID is " + patient.identifier)
        return redirect(url_for("dashboard"))

    return page("""
    <section class="formcard" style="max-width:550px;margin:auto">
      <h1>Patient Registration</h1>
      <p>Create your demo patient account.</p>
      <form method="post">
        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">

        <label>First name *</label>
        <input name="given_name" required maxlength="100">

        <label>Last name</label>
        <input name="family_name" maxlength="100">

        <label>Username *</label>
        <input name="username" required maxlength="80">

        <label>Password (minimum 8 characters) *</label>
        <input name="password" type="password" required minlength="8"
               autocomplete="new-password">

        <button type="submit">Register Patient</button>
      </form>
      <p><a href="/login">Already registered? Log in</a></p>
    </section>
    """)
@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        u = User.query.filter_by(username=request.form.get("username","").strip()).first()
        if u and u.check_password(request.form.get("password","")):
            session.clear(); session["uid"] = u.id
            return redirect(url_for("dashboard"))
        flash("Login failed. Check username and password.")
    return page("""<section class="formcard" style="max-width:500px;margin:auto"><h1>Sign in</h1>
    <form method="post"><input type="hidden" name="csrf_token" value="{{ csrf_token( ) }}"><label>Username</label><input name="username" required autocomplete="username">
    <label>Password</label><input name="password" type="password" required autocomplete="current-password">
    <button type="submit">Log in</button></form><p class="muted">Demo accounts are created by the site administrator.</p></section>""")

@app.route("/logout")
def logout():
    session.clear(); return redirect(url_for("home"))

@app.route("/dashboard")
@login_required
def dashboard():
    u = current_user()
    if u.role in ("clinic","admin"):
        rows = Appointment.query.order_by(Appointment.start).all()
    else:
        p = Patient.query.filter_by(user_id=u.id).first()
        rows = Appointment.query.filter_by(patient_id=p.id).order_by(Appointment.start).all() if p else []
    html = """<h1 style="font-size:2.5rem">Dashboard</h1><p>Signed in as <b>{{u.username}}</b> · Role: {{u.role}}</p>
    {% if u.role == 'patient' %}<section class="card"><h2>Book an appointment</h2><form method="post" action="/appointments/new"><input type="hidden" name="csrf_token" value="{{ csrf_token( ) }}">
    <label>Date and time</label><input name="start" type="datetime-local" required><label>Reason (demo only)</label><input name="reason" maxlength="250">
    <button>Confirm booking</button></form></section>{% endif %}
    <section class="card"><h2>Appointments ({{rows|length}})</h2>{% if rows %}<div class="tablewrap"><table><tr><th>Patient ID</th><th>Patient</th><th>Date/time</th><th>Reason</th><th>Status</th>{% if u.role in ['clinic','admin'] %}<th>Update</th>{% endif %}</tr>
    {% for a in rows %}<tr><td>{{a.patient.identifier}}</td><td>{{a.patient.given_name}} {{a.patient.family_name}}</td><td>{{a.start}}</td><td>{{a.reason or '—'}}</td><td>{{a.status}}</td>
    {% if u.role in ['clinic','admin'] %}<td><form method="post" action="/appointments/{{a.id}}/status"><input type="hidden" name="csrf_token" value="{{ csrf_token( ) }}"><select name="status">{% for s in ['booked','arrived','in-progress','fulfilled','cancelled'] %}<option {% if a.status==s %}selected{% endif %}>{{s}}</option>{% endfor %}</select><button>Save</button></form></td>{% endif %}</tr>{% endfor %}</table></div>{% else %}<p class="muted">No appointments yet.</p>{% endif %}</section>"""
    return page(html, u=u, rows=rows)

@app.route("/appointments/new", methods=["POST"])
@login_required
def new_appointment():
    u = current_user()
    if u.role != "patient":
        return "Only patient demo accounts can book appointments.", 403
    p = Patient.query.filter_by(user_id=u.id).first()
    if not p:
        p = Patient(user_id=u.id, identifier=f"DEMO-{u.id}", given_name=u.username)
        db.session.add(p); db.session.commit()
    a = Appointment(patient_id=p.id, start=request.form["start"], reason=request.form.get("reason","")[:250], status="booked")
    db.session.add(a); db.session.flush()
    db.session.add(AuditEvent(username=u.username, action="create", resource="Appointment:"+str(a.id)))
    db.session.commit()
    flash("Appointment booked. Clinic dashboard can now see it.")
    return redirect(url_for("dashboard"))

@app.route("/appointments/<int:aid>/status", methods=["POST"])
@login_required
def update_status(aid):
    u = current_user()
    if u.role not in ("clinic","admin"): return "Forbidden", 403
    a = db.session.get(Appointment, aid)
    if not a: return "Not found", 404
    status = request.form.get("status")
    if status not in ("booked","arrived","in-progress","fulfilled","cancelled"): return "Invalid status", 400
    a.status = status
    db.session.add(AuditEvent(username=u.username, action="update_status", resource="Appointment:"+str(a.id)))
    db.session.commit()
    flash("Appointment status updated.")
    return redirect(url_for("dashboard"))

@app.route("/api/fhir/Patient")
@app.route("/api/fhir/Patient/")
@login_required
def fhir_patients():
    u = current_user()
    if u.role not in ("clinic","admin"): return jsonify({"detail":"Forbidden"}), 403
    patients = Patient.query.order_by(Patient.id).all()
    return jsonify({"resourceType":"Bundle","type":"searchset","total":len(patients),"entry":[{"resource":{
        "resourceType":"Patient","id":p.identifier,"active":True,
        "name":[{"use":"official","family":p.family_name,"given":[p.given_name]}]
    }} for p in patients]})

@app.route("/api/fhir/Appointment")
@app.route("/api/fhir/Appointment/")
@login_required
def fhir_appointments():
    u = current_user()
    if u.role in ("clinic","admin"):
        rows = Appointment.query.order_by(Appointment.start).all()
    elif u.role == "patient":
        p = Patient.query.filter_by(user_id=u.id).first()
        rows = Appointment.query.filter_by(patient_id=p.id).all() if p else []
    else:
        return jsonify({"detail":"Forbidden"}), 403
    return jsonify({"resourceType":"Bundle","type":"searchset","total":len(rows),"entry":[{"resource":{
        "resourceType":"Appointment","id":str(a.id),"status":a.status,"start":a.start,
        "description":a.reason,"participant":[{"actor":{"reference":"Patient/"+a.patient.identifier}}]
    }} for a in rows]})

@app.cli.command("init-demo")
def init_demo():
    """Create database and demo users; override passwords using environment variables."""
    db.create_all()
    accounts = [
        ("demo_patient", os.environ.get("DEMO_PATIENT_PASSWORD","PatientDemo-ChangeMe!"), "patient"),
        ("demo_clinic", os.environ.get("DEMO_CLINIC_PASSWORD","ClinicDemo-ChangeMe!"), "clinic"),
    ]
    for username, password, role in accounts:
        user = User.query.filter_by(username=username).first()
        if not user:
            user = User(username=username, role=role); user.set_password(password); db.session.add(user)
    db.session.commit()
    print("Demo users created if missing. Change their passwords before sharing the site.")

with app.app_context():
    db.create_all()

if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG","0")=="1")
