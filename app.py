import os, secrets, json
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, Response
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

class SiteSetting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False)
    value = db.Column(db.Text, default="")

class Project(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(160), nullable=False)
    category = db.Column(db.String(100), nullable=False)
    condition = db.Column(db.String(50), default="جديد")  # إضافة حقل الحالة (جديد / مستعمل)
    description = db.Column(db.Text, default="")
    price = db.Column(db.String(100), default="")
    phone = db.Column(db.String(80), default="")
    featured = db.Column(db.Boolean, default=False)
    images = db.relationship("ProjectImage", cascade="all, delete-orphan", backref="project", lazy=True)

class ProjectImage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("project.id"), nullable=False)
    url = db.Column(db.Text, nullable=False)
    public_id = db.Column(db.String(255), default="")

class PendingAd(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(160), nullable=False)
    category = db.Column(db.String(100), nullable=False)
    condition = db.Column(db.String(50), default="جديد")  # حالة الإعلان المعلق
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

def get_setting(key, default=""):
    s = SiteSetting.query.filter_by(key=key).first()
    return s.value if s and s.value else default

def set_setting(key, value):
    s = SiteSetting.query.filter_by(key=key).first()
    if not s:
        s = SiteSetting(key=key, value=value)
        db.session.add(s)
    else:
        s.value = value
    db.session.commit()

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
    condition = request.args.get("condition","").strip()  # تصفية حسب جديد أو مستعمل
    
    q = Project.query
    if category:
        q = q.filter_by(category=category)
    if condition:
        q = q.filter_by(condition=condition)
        
    projects = q.order_by(Project.featured.desc(), Project.id.desc()).all()
    categories = [r[0] for r in db.session.query(Project.category).distinct().order_by(Project.category).all()]
    
    config = {
        "main_title": get_setting("main_title", "منصة الحراج والخدمات الشاملة"),
        "subtitle": get_setting("subtitle", "أضف إعلانك بكل سهولة وتصفح مختلف الأقسام"),
        "bg_color": get_setting("bg_color", "#0b0f19"),
        "primary_color": get_setting("primary_color", "#d97706"),
        "text_color": get_setting("text_color", "#f3f4f6"),
        "hero_image": get_setting("hero_image", ""),
        "profile_image": get_setting("profile_image", "")
    }
    return render_template("index.html", projects=projects, categories=categories, active_category=category, active_condition=condition, config=config)

@app.route("/project/<int:project_id>")
def project(project_id):
    p = Project.query.get_or_404(project_id)
    config = {
        "main_title": get_setting("main_title", "منصة الحراج والخدمات الشاملة"),
        "primary_color": get_setting("primary_color", "#d97706"),
        "text_color": get_setting("text_color", "#f3f4f6"),
        "bg_color": get_setting("bg_color", "#0b0f19")
    }
    return render_template("project.html", project=p, config=config)

@app.post("/submit-ad")
def submit_ad():
    title = request.form.get("title","").strip()
    sel_cat = request.form.get("category","").strip()
    custom_cat = request.form.get("custom_category","").strip()
    category = custom_cat if sel_cat == "أخرى_كتب_بنفسك" and custom_cat else sel_cat
    
    condition = request.form.get("condition","جديد").strip()
    description = request.form.get("details","").strip()
    price = request.form.get("price","").strip()
    phone = request.form.get("phone","").strip()
    
    if not title or not category or not phone:
        flash("يرجى إكمال الحقول الأساسية ورقم الجوال", "error")
        return redirect(url_for("home")+"#add-ad")
        
    ad = PendingAd(title=title, category=category, condition=condition, description=description, price=price, phone=phone)
    db.session.add(ad)
    db.session.flush()
    
    for f in request.files.getlist("images"):
        url, public_id = upload_image(f)
        if url:
            db.session.add(PendingAdImage(pending_ad_id=ad.id, url=url, public_id=public_id))
            
    db.session.commit()
    flash("تم إرسال إعلانك بنجاح وسيتم مراجعته ونشره قريباً", "success")
    return redirect(url_for("home"))

@app.route("/secure-admin-login-x99", methods=["GET","POST"])
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

@app.get("/secure-admin-panel-x99")
@admin_required
def admin():
    projects = Project.query.order_by(Project.id.desc()).all()
    pending_ads = PendingAd.query.order_by(PendingAd.id.desc()).all()
    orders = Order.query.order_by(Order.id.desc()).all()
    config = {
        "main_title": get_setting("main_title", ""),
        "subtitle": get_setting("subtitle", ""),
        "bg_color": get_setting("bg_color", "#0b0f19"),
        "primary_color": get_setting("primary_color", "#d97706"),
        "text_color": get_setting("text_color", "#f3f4f6"),
        "hero_image": get_setting("hero_image", ""),
        "profile_image": get_setting("profile_image", "")
    }
    return render_template("admin.html", projects=projects, pending_ads=pending_ads, orders=orders, config=config)

@app.get("/admin/backup")
@admin_required
def export_backup():
    data = {
        "settings": [{"key": s.key, "value": s.value} for s in SiteSetting.query.all()],
        "projects": [{
            "title": p.title, "category": p.category, "condition": getattr(p, "condition", "جديد"), "description": p.description,
            "price": p.price, "phone": p.phone, "featured": p.featured,
            "images": [{"url": img.url, "public_id": img.public_id} for img in p.images]
        } for p in Project.query.all()]
    }
    json_str = json.dumps(data, ensure_ascii=False, indent=4)
    return Response(
        json_str,
        mimetype="application/json",
        headers={"Content-Disposition": "attachment;filename=store_backup.json"}
    )

@app.post("/admin/restore")
@admin_required
def import_backup():
    file = request.files.get("backup_file")
    if not file or not file.filename.endswith(".json"):
        flash("يرجى اختيار ملف نسخة احتياطية بصيغة JSON صحيح", "error")
        return redirect(url_for("admin"))
    try:
        content = file.read().decode("utf-8")
        data = json.loads(content)
        if "settings" in data:
            for s in data["settings"]:
                set_setting(s["key"], s["value"])
        if "projects" in data:
            for item in data["projects"]:
                p = Project(
                    title=item.get("title",""),
                    category=item.get("category",""),
                    condition=item.get("condition","جديد"),
                    description=item.get("description",""),
                    price=item.get("price",""),
                    phone=item.get("phone",""),
                    featured=item.get("featured", False)
                )
                db.session.add(p)
                db.session.flush()
                for img in item.get("images", []):
                    db.session.add(ProjectImage(project_id=p.id, url=img.get("url",""), public_id=img.get("public_id","")))
            db.session.commit()
        flash("تمت استعادة كافة المنتجات والبيانات بنجاح", "success")
    except Exception as e:
        flash("حدث خطأ أثناء القراءة", "error")
    return redirect(url_for("admin"))

@app.post("/admin/settings")
@admin_required
def update_settings():
    set_setting("main_title", request.form.get("main_title", "").strip())
    set_setting("subtitle", request.form.get("subtitle", "").strip())
    set_setting("bg_color", request.form.get("bg_color", "#0b0f19").strip())
    set_setting("primary_color", request.form.get("primary_color", "#d97706").strip())
    set_setting("text_color", request.form.get("text_color", "#f3f4f6").strip())
    
    if request.form.get("remove_hero"):
        set_setting("hero_image", "")
    else:
        hero_file = request.files.get("hero_image")
        if hero_file and hero_file.filename:
            url, _ = upload_image(hero_file)
            if url:
                set_setting("hero_image", url)
            
    if request.form.get("remove_profile"):
        set_setting("profile_image", "")
    else:
        prof_file = request.files.get("profile_image")
        if prof_file and prof_file.filename:
            url, _ = upload_image(prof_file)
            if url:
                set_setting("profile_image", url)
            
    flash("تم تحديث الإعدادات بنجاح", "success")
    return redirect(url_for("admin"))

@app.post("/admin/pending/<int:ad_id>/approve")
@admin_required
def approve_ad(ad_id):
    ad = PendingAd.query.get_or_404(ad_id)
    p = Project(
        title=ad.title,
        category=ad.category,
        condition=ad.condition,
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
    sel_cat = request.form.get("category","").strip()
    custom_cat = request.form.get("custom_category","").strip()
    category = custom_cat if sel_cat == "أخرى_كتب_بنفسك" and custom_cat else sel_cat
    
    p = Project(
        title=request.form.get("title","").strip(),
        category=category,
        condition=request.form.get("condition","جديد").strip(),
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

@app.post("/admin/project/<int:project_id>/edit")
@admin_required
def edit_project(project_id):
    p = Project.query.get_or_404(project_id)
    sel_cat = request.form.get("category","").strip()
    custom_cat = request.form.get("custom_category","").strip()
    category = custom_cat if sel_cat == "أخرى_كتب_بنفسك" and custom_cat else sel_cat
    
    p.title = request.form.get("title","").strip()
    p.category = category
    p.condition = request.form.get("condition","جديد").strip()
    p.description = request.form.get("description","").strip()
    p.price = request.form.get("price","").strip()
    p.phone = request.form.get("phone","").strip()
    p.featured = bool(request.form.get("featured"))
    for f in request.files.getlist("images"):
        url, public_id = upload_image(f)
        if url:
            db.session.add(ProjectImage(project_id=p.id, url=url, public_id=public_id))
    db.session.commit()
    flash("تم حفظ التعديل", "success")
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

@app.post("/admin/image/<int:image_id>/delete")
@admin_required
def delete_image(image_id):
    img = ProjectImage.query.get_or_404(image_id)
    delete_cloud_image(img.public_id)
    db.session.delete(img)
    db.session.commit()
    return redirect(url_for("admin"))

@app.post("/admin/order/<int:order_id>/status")
@admin_required
def order_status(order_id):
    o = Order.query.get_or_404(order_id)
    o.status = request.form.get("status","جديد")
    db.session.commit()
    return redirect(url_for("admin"))

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")))
