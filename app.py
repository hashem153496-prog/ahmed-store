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
        
        # استعادة إعدادات الموقع
        if "settings" in data:
            for s in data["settings"]:
                set_setting(s["key"], s["value"])
                
        # تفريغ البيانات الحالية واستبدالها بالكامل لضمان مطابقة النسخة وعدم التكرار
        ProjectImage.query.delete()
        Project.query.delete()
        PendingAdImage.query.delete()
        PendingAd.query.delete()
        Order.query.delete()
        db.session.commit()
        
        # استعادة المشاريع والمنشورات مع صورها بكامل تفاصيلها
        if "projects" in data:
            for item in data["projects"]:
                p = Project(
                    title=item.get("title",""),
                    category=item.get("category",""),
                    condition=item.get("condition","جديد"),
                    location=item.get("location",""),
                    description=item.get("description",""),
                    price=item.get("price",""),
                    phone=format_whatsapp_phone(item.get("phone","")),
                    featured=item.get("featured", False)
                )
                db.session.add(p)
                db.session.flush()
                for img in item.get("images", []):
                    db.session.add(ProjectImage(project_id=p.id, url=img.get("url",""), public_id=img.get("public_id","")))
        
        # استعادة الإعلانات المعلقة إن وجدت
        if "pending_ads" in data:
            for item in data["pending_ads"]:
                ad = PendingAd(
                    title=item.get("title",""),
                    category=item.get("category",""),
                    condition=item.get("condition","جديد"),
                    location=item.get("location",""),
                    description=item.get("description",""),
                    price=item.get("price",""),
                    phone=format_whatsapp_phone(item.get("phone",""))
                )
                db.session.add(ad)
                db.session.flush()
                for img in item.get("images", []):
                    db.session.add(PendingAdImage(pending_ad_id=ad.id, url=img.get("url",""), public_id=img.get("public_id","")))

        # استعادة طلبات العملاء إن وجدت
        if "orders" in data:
            for item in data["orders"]:
                o = Order(
                    name=item.get("name",""),
                    phone=item.get("phone",""),
                    seller_phone=item.get("seller_phone",""),
                    product_code=item.get("product_code",""),
                    service=item.get("service",""),
                    delivery_address=item.get("delivery_address",""),
                    delivery_needed=item.get("delivery_needed", False),
                    details=item.get("details",""),
                    status=item.get("status","جديد")
                )
                db.session.add(o)

        db.session.commit()
        flash("تمت استعادة كافة المنتجات، الصور، والطلبات بنجاح تام", "success")
    except Exception as e:
        db.session.rollback()
        flash("حدث خطأ أثناء قراءة واستعادة النسخة الاحتياطية", "error")
    return redirect(url_for("admin"))
