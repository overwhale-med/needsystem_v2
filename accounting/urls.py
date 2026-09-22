from django.urls import path
from . import views

urlpatterns = [
    # หน้าหลัก Dashboard บัญชี
    path('dashboard/', views.accounting_dashboard, name='accounting_dashboard'),

    # 🌟 [NEW] กระดานกระทบยอดบัญชี (Reconciliation Board)
    path('commission-recon/', views.commission_recon_board, name='accounting_commission_recon'),

    # เส้นทางสำหรับศูนย์ตรวจสอบของฝ่ายบัญชี
    path('verify/<str:task_type>/', views.verification_hub, name='accounting_verification_hub'),
    path('approve/<str:task_type>/<int:item_id>/', views.approve_transaction, name='accounting_approve_transaction'),
    path('accounting/job-expense-hub/', views.accounting_job_expense_hub, name='accounting_job_expense_hub'),
    path('accounting/job-expense-detail/<int:claim_id>/', views.accounting_job_expense_detail, name='accounting_job_expense_detail'), # 🌟 บรรทัดที่เพิ่มใหม่
    path('accounting/job-expense-pay/<int:claim_id>/', views.pay_job_expense_claim, name='pay_job_expense_claim'),
]