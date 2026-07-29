from django.urls import path
from . import views

urlpatterns = [
    # --- 🟢 โซนพนักงานหลัก (Core HR) ---
    path('dashboard/', views.employee_dashboard, name='employee_dashboard'),
    path('check-in/', views.check_in, name='check_in'),
    path('check-out/', views.check_out, name='check_out'),
    path('leave/create/', views.leave_create, name='leave_create'),
    path('payslips/', views.payslip_list, name='payslip_list'),
    path('payslip/<int:payslip_id>/', views.payslip_detail, name='payslip_detail'),

    # --- 🟡 โซนหัวหน้างาน (Manager) ---
    path('manager/', views.manager_dashboard, name='manager_dashboard'),
    path('manager/approve/<int:leave_id>/', views.approve_leave, name='approve_leave'),
    path('manager/reject/<int:leave_id>/', views.reject_leave, name='reject_leave'),

    # --- 🔴 โซนฝ่ายบุคคล/ผู้บริหาร (HR/Admin) ---
    path('analytics/', views.hr_executive_dashboard, name='hr_executive_dashboard'),

    # 🌟 [NEW] หน้าจอตรวจสอบเวลาเข้างานและพิกัด GPS 🌟
    path('attendance-tracking/', views.attendance_map, name='attendance_map'),

    path('employee/add/', views.employee_add, name='employee_create'),
    path('employee/edit/<str:emp_id>/', views.employee_edit, name='employee_edit'),
    path('network/tree/', views.network_tree, name='network_tree'),
    path('network/org-chart/', views.org_chart_tree, name='org_chart_tree'), # 🌟 [NEW] แผนผังองค์กร (Tree View)

    # --- API สำหรับปุ่ม Quick Add (+) ---
    path('api/create-position/', views.api_create_position, name='api_create_position'),
    path('api/create-department/', views.api_create_department, name='api_create_department'),

    # 🌟 เส้นทางใหม่: สร้างรหัสพนักงาน และ สร้างกลุ่ม 🌟
    path('api/generate-emp-id/', views.api_generate_emp_id, name='api_generate_emp_id'),
    path('api/create-group/', views.api_create_group, name='api_create_group'),

    # 🌟 เส้นทางสำหรับระบบจัดการสิทธิ์ และ Profile การเข้าถึง 🌟
    path('roles/', views.role_management, name='role_management'),
    path('api/update-role/', views.api_update_user_role, name='api_update_user_role'),
    path('access-profile/<str:emp_id>/', views.employee_access_profile, name='employee_access_profile'),
    path('api/reset-password/', views.api_reset_password, name='api_reset_password'),
    path('api/toggle-user-group/', views.api_toggle_user_group, name='api_toggle_user_group'),
    path('sales-groups/', views.sales_group_settings, name='sales_group_settings'),

    # 🌟 เส้นทางทำเนียบพนักงาน และ API แก้ไขทีมขายไว 🌟
    path('directory/', views.employee_directory, name='employee_directory'),
    path('api/update-sales-role/', views.api_update_sales_role, name='api_update_sales_role'),
    path('api/assign-to-team/', views.api_assign_to_team, name='api_assign_to_team'),
]