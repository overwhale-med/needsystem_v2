from django.urls import path
from . import views

urlpatterns = [
    path('dashboard/', views.center_dashboard, name='solar_center_dashboard'),

    path('create-quick-job/', views.solar_job_create, name='solar_job_create'),
    path('manage/<int:job_id>/', views.solar_job_manage, name='solar_job_manage'),

    # 🌟 [NEW] เส้นทางใหม่สำหรับหน้าประวัติการเบิกของ
    path('manage/<int:job_id>/bom-history/', views.solar_job_bom_history, name='solar_job_bom_history'),

    path('manage/<int:job_id>/submit-requisition/', views.center_submit_requisition, name='center_submit_requisition'),
    path('manage/<int:job_id>/start/', views.center_start_job, name='center_start_job'),
    path('manage/<int:job_id>/complete/', views.center_complete_job, name='center_complete_job'),

    path('subcontractors/', views.subcontractor_list, name='subcontractor_list'),
    path('subcontractors/create/', views.subcontractor_create, name='subcontractor_create'),
    path('subcontractors/edit/<int:pk>/', views.subcontractor_edit, name='subcontractor_edit'),

    path('expenses/', views.expense_list, name='solar_expense_list'),
    path('expenses/create/', views.expense_create, name='solar_expense_create'),
    path('expenses/approve/<int:expense_id>/', views.expense_approve, name='solar_expense_approve'),
    path('expenses/pay/<int:expense_id>/', views.center_pay_expense, name='center_pay_expense'),

    path('api/update-job-status/', views.update_job_status, name='update_job_status'),
    path('overview/', views.solar_job_overview, name='solar_job_overview'),
    path('master-job-report/', views.solar_master_job_report, name='solar_master_job_report'),
    # ==========================================
    # 🌟 [NEW] ระบบแจ้งซ่อมและบริการโซล่าเซลล์ (After-Sales Service) 🌟
    # ==========================================
    path('service-board/', views.solar_service_board, name='solar_service_board'),
    path('service-tickets/<int:ticket_id>/process/', views.process_solar_service_ticket, name='process_solar_service_ticket'),
    path('service-history/', views.solar_service_history_list, name='solar_service_history_list'),
    path('service-tickets/<int:ticket_id>/claim-labor/', views.submit_solar_service_labor_claim, name='submit_solar_service_labor_claim'),
    # ==========================================
    # 🌟 [NEW] ศูนย์รวมแฟ้มภาพ (Solar Media Hub) 🌟
    # ==========================================
    path('media-hub/', views.solar_media_hub_list, name='solar_media_hub_list'),
    path('media-hub/<int:job_id>/', views.solar_media_hub_detail, name='solar_media_hub_detail'),
    path('media-hub/<int:job_id>/upload/', views.solar_media_hub_upload, name='solar_media_hub_upload'),
]