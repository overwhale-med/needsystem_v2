from django.urls import path
from . import views

urlpatterns = [
    path('dashboard/', views.center_dashboard, name='solar_center_dashboard'),

    path('create-quick-job/', views.solar_job_create, name='solar_job_create'),
    path('manage/<int:job_id>/', views.solar_job_manage, name='solar_job_manage'),

    path('subcontractors/', views.subcontractor_list, name='subcontractor_list'),
    path('subcontractors/create/', views.subcontractor_create, name='subcontractor_create'),
    path('subcontractors/edit/<int:pk>/', views.subcontractor_edit, name='subcontractor_edit'),

    path('expenses/', views.expense_list, name='solar_expense_list'),
    path('expenses/create/', views.expense_create, name='solar_expense_create'),
    path('expenses/approve/<int:expense_id>/', views.expense_approve, name='solar_expense_approve'),
    # 🌟 [NEW] เพิ่มเส้นทางจ่ายเงินและแนบสลิปสำหรับแผนก Center 🌟
    path('expenses/pay/<int:expense_id>/', views.center_pay_expense, name='center_pay_expense'),

    # 🌟 [NEW] เพิ่มเส้นทาง API สำหรับลากการ์ด 🌟
    path('api/update-job-status/', views.update_job_status, name='update_job_status'),
    path('overview/', views.solar_job_overview, name='solar_job_overview'),
]