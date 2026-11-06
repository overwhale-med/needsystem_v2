from django.urls import path
from .views import dashboards, production, inventory, logistics, services, bom

urlpatterns = [
    # ==========================
    # 📊 หมวดกระดาน (Dashboards)
    # ==========================
    path('control/dashboard/', dashboards.control_dashboard, name='control_dashboard'),
    path('production/planner/', dashboards.planner_board, name='planner_board'),
    path('production/head-board/', dashboards.production_head_board, name='production_head_board'),
    path('production/qc-board/', dashboards.qc_board, name='qc_board'),
    path('production/logistics-board/', dashboards.logistics_board, name='logistics_board'),
    path('production/service-board/', dashboards.service_board, name='service_board'),

    # ==========================
    # 🏭 หมวดฝ่ายผลิตและแบบแปลน (Production)
    # ==========================
    path('production/', production.production_list, name='production_list'),
    path('production/create/', production.production_create, name='production_create'),
    path('production/<int:pk>/detail/', production.production_detail, name='production_detail'),
    path('production/<int:po_id>/print/', production.production_print, name='production_print'),
    path('production/<int:pk>/update-board/', production.update_production_board, name='update_production_board'),
    path('production/<int:pk>/start/', production.start_production, name='start_production'),
    path('production/<int:pk>/start-actual/', production.start_actual_production, name='start_actual_production'),
    path('production/<int:pk>/process/', production.production_process, name='production_process'),
    path('production/<int:pk>/generate-pos/', production.generate_pos_from_production, name='generate_pos_from_production'),
    path('production/<int:pk>/submit-qc/', production.submit_to_qc, name='submit_to_qc'),
    path('production/<int:pk>/process-qc/', production.process_qc, name='process_qc'),
    path('production/<int:pk>/media-hub/', production.media_hub, name='media_hub'),
    path('production/media-hub/', production.media_hub_list, name='media_hub_list'),
    path('production/my-log/', production.my_production_log, name='my_production_log'),
    path('production/my-qc-log/', production.my_qc_log, name='my_qc_log'),
    path('production/<int:pk>/add-material/', production.add_additional_material, name='add_additional_material'),
    path('production/material/<int:pk>/delete/', production.delete_production_material, name='delete_production_material'),
    
    # -- แบบแปลน (Blueprint Hub) --
    path('production/blueprint-hub/', production.blueprint_hub, name='blueprint_hub'),
    path('production/blueprint-hub/<int:pk>/workspace/', production.blueprint_workspace, name='blueprint_workspace'),
    path('production/blueprint-hub/<int:pk>/approve/', production.blueprint_approve, name='blueprint_approve'),
    path('production/<int:pk>/upload-blueprint/', production.upload_blueprint, name='upload_blueprint'),
    path('production/<int:pk>/blueprint-viewer/', production.blueprint_viewer, name='blueprint_viewer'),
    path('production/blueprint-hub/claim/', production.blueprint_create_claim, name='blueprint_create_claim'),
    path('production/blueprint-hub/claim/<int:pk>/print/', production.print_blueprint_claim, name='print_blueprint_claim'),
    path('production/blueprint-claim/<int:claim_id>/pay/', production.pay_blueprint_claim, name='pay_blueprint_claim'),

    # ==========================
    # 📦 หมวดคลังสินค้าและจัดซื้อ (Inventory & Purchasing)
    # ==========================
    path('production/inventory/', inventory.inventory_board, name='inventory_board'),
    path('production/<int:pk>/materials-ready/', inventory.materials_ready, name='materials_ready'),
    path('prepare-purchase/', inventory.ppo_prepare, name='ppo_prepare'),

    # ==========================
    # 🚚 หมวดจัดส่งสินค้า (Logistics)
    # ==========================
    path('production/<int:pk>/process-logistics/', logistics.process_logistics, name='process_logistics'),
    path('production/<int:pk>/print-delivery/', logistics.print_delivery_note, name='print_delivery_note'),
    path('production/<int:pk>/print-consent/', logistics.print_consent_form, name='print_consent_form'),
    path('production/<int:pk>/print-site-checklist/', logistics.print_site_checklist, name='print_site_checklist'),
    path('production/logistics-claim/', logistics.create_logistics_claim, name='create_logistics_claim'),
    path('production/logistics-claim/<int:pk>/print/', logistics.print_logistics_claim, name='print_logistics_claim'),
    path('production/logistics-claim/history/', logistics.logistics_claim_history, name='logistics_claim_history'),
    path('production/logistics-claim/<int:claim_id>/pay/', logistics.pay_logistics_claim, name='pay_logistics_claim'),
    path('logistics-history/', logistics.logistics_history_log, name='logistics_history_log'),

    # ==========================
    # 🛠️ หมวดแจ้งซ่อมและบริการ (Services)
    # ==========================
    path('production/service-tickets/<int:ticket_id>/process/', services.process_service_ticket, name='process_service_ticket'),
    path('production/service-history/', services.service_history_list, name='service_history_list'),
    path('production/service-tickets/<int:ticket_id>/claim-labor/', services.submit_service_labor_claim, name='submit_service_labor_claim'),

    # ==========================
    # 🧱 หมวดสูตรการผลิต (BOM)
    # ==========================
    path('bom/', bom.bom_list, name='bom_list'),
    path('bom/create/', bom.bom_create, name='bom_create'),
    path('bom/<int:pk>/', bom.bom_detail, name='bom_detail'),
    path('bom/<int:pk>/edit/', bom.bom_edit, name='bom_edit'),
    path('bom/<int:pk>/update-labor-cost/', bom.update_bom_labor_cost, name='update_bom_labor_cost'),
    path('bom/<int:pk>/print/', bom.print_master_bom, name='print_master_bom'),
    path('bom/import/', bom.import_bom_excel, name='import_bom_excel'),
    path('bom/import/template/', bom.download_bom_template, name='download_bom_template'),
    path('production/<int:pk>/load-bom/', bom.load_standard_bom, name='load_standard_bom'),
    path('production/<int:pk>/print-bom/', bom.print_bom, name='print_bom'),

    # ==========================
    # 🔄 AJAX Endpoints
    # ==========================
    path('ajax/add-branch/', production.ajax_add_branch, name='ajax_add_branch'),
    path('ajax/add-salesperson/', production.ajax_add_salesperson, name='ajax_add_salesperson'),
    path('ajax/add-prod-status/', production.ajax_add_prod_status, name='ajax_add_prod_status'),
    path('ajax/add-prod-team/', production.ajax_add_prod_team, name='ajax_add_prod_team'),
    path('ajax/add-delivery-status/', production.ajax_add_delivery_status, name='ajax_add_delivery_status'),
    path('ajax/get-fg-by-category/', production.ajax_get_fg_by_category, name='ajax_get_fg_by_category'),
    path('ajax/add-transporter/', logistics.ajax_add_transporter, name='ajax_add_transporter'),
    path('ajax/add-transporter-full/', logistics.ajax_add_transporter_full, name='ajax_add_transporter_full'),
    path('ajax/search-raw-material/', bom.ajax_search_raw_material, name='ajax_search_raw_material'),
]