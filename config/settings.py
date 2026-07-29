"""
Django settings for NEED_system project.
"""

from pathlib import Path
import os

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'django-insecure-change-me-to-something-secure-later'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = ['*']

CSRF_TRUSTED_ORIGINS = [
    'https://needsystem.needshopping.co.th',
    'https://*.needshopping.co.th',
    'http://localhost:8009',
    'http://127.0.0.1:8009',
]

SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# Application definition

INSTALLED_APPS = [
    # --- Django Apps ---
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'mathfilters',
    'solar_purchasing',
    'solar_jobs',
    'solar_sales',

    # --- 3rd Party Tools ---
    'import_export',           # สำหรับนำเข้า/ส่งออก Excel
    'django.contrib.humanize', # สำหรับจัดรูปแบบตัวเลข (ใส่ลูกน้ำ)

    # ✅ เพิ่ม Crispy Forms (ตัวตกแต่งฟอร์ม) ที่ขาดหายไป
    'crispy_forms',
    'crispy_bootstrap5',

    # --- 🏢 อาณาจักรของเรา (Custom Apps) ---
    'master_data',    # 1. ฐานข้อมูลกลาง (บริษัท, ลูกค้า, ซัพพลายเออร์)
    'core',           # 2. Dashboard CEO
    'hr',             # 3. ฝ่ายบุคคล
    'sales',          # 4. ฝ่ายขาย (POS + ใบเสนอราคา)
    'inventory',      # 5. คลังสินค้า
    'manufacturing',  # 6. ฝ่ายผลิต
    'accounting',     # 7. ฝ่ายบัญชี
    'purchasing',     # 8. ฝ่ายจัดซื้อ
    'marketing',      # 9. ฝ่ายการตลาด
    'operations',     # 10. ฝ่ายปฏิบัติการ
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'core.context_processors.company_context',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# Database
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    { 'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator', },
    { 'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', },
    { 'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator', },
    { 'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator', },
]

# ==========================================
# Internationalization (ตั้งค่าภาษาและวันที่)
# ==========================================
LANGUAGE_CODE = 'th'       # 👈 เปลี่ยนเป็นภาษาไทย
TIME_ZONE = 'Asia/Bangkok' # 👈 เวลาไทย
USE_I18N = True

# ⚠️ สำคัญ: ต้องปิด L10N เพื่อให้ระบบยอมใช้ Format ที่เรากำหนดเองด้านล่าง
USE_L10N = False
USE_TZ = True

# ✅ กำหนดรูปแบบวันที่แสดงผลเป็น: 31/01/2026 (dd/mm/yyyy)
DATE_FORMAT = 'd/m/Y'
DATETIME_FORMAT = 'd/m/Y H:i'
TIME_FORMAT = 'H:i'

# ✅ กำหนดให้ช่องกรอกข้อมูลยอมรับรูปแบบนี้ (แก้ปัญหา Enter a valid date)
DATE_INPUT_FORMATS = [
    '%d/%m/%Y',  # รูปแบบหลัก: 31/10/1975
    '%Y-%m-%d',  # รูปแบบสำรอง (กันเหนียว)
]

DATETIME_INPUT_FORMATS = [
    '%d/%m/%Y %H:%M',
    '%d/%m/%Y %H:%M:%S',
    '%Y-%m-%d %H:%M:%S',
]

# Static files (CSS, JavaScript, Images)
STATIC_URL = 'static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# Media files (User uploaded images)
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Login Redirect
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/login/'
LOGIN_URL = 'login'

# ==========================================
# ✅ เพิ่มการตั้งค่า Crispy Forms (Bootstrap 5)
# ==========================================
CRISPY_ALLOWED_TEMPLATE_PACKS = "bootstrap5"
CRISPY_TEMPLATE_PACK = "bootstrap5"