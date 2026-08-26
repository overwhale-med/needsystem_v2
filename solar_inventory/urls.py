from django.urls import path
from . import views

urlpatterns = [
    path('', views.solar_inventory_list, name='solar_inventory_list'),
    path('create/', views.solar_product_create, name='solar_product_create'),
    path('edit/<int:pk>/', views.solar_product_edit, name='solar_product_edit'),
    path('stock-card/<int:pk>/', views.solar_stock_card, name='solar_stock_card'),
    path('category/add-fg-ajax/', views.add_fg_category_ajax, name='add_fg_category_ajax'),
    path('category/add-rm-ajax/', views.add_rm_category_ajax, name='add_rm_category_ajax'),
    path('download-template/', views.solar_inventory_download_template, name='solar_inventory_download_template'),
    path('import/', views.solar_inventory_import, name='solar_inventory_import'),
]