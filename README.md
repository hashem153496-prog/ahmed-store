# Ahmed Cloud Store

نسخة مهيأة لتعمل أونلاين من الموبايل والكمبيوتر.

## ماذا تدعم؟
- لوحة تحكم Responsive للموبايل والكمبيوتر
- إضافة/تعديل/حذف الأعمال
- رفع أكثر من صورة لكل عمل
- كتابة السعر والوصف والقسم
- إدارة طلبات العملاء
- PostgreSQL للبيانات عند النشر
- Cloudinary للصور عند النشر
- لا تعتمد على ملفات اللابتوب بعد رفعها

## النشر المقترح
Render + PostgreSQL + Cloudinary

### Environment Variables
SECRET_KEY
ADMIN_USERNAME
ADMIN_PASSWORD
DATABASE_URL
CLOUDINARY_CLOUD_NAME
CLOUDINARY_API_KEY
CLOUDINARY_API_SECRET

### تشغيل محلي اختياري
pip install -r requirements.txt
python app.py

لو لم تضف Cloudinary سيستخدم مجلد static/uploads محلياً للاختبار فقط.
