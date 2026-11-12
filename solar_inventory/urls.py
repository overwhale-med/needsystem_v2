from django.urls import path
from . import views

urlpatterns = [
    path('', views.solar_inventory_list, name='solar_inventory_list'), # เส้นทางนี้จะเป็นหน้า Dashboard แทน

    # 🌟 [NEW] เพิ่มเส้นทางแยกสำหรับหน้า FG และ RM
    path('fg/', views.solar_fg_list, name='solar_fg_list'),
    path('rm/', views.solar_rm_list, name='solar_rm_list'),

    # 🌟 [UPDATE] แยกเส้นทางสำหรับบันทึกรับเข้า (GR) และ เบิกออก (GI) แบบ Manual ให้ขาดจากกัน
    path('stock-in/create/', views.solar_stock_in_create, name='solar_stock_in_create'),
    path('stock-out/create/', views.solar_stock_out_create, name='solar_stock_out_create'),

    path('create/', views.solar_product_create, name='solar_product_create'),
    path('edit/<int:pk>/', views.solar_product_edit, name='solar_product_edit'),
    path('stock-card/<int:pk>/', views.solar_stock_card, name='solar_stock_card'),
    path('category/add-fg-ajax/', views.add_fg_category_ajax, name='add_fg_category_ajax'),
    path('category/add-rm-ajax/', views.add_rm_category_ajax, name='add_rm_category_ajax'),
    path('download-template/', views.solar_inventory_download_template, name='solar_inventory_download_template'),
    path('import/', views.solar_inventory_import, name='solar_inventory_import'),

    # 🌟 หน้าแสดงรายการรอเบิกของ และ API ตัดสต็อก
    path('requisitions/', views.store_requisition_list, name='store_requisition_list'),

    # 🌟 [NEW] เส้นทางสำหรับหน้าประวัติและพิมพ์ใบจัดของ
    path('requisitions/history/', views.store_requisition_history, name='store_requisition_history'),
    path('requisitions/print-picking-list/<int:job_id>/', views.store_print_picking_list, name='store_print_picking_list'),

    path('requisitions/<int:job_id>/', views.store_requisition_detail, name='store_requisition_detail'),
    path('requisitions/confirm/<int:job_id>/', views.store_confirm_deduction, name='store_confirm_deduction'),
    path('requisitions/trigger-pr/<int:job_id>/', views.store_trigger_pr, name='store_trigger_pr'),

    # 🌟 [NEW] เส้นทางสำหรับประวัติใบรับของ และพิมพ์เอกสาร A4
    path('documents/in/', views.solar_document_list_in, name='solar_document_list_in'),
    path('print-doc/<str:doc_no>/', views.solar_print_document, name='solar_print_document'),
    # เส้นทางสำหรับประวัติใบเบิกของ (GI)
    path('documents/out/', views.solar_document_list_out, name='solar_document_list_out'),

    # 🌟 [NEW] เส้นทางสำหรับพิมพ์ใบ GI ย้อนหลัง
    path('documents/print-gi/<str:doc_no>/', views.store_print_gi_doc, name='store_print_gi_doc'),

    path('pending-pos/', views.store_pending_po_list, name='store_pending_po_list'),
    # 🌟 [NEW] เส้นทางสำหรับพิมพ์ใบตรวจนับสต็อก (A4)
    path('print-stock-count/', views.solar_print_stock_count, name='solar_print_stock_count'),
]