from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),

    # --- เชื่อมต่อแอปต่างๆ เข้ากับระบบหลัก ---
    path('', include('core.urls')),                # หน้าแรก (Dashboard)
    path('hr/', include('hr.urls')),               # ระบบ HR
    path('sales/', include('sales.urls')),         # ระบบขาย

    # ✅ ระบบคลังสินค้า (Inventory) เชื่อมต่อเรียบร้อยแล้ว
    path('inventory/', include('inventory.urls')),

    # ✅ ระบบข้อมูลลูกค้า (Master Data)
    path('master_data/', include('master_data.urls')),

    # 🌟 เพิ่มใหม่: เชื่อมต่อระบบจัดซื้อ (Purchasing) 🌟
    path('purchasing/', include('purchasing.urls')),

    # 🌟 เพิ่มใหม่: เชื่อมต่อระบบฝ่ายผลิต (Manufacturing) 🌟
    path('manufacturing/', include('manufacturing.urls')),

    path('accounting/', include('accounting.urls')),
    path('solar-purchasing/', include('solar_purchasing.urls')),
    path('solar-jobs/', include('solar_jobs.urls')),
    path('solar-sales/', include('solar_sales.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)