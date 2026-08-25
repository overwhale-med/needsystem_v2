from django.urls import path
from . import views

urlpatterns = [
    path('dashboard/', views.solar_sales_dashboard, name='solar_sales_dashboard'),
    path('quotations/', views.solar_quotation_list, name='solar_quotation_list'),
    path('quotations/create/', views.solar_quotation_create, name='solar_quotation_create'),
    path('quotations/<int:qt_id>/', views.solar_quotation_edit, name='solar_quotation_edit'),

    path('quotations/item/<int:item_id>/delete/', views.solar_delete_item, name='solar_delete_item'),

    path('quotations/<int:qt_id>/approve/', views.solar_quotation_approve, name='solar_quotation_approve'),
    path('quotations/<int:qt_id>/send-to-center/', views.solar_quotation_send_to_center, name='solar_quotation_send_to_center'),
    path('quotations/<int:qt_id>/print/', views.solar_quotation_print, name='solar_quotation_print'),

    path('quotations/<int:qt_id>/print-contract/', views.solar_quotation_print_contract, name='solar_quotation_print_contract'),
    path('quotations/<int:qt_id>/copy/', views.solar_quotation_copy, name='solar_quotation_copy'),
    path('quotations/<int:qt_id>/cancel/', views.solar_quotation_cancel, name='solar_quotation_cancel'),

    path('quotations/<int:qt_id>/record-deposit/', views.solar_record_deposit, name='solar_record_deposit'),
    path('quotations/<int:qt_id>/verify-deposit/', views.solar_verify_deposit, name='solar_verify_deposit'),

    # 🌟 [NEW] เพิ่มเส้นทางปุ่ม "เปิดบิลขาย" 🌟
    path('quotations/<int:qt_id>/create-invoice/', views.solar_quotation_create_invoice, name='solar_quotation_create_invoice'),

    path('deposits/', views.solar_deposit_list, name='solar_deposit_list'),

    path('invoices/', views.solar_invoice_list, name='solar_invoice_list'),
    path('invoices/<int:inv_id>/', views.solar_invoice_detail, name='solar_invoice_detail'),
    path('invoices/<int:inv_id>/print/', views.solar_invoice_print, name='solar_invoice_print'),
    path('invoices/<int:inv_id>/record-payment/', views.solar_invoice_detail, name='solar_invoice_record_payment'),

    path('inventory/', views.solar_inventory_list, name='solar_inventory_list'),
    path('inventory/create/', views.solar_product_create, name='solar_product_create'),
    path('inventory/edit/<int:pk>/', views.solar_product_edit, name='solar_product_edit'),
    path('inventory/category/add-fg-ajax/', views.add_fg_category_ajax, name='add_fg_category_ajax'),
    path('inventory/category/add-rm-ajax/', views.add_rm_category_ajax, name='add_rm_category_ajax'),
    path('inventory/download-template/', views.solar_inventory_download_template, name='solar_inventory_download_template'),
    path('inventory/import/', views.solar_inventory_import, name='solar_inventory_import'),
    # เพิ่ม URL นี้สำหรับการเซ็นใบเสนอราคาออนไลน์ของฝั่งโซล่าเซลล์
    path('solar-sales/sign-quotation/<str:token>/', views.solar_customer_sign_quotation, name='solar_customer_sign_quotation'),
    # ในไฟล์ urls.py เพิ่มลิงก์นี้
    path('deposits/<int:qt_id>/print/', views.solar_deposit_print, name='solar_deposit_print'),
    # ==========================================
    # 🌟 ระบบสำรวจหน้างานและเบิกจ่ายโซล่าเซลล์
    # ==========================================
    path('surveys/', views.solar_survey_list, name='solar_survey_list'),
    path('surveys/create/', views.solar_survey_create, name='solar_survey_create'),
    path('surveys/<int:job_id>/', views.solar_survey_detail, name='solar_survey_detail'),

    path('expenses/', views.solar_expense_list, name='solar_expense_list'),
    # ช่างสามารถกดเบิกเงินโดยอ้างอิงจากใบงานได้
    path('expenses/create/<int:job_id>/', views.solar_expense_create, name='solar_expense_create'),
    # หัวหน้า/แอดมิน กดอนุมัติ
    path('expenses/<int:exp_id>/approve/', views.solar_expense_approve, name='solar_expense_approve'),
    path('expenses/<int:exp_id>/print/', views.solar_expense_print, name='solar_expense_print'),
]