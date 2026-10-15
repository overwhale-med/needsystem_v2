from django.urls import path
from . import views

urlpatterns = [
    path('', views.solar_inventory_list, name='solar_inventory_list'), # เส้นทางนี้จะเป็นหน้า Dashboard แทน

    # 🌟 [NEW] เพิ่มเส้นทางแยกสำหรับหน้า FG และ RM
    path('fg/', views.solar_fg_list, name='solar_fg_list'),
    path('rm/', views.solar_rm_list, name='solar_rm_list'),
    path('movement/create/', views.solar_stock_movement_create, name='solar_stock_movement_create'),
    path('create/', views.solar_product_create, name='solar_product_create'),
    path('edit/<int:pk>/', views.solar_product_edit, name='solar_product_edit'),
    path('stock-card/<int:pk>/', views.solar_stock_card, name='solar_stock_card'),
    path('category/add-fg-ajax/', views.add_fg_category_ajax, name='add_fg_category_ajax'),
    path('category/add-rm-ajax/', views.add_rm_category_ajax, name='add_rm_category_ajax'),
    path('download-template/', views.solar_inventory_download_template, name='solar_inventory_download_template'),
    path('import/', views.solar_inventory_import, name='solar_inventory_import'),

    # 🌟 หน้าแสดงรายการรอเบิกของ และ API ตัดสต็อก
    path('requisitions/', views.store_requisition_list, name='store_requisition_list'),
    path('requisitions/<int:job_id>/', views.store_requisition_detail, name='store_requisition_detail'),
    path('requisitions/confirm/<int:job_id>/', views.store_confirm_deduction, name='store_confirm_deduction'),
    path('requisitions/trigger-pr/<int:job_id>/', views.store_trigger_pr, name='store_trigger_pr'),

    # 🌟 [NEW] เส้นทางสำหรับประวัติใบรับของ และพิมพ์เอกสาร A4
    path('documents/in/', views.solar_document_list_in, name='solar_document_list_in'),
    path('print-doc/<str:doc_no>/', views.solar_print_document, name='solar_print_document'),
    # เส้นทางสำหรับประวัติใบเบิกของ (GI)
    path('documents/out/', views.solar_document_list_out, name='solar_document_list_out'),
]