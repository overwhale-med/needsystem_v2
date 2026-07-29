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
    
    # 🌟 [FIXED] เพิ่มเส้นทาง URL สำหรับเมนูใหม่ (สัญญา, คัดลอก, ยกเลิก) 🌟
    path('quotations/<int:qt_id>/print-contract/', views.solar_quotation_print_contract, name='solar_quotation_print_contract'),
    path('quotations/<int:qt_id>/copy/', views.solar_quotation_copy, name='solar_quotation_copy'),
    path('quotations/<int:qt_id>/cancel/', views.solar_quotation_cancel, name='solar_quotation_cancel'),

    path('quotations/<int:qt_id>/record-deposit/', views.solar_record_deposit, name='solar_record_deposit'),
    path('quotations/<int:qt_id>/verify-deposit/', views.solar_verify_deposit, name='solar_verify_deposit'),
    
    path('invoices/', views.solar_invoice_list, name='solar_invoice_list'),
    path('invoices/<int:inv_id>/', views.solar_invoice_detail, name='solar_invoice_detail'),
    path('invoices/<int:inv_id>/print/', views.solar_invoice_print, name='solar_invoice_print'),
    
    path('inventory/', views.solar_inventory_list, name='solar_inventory_list'),
    path('inventory/create/', views.solar_product_create, name='solar_product_create'),
    path('inventory/edit/<int:pk>/', views.solar_product_edit, name='solar_product_edit'),
    path('inventory/download-template/', views.solar_inventory_download_template, name='solar_inventory_download_template'),
    path('inventory/import/', views.solar_inventory_import, name='solar_inventory_import'),
]