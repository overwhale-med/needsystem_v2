from django.urls import path
from . import views

urlpatterns = [
    path('', views.inventory_dashboard, name='inventory_dashboard'),
    path('products/', views.product_list, name='product_list'),

    path('documents/in/', views.document_list_in, name='document_list_in'),
    path('documents/out/', views.document_list_out, name='document_list_out'),

    path('stock/in/', views.stock_in, name='stock_in'),
    path('stock/out/', views.stock_out, name='stock_out'),

    path('product/new/', views.product_create, name='product_create'),
    path('product/edit/<int:pk>/', views.product_update, name='product_update'),
    path('product/delete/<int:pk>/', views.product_delete, name='product_delete'),
    path('product/<int:pk>/stock-card/', views.product_stock_card, name='product_stock_card'),
    path('print-barcode/<int:product_id>/', views.print_barcode, name='print_barcode'),
    path('print-doc/<str:doc_no>/', views.print_document, name='print_document'),

    path('ajax/add-category/', views.ajax_add_category, name='ajax_add_category'),
    path('ajax/add-supplier/', views.ajax_add_supplier, name='ajax_add_supplier'),
    path('ajax/add-sub-category/', views.ajax_add_sub_category, name='ajax_add_sub_category'),

    # 🌟 เส้นทางสำหรับเพิ่มหมวดหมู่วัตถุดิบ (แผนก) ผ่านหน้าจอ Modal 🌟
    path('ajax/add-rm-category/', views.ajax_add_rm_category, name='ajax_add_rm_category'),

    # 🌟 เส้นทางใหม่: สำหรับรับสินค้าจาก PO (GR) 🌟
    path('receive-po/', views.po_receive_list, name='po_receive_list'),
    path('receive-po/<int:po_id>/', views.po_receive_process, name='po_receive_process'),

    # 🌟 [NEW] เส้นทางใหม่: สำหรับรับสินค้าจาก PQ ต่างประเทศ (GR-PQ) 🌟
    path('receive-pq/', views.pq_receive_list, name='pq_receive_list'),
    path('receive-pq/<int:pq_id>/', views.pq_receive_process, name='pq_receive_process'),
    path('import-images/', views.import_product_images, name='import_product_images'),
    path('import-rm/', views.import_rm_excel, name='import_rm_excel'),
    path('tools/', views.inventory_tools, name='inventory_tools'),
]