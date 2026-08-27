from django.urls import path
from . import views

urlpatterns = [
    path('', views.solar_inventory_list, name='solar_inventory_list'),
    path('movement/create/', views.solar_stock_movement_create, name='solar_stock_movement_create'),
    path('create/', views.solar_product_create, name='solar_product_create'),
    path('edit/<int:pk>/', views.solar_product_edit, name='solar_product_edit'),
    path('stock-card/<int:pk>/', views.solar_stock_card, name='solar_stock_card'),
    path('category/add-fg-ajax/', views.add_fg_category_ajax, name='add_fg_category_ajax'),
    path('category/add-rm-ajax/', views.add_rm_category_ajax, name='add_rm_category_ajax'),
    path('download-template/', views.solar_inventory_download_template, name='solar_inventory_download_template'),
    path('import/', views.solar_inventory_import, name='solar_inventory_import'),

    # 🌟 [NEW] หน้าแสดงรายการรอเบิกของ และ API ตัดสต็อก
    path('requisitions/', views.store_requisition_list, name='store_requisition_list'),
    path('requisitions/<int:job_id>/', views.store_requisition_detail, name='store_requisition_detail'), # <-- เพิ่มบรรทัดนี้
    path('requisitions/confirm/<int:job_id>/', views.store_confirm_deduction, name='store_confirm_deduction'),
]