import os, secrets
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename

try:
    import cloudinary
    import cloudinary.uploader
except Exception:
    cloudinary = None

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "change-this-in-production")
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024

db_url = os.getenv("DATABASE_URL", "sqlite:///store.db")
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

UPLOAD_DIR = os.path.join(app.root_path, "static", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
ALLOWED = {"png","jpg","jpeg","webp"}

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "ChangeMe123!")

if cloudinary and os.getenv("CLOUDINARY_CLOUD_NAME"):
    cloudinary.config(
        cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
        api_key=os.getenv("CLOUDINARY_API_KEY"),
        api_secret=os.getenv("CLOUDINARY_API_SECRET"),
        secure=True
    )

# جدول الإعلانات المنشورة في الموقع
class Project(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(160), nullable=False)
    category = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, default="")
    price = db.Column(db.String(100), default="")
    phone = db.Column(db.String(80), default="") # تم إضافة رقم التواصل
    featured = db.Column(db.Boolean, default=False)
    images = db.relationship("ProjectImage", cascade="all, delete-orphan", backref="project", lazy=True)

class ProjectImage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("project.id"), nullable=False)
    url = db.Column(db.Text, nullable=False)
    public_id = db.Column(db.String(255), default="")

# جدول الإعلانات المعلقة (بانتظار موافقة الإدارة)
class PendingAd(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(160), nullable=False)
    category = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, default="")
    price = db.Column(db.String(100), default="")
    phone = db.Column(db.String(80), nullable=False)
    images = db.relationship("PendingAdImage", cascade="all, delete-orphan", backref="pending_ad", lazy=True)

class PendingAdImage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    pending_ad_id = db.Column(db.Integer, db.ForeignKey("pending_ad.id"), nullable=False)
    url = db.Column(db.Text, nullable=False)
    public_id = db.Column(db.String(255), default="")

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(80), nullable=False)
    service = db.Column(db.String(160), nullable=False)
    details = db.Column(db.Text, default="")
    status = db.Column(db.String(50), default="جديد")

def allowed_file(name):
    return "." in name and name.rsplit(".",1)[1].lower() in ALLOWED

def upload_image(file):
    if not file or not file.filename or not allowed_file(file.filename):
        return None, None
    if cloudinary and os.getenv("CLOUDINARY_CLOUD_NAME"):
        result = cloudinary.uploader.upload(file, folder="ahmed_store")
        return result["secure_url"], result.get("public_id","")
    filename = secrets.token_hex(8) + "_" + secure_filename(file.filename)
    path = os.path.join(UPLOAD_DIR, filename)
    file.save(path)
    return url_for("static", filename="uploads/"+filename), ""

def delete_cloud_image(public_id):
    if public_id and cloudinary and os.getenv("CLOUDINARY_CLOUD_NAME"):
        try:
            cloudinary.uploader.destroy(public_id)
        except Exception:
            pass

def admin_required(fn):
    @wraps(fn)
    def inner(*args, **kwargs):
        if not session.get("admin"):
            return redirect(url_for("admin_login"))
        return fn(*args, **kwargs)
    return inner

@app.before_request
def ensure_tables():
    db.create_all()

@app.route("/")
def home():
    category = request.args.get("category","").strip()
    q = Project.query
    if category:
        q = q.filter_by(category=category)
    projects = q.order_by(Project.featured.desc(), Project.id.desc()).all()
    categories = [r[0] for r in db.session.query(Project.category).distinct().order_by(Project.category).all()]
    return render_template("index.html", projects=projects, categories=categories, active_category=category)

@app.route("/project/<int:project_id>")
def project(project_id):
    p = Project.query.get_or_404(project_id)
    return render_template("project.html", project=p)

# مسار استقبال إعلانات الزوار ووضعها في جدول الانتظار
@app.post("/submit-ad")
def submit_ad():
    title = request.form.get("title","").strip()
    category = request.form.get("category","").strip()
    description = request.form.get("description","").strip()
    price = request.form.get("price","").strip()
    phone = request.form.get("phone","").strip()
    
    if not title or not category or not phone:
        flash("يرجى إكمال الحقول الأساسية ورقم الجوال", "error")
        return redirect(url_for("home")+"#add-ad")
        
    ad = PendingAd(title=title, category=category, description=description, price=price, phone=phone)
    db.session.add(ad)
    db.session.flush()
    
    for f in request.files.getlist("images"):
        url, public_id = upload_image(f)
        if url:
            db.session.add(PendingAdImage(pending_ad_id=ad.id, url=url, public_id=public_id))
            
    db.session.commit()
    flash("تم إرسال إعلانك بنجاح وسيتم مراجعته ونشره قريباً", "success")
    return redirect(url_for("home"))

@app.route("/admin/login", methods=["GET","POST"])
def admin_login():
    if request.method == "POST":
        u = request.form.get("username","")
        p = request.form.get("password","")
        if secrets.compare_digest(u, ADMIN_USERNAME) and secrets.compare_digest(p, ADMIN_PASSWORD):
            session["admin"] = True
            return redirect(url_for("admin"))
        flash("بيانات الدخول غير صحيحة", "error")
    return render_template("login.html")

@app.get("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("home"))

@app.get("/admin")
@admin_required
def admin():
    projects = Project.query.order_by(Project.id.desc()).all()
    pending_ads = PendingAd.query.order_by(PendingAd.id.desc()).all()
    orders = Order.query.order_by(Order.id.desc()).all()
    return render_template("admin.html", projects=projects, pending_ads=pending_ads, orders=orders)

# الموافقة على الإعلان ونقله للموقع الرئيسي
@app.post("/admin/pending/<int:ad_id>/approve")
@admin_required
def approve_ad(ad_id):
    ad = PendingAd.query.get_or_404(ad_id)
    p = Project(
        title=ad.title,
        category=ad.category,
        description=ad.description,
        price=ad.price,
        phone=ad.phone
    )
    db.session.add(p)
    db.session.flush()
    
    for img in ad.images:
        db.session.add(ProjectImage(project_id=p.id, url=img.url, public_id=img.public_id))
        
    db.session.delete(ad)
    db.session.commit()
    flash("تمت الموافقة على الإعلان ونشره", "success")
    return redirect(url_for("admin"))

# رفض أو حذف الإعلان المعلق
@app.post("/admin/pending/<int:ad_id>/delete")
@admin_required
def delete_pending_ad(ad_id):
    ad = PendingAd.query.get_or_404(ad_id)
    for img in ad.images:
        delete_cloud_image(img.public_id)
    db.session.delete(ad)
    db.session.commit()
    flash("تم رفض وحذف الإعلان", "success")
    return redirect(url_for("admin"))

@app.post("/admin/project/add")
@admin_required
def add_project():
    p = Project(
        title=request.form.get("title","").strip(),
        category=request.form.get("category","").strip(),
        description=request.form.get("description","").strip(),
        price=request.form.get("price","").strip(),
        phone=request.form.get("phone","").strip(),
        featured=bool(request.form.get("featured"))
    )
    db.session.add(p)
    db.session.flush()
    for f in request.files.getlist("images"):
        url, public_id = upload_image(f)
        if url:
            db.session.add(ProjectImage(project_id=p.id, url=url, public_id=public_id))
    db.session.commit()
    flash("تمت إضافة العمل", "success")
    return redirect(url_for("admin"))

@app.post("/admin/project/<int:project_id>/delete")
@admin_required
def delete_project(project_id):
    p = Project.query.get_or_404(project_id)
    for img in p.images:
        delete_cloud_image(img.public_id)
    db.session.delete(p)
    db.session.commit()
    flash("تم حذف العمل", "success")
    return redirect(url_for("admin"))

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")))
