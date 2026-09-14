import os, secrets, json, re
from datetime import datetime
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, Response, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text
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
if db_url and db_url.startswith("postgres://"):
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

def format_whatsapp_phone(phone):
    if not phone:
        return ""
    cleaned = re.sub(r'[^\d+]', '', str(phone).strip())
    if not cleaned:
        return ""
    if cleaned.startswith('+'):
        return cleaned.replace('+', '')
    if cleaned.startswith('966') or cleaned.startswith('20'):
        return cleaned
    if cleaned.startswith('05') and len(cleaned) == 10:
        return '966' + cleaned[1:]
    elif len(cleaned) == 9 and cleaned.startswith('5'):
        return '966' + cleaned
    if cleaned.startswith('01') and len(cleaned) == 11:
        return '20' + cleaned[1:]
    elif len(cleaned) == 10 and cleaned.startswith('1'):
        return '20' + cleaned
    return cleaned

class SiteSetting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False)
    value = db.Column(db.Text, default="")

class Project(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(160), nullable=False)
    category = db.Column(db.String(100), nullable=False)
    condition = db.Column(db.String(50), default="جديد")
    location = db.Column(db.String(120), default="")
    description = db.Column(db.Text, default="")
    price = db.Column(db.String(100), default="")
    phone = db.Column(db.String(80), default="")
    featured = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
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
    condition = db.Column(db.String(50), default="جديد")
    location = db.Column(db.String(120), default="")
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
    seller_phone = db.Column(db.String(80), default="")
    product_code = db.Column(db.String(50), default="")
    service = db.Column(db.String(160), nullable=False)
    delivery_address = db.Column(db.String(255), default="")
    delivery_needed = db.Column(db.Boolean, default=False)
    details = db.Column(db.Text, default="")
    status = db.Column(db.String(50), default="جديد")

def allowed_file(name):
    return "." in name and name.rsplit(".", 1)[1].lower() in ALLOWED

def upload_image(file):
    if not file or not file.filename or not allowed_file(file.filename):
        return None, None
    if cloudinary and os.getenv("CLOUDINARY_CLOUD_NAME"):
        result = cloudinary.uploader.upload(
            file, 
            folder="ahmed_store",
            transformation=[
                {"quality": "auto", "fetch_format": "auto"},
                {
                    "overlay": "logo",
                    "gravity": "south_east",
                    "x": 15,
                    "y": 15,
                    "opacity": 60,
                    "width": 100
                }
            ]
        )
        return result["secure_url"], result.get("public_id", "")
    
    filename = secrets.token_hex(8) + "_" + secure_filename(file.filename)
    path = os.path.join(UPLOAD_DIR, filename)
    file.save(path)
    return url_for("static", filename="uploads/" + filename), ""

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
    # التحقق التلقائي من وجود حقل created_at وإضافته لعدم حدوث أخطاء
    try:
        db.session.execute(text("SELECT created_at FROM project LIMIT 1"))
    except Exception:
        db.session.rollback()
        try:
            db.session.execute(text("ALTER TABLE project ADD COLUMN created_at DATETIME"))
            db.session.commit()
        except Exception:
            db.session.rollback()

@app.route("/")
def home():
    category = request.args.get("category", "").strip()
    condition = request.args.get("condition", "").strip()
    
    q = Project.query
    if category:
        q = q.filter_by(category=category)
    if condition:
        q = q.filter_by(condition=condition)
        
    projects = q.order_by(Project.featured.desc(), Project.created_at.desc().nullslast()).all()
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

@app.route("/get-product/<string:code>")
def get_product_by_code(code):
    code = code.strip().upper()
    try:
        if code.startswith("AH-"):
            p_id = int(code.replace("AH-", ""))
            p = Project.query.get(p_id)
            if p:
                full_info = f"اسم المنتج: {p.title} | السعر: {p.price} | الحالة: {p.condition} | الموقع: {p.location} | الوصف: {p.description}"
                return jsonify({
                    "found": True, 
                    "title": p.title, 
                    "price": p.price, 
                    "phone": format_whatsapp_phone(p.phone) if p.phone else "",
                    "full_details": full_info
                })
    except Exception:
        pass
    return jsonify({"found": False})

@app.post("/submit-ad")
def submit_ad():
    title = request.form.get("title", "").strip()
    sel_cat = request.form.get("category", "").strip()
    custom_cat = request.form.get("custom_category", "").strip()
    category = custom_cat if sel_cat == "أخرى_كتب_بنفسك" and custom_cat else sel_cat
    
    condition = request.form.get("condition", "جديد").strip()
    location = request.form.get("location", "").strip()
    description = request.form.get("details", "").strip()
    price = request.form.get("price", "").strip()
    phone = format_whatsapp_phone(request.form.get("phone", "").strip())
    
    if not title or not category or not phone:
        flash("يرجى إكمال الحقول الأساسية ورقم الجوال", "error")
        return redirect(url_for("home") + "#add-ad")
        
    ad = PendingAd(title=title, category=category, condition=condition, location=location, description=description, price=price, phone=phone)
    db.session.add(ad)
    db.session.flush()
    
    for f in request.files.getlist("images"):
        url, public_id = upload_image(f)
        if url:
            db.session.add(PendingAdImage(pending_ad_id=ad.id, url=url, public_id=public_id))
            
    db.session.commit()
    flash("تم إرسال إعلانك بنجاح وسيتم مراجعته ونشره قريباً", "success")
    return redirect(url_for("home"))

@app.post("/submit-order")
def submit_order():
    name = request.form.get("name", "").strip()
    phone = format_whatsapp_phone(request.form.get("phone", "").strip())
    product_code = request.form.get("product_code", "").strip()
    service = request.form.get("service", "طلب منتج / توصيل").strip()
    delivery_address = request.form.get("delivery_address", "").strip()
    delivery_needed = bool(request.form.get("delivery_needed"))
    user_details = request.form.get("details", "").strip()

    seller_phone = ""
    combined_details = user_details

    if product_code.upper().startswith("AH-"):
        try:
            p_id = int(product_code.upper().replace("AH-", ""))
            p = Project.query.get(p_id)
            if p:
                if p.phone:
                    seller_phone = format_whatsapp_phone(p.phone)
                ad_info = f"[تفاصيل الإعلان الكاملة - كود {product_code}]\nالعنوان: {p.title}\nالسعر: {p.price}\nالحالة: {p.condition}\nالموقع: {p.location}\nالوصف: {p.description}"
                if combined_details:
                    combined_details = ad_info + "\nملاحظات العميل: " + combined_details
                else:
                    combined_details = ad_info
        except Exception:
            pass

    if not name or not phone:
        flash("يرجى إدخال الاسم ورقم الجوال", "error")
        return redirect(url_for("home"))

    order = Order(
        name=name,
        phone=phone,
        seller_phone=seller_phone,
        product_code=product_code,
        service=service,
        delivery_address=delivery_address,
        delivery_needed=delivery_needed,
        details=combined_details,
        status="جديد"
    )
    db.session.add(order)
    db.session.commit()
    flash("تم إرسال طلبك بنجاح، سنتواصل معك قريباً", "success")
    return redirect(url_for("home"))

@app.route("/secure-admin-login-x99", methods=["GET","POST"])
def admin_login():
    if request.method == "POST":
        u = request.form.get("username", "")
        p = request.form.get("password", "")
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
    projects = Project.query.order_by(Project.created_at.desc().nullslast()).all()
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

@app.post("/admin/project/<int:project_id>/promote")
@admin_required
def promote_project(project_id):
    p = Project.query.get_or_404(project_id)
    p.created_at = datetime.utcnow()
    db.session.commit()
    flash("تم ترقية ونشر المنشور لقمة الصفحة الرئيسية بنجاح", "success")
    return redirect(url_for("admin"))

@app.get("/admin/backup")
@admin_required
def export_backup():
    data = {
        "settings": [{"key": s.key, "value": s.value} for s in SiteSetting.query.all()],
        "projects": [{
            "title": p.title, "category": p.category, "condition": getattr(p, "condition", "جديد"), 
            "location": getattr(p, "location", ""), "description": p.description,
            "price": p.price, "phone": p.phone, "featured": p.featured,
            "images": [{"url": img.url, "public_id": img.public_id} for img in p.images]
        } for p in Project.query.all()],
        "pending_ads": [{
            "title": ad.title, "category": ad.category, "condition": getattr(ad, "condition", "جديد"),
            "location": getattr(ad, "location", ""), "description": ad.description,
            "price": ad.price, "phone": ad.phone,
            "images": [{"url": img.url, "public_id": img.public_id} for img in ad.images]
        } for ad in PendingAd.query.all()],
        "orders": [{
            "name": o.name, "phone": o.phone, "seller_phone": o.seller_phone,
            "product_code": o.product_code, "service": o.service,
            "delivery_address": o.delivery_address, "delivery_needed": o.delivery_needed,
            "details": o.details, "status": o.status
        } for o in Order.query.all()]
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
                
        ProjectImage.query.delete()
        Project.query.delete()
        PendingAdImage.query.delete()
        PendingAd.query.delete()
        Order.query.delete()
        db.session.commit()
        
        if "projects" in data:
            for item in data["projects"]:
                p = Project(
                    title=item.get("title", ""),
                    category=item.get("category", ""),
                    condition=item.get("condition", "جديد"),
                    location=item.get("location", ""),
                    description=item.get("description", ""),
                    price=item.get("price", ""),
                    phone=format_whatsapp_phone(item.get("phone", "")),
                    featured=item.get("featured", False),
                    created_at=datetime.utcnow()
                )
                db.session.add(p)
                db.session.flush()
                for img in item.get("images", []):
                    db.session.add(ProjectImage(project_id=p.id, url=img.get("url", ""), public_id=img.get("public_id", "")))
        
        if "pending_ads" in data:
            for item in data["pending_ads"]:
                ad = PendingAd(
                    title=item.get("title", ""),
                    category=item.get("category", ""),
                    condition=item.get("condition", "جديد"),
                    location=item.get("location", ""),
                    description=item.get("description", ""),
                    price=item.get("price", ""),
                    phone=format_whatsapp_phone(item.get("phone", ""))
                )
                db.session.add(ad)
                db.session.flush()
                for img in item.get("images", []):
                    db.session.add(PendingAdImage(pending_ad_id=ad.id, url=img.get("url", ""), public_id=img.public_id))

        if "orders" in data:
            for item in data["orders"]:
                o = Order(
                    name=item.get("name", ""),
                    phone=item.get("phone", ""),
                    seller_phone=item.get("seller_phone", ""),
                    product_code=item.get("product_code", ""),
                    service=item.get("service", ""),
                    delivery_address=item.get("delivery_address", ""),
                    delivery_needed=item.get("delivery_needed", False),
                    details=item.get("details", ""),
                    status=item.get("status", "جديد")
                )
                db.session.add(o)

        db.session.commit()
        flash("تمت استعادة كافة المنتجات، الصور، والطلبات بنجاح تام", "success")
    except Exception as e:
        db.session.rollback()
        flash("حدث خطأ أثناء قراءة واستعادة النسخة الاحتياطية", "error")
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
        location=ad.location,
        description=ad.description,
        price=ad.price,
        phone=format_whatsapp_phone(ad.phone),
        created_at=datetime.utcnow()
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
    sel_cat = request.form.get("category", "").strip()
    custom_cat = request.form.get("custom_category", "").strip()
    category = custom_cat if sel_cat == "أخرى_كتب_بنفسك" and custom_cat else sel_cat
    
    p = Project(
        title=request.form.get("title", "").strip(),
        category=category,
        condition=request.form.get("condition", "جديد").strip(),
        location=request.form.get("location", "").strip(),
        description=request.form.get("description", "").strip(),
        price=request.form.get("price", "").strip(),
        phone=format_whatsapp_phone(request.form.get("phone", "").strip()),
        featured=bool(request.form.get("featured")),
        created_at=datetime.utcnow()
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
    sel_cat = request.form.get("category", "").strip()
    custom_cat = request.form.get("custom_category", "").strip()
    category = custom_cat if sel_cat == "أخرى_كتب_بنفسك" and custom_cat else sel_cat
    
    p.title = request.form.get("title", "").strip()
    p.category = category
    p.condition = request.form.get("condition", "جديد").strip()
    p.location = request.form.get("location", "").strip()
    p.description = request.form.get("description", "").strip()
    p.price = request.form.get("price", "").strip()
    p.phone = format_whatsapp_phone(request.form.get("phone", "").strip())
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
    o.status = request.form.get("status", "جديد")
    db.session.commit()
    return redirect(url_for("admin"))

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")))
