from django.urls import path
from . import views

urlpatterns = [
    path('production/', views.production_list, name='production_list'),
    path('production/create/', views.production_create, name='production_create'),
    path('production/planner/', views.planner_board, name='planner_board'),
    path('production/inventory/', views.inventory_board, name='inventory_board'),
    path('production/blueprint-hub/', views.blueprint_hub, name='blueprint_hub'),
    path('production/blueprint-hub/<int:pk>/workspace/', views.blueprint_workspace, name='blueprint_workspace'),
    path('production/blueprint-hub/<int:pk>/approve/', views.blueprint_approve, name='blueprint_approve'),
    path('production/blueprint-hub/claim/', views.blueprint_create_claim, name='blueprint_create_claim'),
    path('production/blueprint-hub/claim/<int:pk>/print/', views.print_blueprint_claim, name='print_blueprint_claim'),
    path('production/blueprint-claim/<int:claim_id>/pay/', views.pay_blueprint_claim, name='pay_blueprint_claim'),
    path('production/head-board/', views.production_head_board, name='production_head_board'),
    path('production/qc-board/', views.qc_board, name='qc_board'),

    # 🌟 เส้นทางจัดส่งสินค้า 🌟
    path('production/logistics-board/', views.logistics_board, name='logistics_board'),
    path('production/<int:pk>/process-logistics/', views.process_logistics, name='process_logistics'),
    path('production/logistics-claim/', views.create_logistics_claim, name='create_logistics_claim'),
    path('production/<int:pk>/print-delivery/', views.print_delivery_note, name='print_delivery_note'),
    path('production/logistics-claim/<int:pk>/print/', views.print_logistics_claim, name='print_logistics_claim'),
    path('production/logistics-claim/history/', views.logistics_claim_history, name='logistics_claim_history'),

    path('production/<int:pk>/submit-qc/', views.submit_to_qc, name='submit_to_qc'),
    path('production/<int:pk>/process-qc/', views.process_qc, name='process_qc'),
    path('production/<int:po_id>/print/', views.production_print, name='production_print'),
    path('production/<int:pk>/detail/', views.production_detail, name='production_detail'),
    path('production/<int:pk>/generate-pos/', views.generate_pos_from_production, name='generate_pos_from_production'),
    path('prepare-purchase/', views.ppo_prepare, name='ppo_prepare'),
    path('production/<int:pk>/upload-blueprint/', views.upload_blueprint, name='upload_blueprint'),
    path('production/<int:pk>/load-bom/', views.load_standard_bom, name='load_standard_bom'),
    path('production/<int:pk>/print-bom/', views.print_bom, name='print_bom'),
    path('production/<int:pk>/start/', views.start_production, name='start_production'),
    path('production/<int:pk>/materials-ready/', views.materials_ready, name='materials_ready'),
    path('production/<int:pk>/start-actual/', views.start_actual_production, name='start_actual_production'),
    path('production/<int:pk>/process/', views.production_process, name='production_process'),
    path('production/<int:pk>/add-material/', views.add_additional_material, name='add_additional_material'),
    path('production/material/<int:pk>/delete/', views.delete_production_material, name='delete_production_material'),
    path('production/<int:pk>/blueprint-viewer/', views.blueprint_viewer, name='blueprint_viewer'),
    
    # 🧱 สูตรการผลิต (BOM)
    path('bom/', views.bom_list, name='bom_list'),
    path('bom/create/', views.bom_create, name='bom_create'),
    path('bom/<int:pk>/', views.bom_detail, name='bom_detail'),
    path('bom/<int:pk>/edit/', views.bom_edit, name='bom_edit'),
    path('bom/<int:pk>/update-labor-cost/', views.update_bom_labor_cost, name='update_bom_labor_cost'), # 🌟 [NEW] เพิ่มเส้นทางอัปเดตค่าแรงประกอบ
    path('bom/<int:pk>/print/', views.print_master_bom, name='print_master_bom'),
    
    path('production/<int:pk>/update-board/', views.update_production_board, name='update_production_board'),
    path('ajax/add-branch/', views.ajax_add_branch, name='ajax_add_branch'),
    path('ajax/add-salesperson/', views.ajax_add_salesperson, name='ajax_add_salesperson'),
    path('ajax/add-prod-status/', views.ajax_add_prod_status, name='ajax_add_prod_status'),
    path('ajax/add-prod-team/', views.ajax_add_prod_team, name='ajax_add_prod_team'),
    path('ajax/add-delivery-status/', views.ajax_add_delivery_status, name='ajax_add_delivery_status'),
    path('ajax/add-transporter/', views.ajax_add_transporter, name='ajax_add_transporter'),
    path('ajax/add-transporter-full/', views.ajax_add_transporter_full, name='ajax_add_transporter_full'),
    path('ajax/get-fg-by-category/', views.ajax_get_fg_by_category, name='ajax_get_fg_by_category'),
    path('bom/import/', views.import_bom_excel, name='import_bom_excel'),
    path('ajax/search-raw-material/', views.ajax_search_raw_material, name='ajax_search_raw_material'),
    path('production/logistics-claim/<int:claim_id>/pay/', views.pay_logistics_claim, name='pay_logistics_claim'),
]