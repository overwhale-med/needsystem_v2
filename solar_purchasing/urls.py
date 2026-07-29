from django.urls import path
from . import views

urlpatterns = [
    # 🌟 หน้า Dashboard และรายการสั่งซื้อ
    path('dashboard/', views.solar_po_list, name='solar_po_list'),
    
    # 🌟 ระบบจัดการใบสั่งซื้อ (CRUD)
    path('create/', views.solar_po_create, name='solar_po_create'),
    path('edit/<int:po_id>/', views.solar_po_edit, name='solar_po_edit'),
    
    # 🌟 ระบบอนุมัติสำหรับผู้จัดการ
    path('approve/<int:po_id>/', views.solar_po_approve, name='solar_po_approve'),
    path('cancel/<int:po_id>/', views.solar_po_cancel, name='solar_po_cancel'),
]