from django.urls import path
from . import views

urlpatterns = [
    # จัดการลูกค้า
    path('customers/', views.customer_list, name='customer_list'),
    path('customers/create/', views.customer_create, name='customer_create'),
    path('customers/edit/<int:pk>/', views.customer_edit, name='customer_edit'),
    path('customers/delete/<int:pk>/', views.customer_delete, name='customer_delete'),

    # ✅ จัดการร้านค้า (Supplier)
    path('suppliers/', views.supplier_list, name='supplier_list'),
    path('suppliers/create/', views.supplier_create, name='supplier_create'),
    path('suppliers/edit/<int:pk>/', views.supplier_edit, name='supplier_edit'),
    path('suppliers/delete/<int:pk>/', views.supplier_delete, name='supplier_delete'),

    # API สำหรับที่อยู่ (Dropdown)
    path('api/provinces/', views.get_provinces, name='get_provinces'),
    path('api/amphures/', views.get_amphures, name='get_amphures'),
    path('api/tambons/', views.get_tambons, name='get_tambons'),
    path('company/settings/', views.company_settings, name='company_settings'),
]