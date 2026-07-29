from django.urls import path
from . import views

urlpatterns = [
    path('dashboard/', views.purchasing_dashboard, name='purchasing_dashboard'),
    path('po/list/', views.po_list, name='po_list'),
    path('po/create/', views.po_create, name='po_create'),
    path('po/edit/<int:po_id>/', views.po_edit, name='po_edit'),
    path('po/approve/<int:po_id>/', views.po_approve, name='po_approve'),
    path('po/cancel/<int:po_id>/', views.po_cancel, name='po_cancel'),
    path('po/print/<int:po_id>/', views.po_print, name='po_print'),
    path('po/payment/<int:po_id>/', views.po_payment, name='po_payment'),
    path('ppo/list/', views.ppo_list, name='ppo_list'),
    path('ppo/<int:pk>/', views.ppo_detail, name='ppo_detail'),
    
    path('suppliers/', views.supplier_list, name='supplier_list'),
    path('suppliers/<int:pk>/', views.supplier_detail, name='supplier_detail'),

    # 🌟 ระบบจัดซื้อต่างประเทศ (Overseas PO) 🌟
    path('overseas/', views.overseas_po_list, name='overseas_po_list'),
    path('overseas/save/', views.overseas_po_save, name='overseas_po_save'),
    path('overseas/delete/<int:pk>/', views.overseas_po_delete, name='overseas_po_delete'),
    path('overseas/<int:po_id>/request-payment/<str:payment_type>/', views.request_overseas_payment, name='request_overseas_payment'),
    path('overseas/print/<int:po_id>/', views.overseas_po_print, name='overseas_po_print'),

    # 🌟 [NEW] ระบบทำเนียบร้านค้าต่างประเทศ 🌟
    path('overseas-suppliers/', views.overseas_supplier_list, name='overseas_supplier_list'),
    path('overseas-suppliers/save/', views.overseas_supplier_save, name='overseas_supplier_save'),
    path('overseas-suppliers/delete/<int:pk>/', views.overseas_supplier_delete, name='overseas_supplier_delete'),
]