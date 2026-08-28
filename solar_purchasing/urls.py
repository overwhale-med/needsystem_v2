from django.urls import path
from . import views

urlpatterns = [
    # 🌟 หน้า Dashboard และรายการสั่งซื้อ
    path('dashboard/', views.solar_po_list, name='solar_po_list'),

    # 🌟 ระบบจัดการใบสั่งซื้อ (CRUD)
    path('create/', views.solar_po_create, name='solar_po_create'),
    path('edit/<int:po_id>/', views.solar_po_edit, name='solar_po_edit'),
    path('print/<int:po_id>/', views.solar_po_print, name='solar_po_print'),

    # 🌟 ระบบอนุมัติสำหรับผู้จัดการ
    path('approve/<int:po_id>/', views.solar_po_approve, name='solar_po_approve'),
    path('cancel/<int:po_id>/', views.solar_po_cancel, name='solar_po_cancel'),

    # 🌟 [NEW] ระบบใบเตรียมสั่งซื้อโซล่าเซลล์ (Solar PPO) ที่ย้ายมาใหม่
    path('ppo/list/', views.solar_ppo_list, name='solar_ppo_list'),
    path('ppo/<int:pk>/', views.solar_ppo_detail, name='solar_ppo_detail'),
]