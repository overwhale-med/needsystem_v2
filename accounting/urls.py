from django.urls import path
from . import views

urlpatterns = [
    # หน้าหลัก Dashboard บัญชี
    path('dashboard/', views.accounting_dashboard, name='accounting_dashboard'),
    
    # 🌟 [NEW] เส้นทางสำหรับศูนย์ตรวจสอบของฝ่ายบัญชี 🌟
    path('verify/<str:task_type>/', views.verification_hub, name='accounting_verification_hub'),
    path('approve/<str:task_type>/<int:item_id>/', views.approve_transaction, name='accounting_approve_transaction'),
]