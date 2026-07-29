from django.urls import path
from . import views

urlpatterns = [
    path('', views.sales_dashboard, name='sales_dashboard'),
    path('hub/', views.sales_hub, name='sales_hub'),
    path('convert-quote/<int:qt_id>/', views.convert_quote_to_invoice, name='convert_quote_to_invoice'),

    path('pos/', views.pos_home, name='pos_home'),
    path('pos/checkout/', views.pos_checkout, name='pos_checkout'),
    path('pos/print/<str:order_code>/', views.pos_print_slip, name='pos_print_slip'),

    path('quotation/', views.quotation_list, name='quotation_list'),
    path('quotation/create/', views.quotation_create, name='quotation_create'),
    path('quotation/edit/<int:qt_id>/', views.quotation_edit, name='quotation_edit'),
    path('quotation/delete-item/<int:item_id>/', views.delete_item, name='delete_item'),
    path('quotation/print/<int:qt_id>/', views.quotation_print, name='quotation_print'),
    path('quotation/approve/<int:qt_id>/', views.quotation_approve, name='quotation_approve'),
    path('quotation/cancel/<int:qt_id>/', views.quotation_cancel, name='quotation_cancel'),
    path('quotation/clone/<int:qt_id>/', views.quotation_clone, name='quotation_clone'),
    path('quotation/create-job/<int:qt_id>/', views.create_job_order, name='create_job_order'),

    path('deposit/', views.deposit_list, name='deposit_list'),
    path('deposit/record/<int:qt_id>/', views.record_deposit, name='record_deposit'),
    path('deposit/verify/<int:qt_id>/', views.verify_deposit, name='verify_deposit'),
    path('deposit/print/<int:qt_id>/', views.deposit_print, name='deposit_print'),

    path('invoice/', views.invoice_list, name='invoice_list'),
    path('invoice/print/<int:inv_id>/', views.invoice_print, name='invoice_print'),
    path('invoice/record-payment/<int:inv_id>/', views.record_invoice_payment, name='record_invoice_payment'),
    path('invoice/delete-payment/<int:pay_id>/', views.delete_invoice_payment, name='delete_invoice_payment'),
    path('confirm-payment/<str:doc_type>/<int:doc_id>/', views.confirm_payment, name='confirm_payment'),

    path('api/customer-search/', views.api_search_customer, name='api_search_customer'),
    path('api/customer-create/', views.api_create_customer, name='api_create_customer'),
    path('export/excel/', views.export_sales_excel, name='export_sales_excel'),
    path('api/dashboard-data/', views.api_dashboard_data, name='api_dashboard_data'),
    path('timeline/', views.sales_timeline, name='sales_timeline'),

    # 🌟 ระบบ CRM ติดตามลูกค้ามุ่งหวัง 🌟
    path('crm/', views.crm_board, name='crm_board'),
    path('crm/create/', views.crm_lead_create, name='crm_lead_create'),
    path('crm/update/<int:lead_id>/', views.crm_lead_update, name='crm_lead_update'),

    # 🌟 ระบบจัดการนัดหมาย (Appointments) 🌟
    path('crm/appointments/', views.appointment_board, name='appointment_board_global'),
    path('crm/appointments/create-modal/', views.appointment_create_modal, name='appointment_create_modal'),
    path('crm/appointments/update/<int:apt_id>/', views.appointment_update, name='appointment_update'),
    path('quotation/<int:qt_id>/print-deposit/', views.print_deposit_contract, name='print_deposit_contract'),
]