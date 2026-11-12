from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction

from manufacturing.models import ProductionOrder
from inventory.models import InventoryDoc, StockMovement
from purchasing.models import PurchasePreparation

# ==========================================
# 🌟 กระดานคลังสินค้า (Inventory Board)
# ==========================================
@login_required
def inventory_board(request):
    orders = ProductionOrder.objects.select_related('quotation_ref', 'salesperson', 'branch', 'production_team', 'product').filter(status='WAITING_INVENTORY', is_closed=False).order_by('status', '-id')
    virtual_stock = {}

    for order in orders:
        shortage = []
        for item in order.materials.all():
            mat_id = item.raw_material.id
            required_qty = Decimal(str(item.quantity))
            if mat_id not in virtual_stock:
                virtual_stock[mat_id] = max(Decimal('0'), item.raw_material.stock_qty or Decimal('0'))

            if virtual_stock[mat_id] < required_qty:
                missing = required_qty - virtual_stock[mat_id]
                shortage.append(f"{item.raw_material.name} (ขาดอีก {missing:.2f})")
                virtual_stock[mat_id] = Decimal('0')
            else:
                virtual_stock[mat_id] -= required_qty
        order.has_shortage = len(shortage) > 0
        order.shortage_list = ", ".join(shortage)

    history_docs = InventoryDoc.objects.select_related('created_by').filter(doc_type='GI', reference__startswith='เบิกผลิต').order_by('-created_at')[:30]

    job_codes = []
    for doc in history_docs:
        if doc.reference and doc.reference.startswith("เบิกผลิต "):
            job_code = doc.reference.replace("เบิกผลิต ", "").strip()
            job_codes.append(job_code)
            doc.extracted_job_code = job_code
        else: doc.extracted_job_code = None

    jobs_with_qt = ProductionOrder.objects.filter(code__in=job_codes).select_related('quotation_ref')
    job_to_qt_map = {job.code: (job.quotation_ref.code if job.quotation_ref else "ไม่มีอ้างอิง") for job in jobs_with_qt}

    for doc in history_docs:
        if doc.extracted_job_code: doc.qt_code = job_to_qt_map.get(doc.extracted_job_code, "ไม่พบข้อมูล")
        else: doc.qt_code = "-"

    return render(request, 'manufacturing/inventory_board.html', {
        'orders': orders, 'history_docs': history_docs
    })

# ==========================================
# 🌟 เตรียมมัดรวมใบสั่งซื้อวัตถุดิบ (PPO Prepare)
# ==========================================
@login_required
def ppo_prepare(request):
    available_jobs = ProductionOrder.objects.filter(status='WAITING_MATERIALS', is_materials_ordered=False, ppo_ref__isnull=True).order_by('code')
    ppo_code = ""
    materials_by_supplier = {}
    selected_job_ids = []

    if request.method == 'POST':
        selected_job_ids = request.POST.getlist('job_ids')
        if selected_job_ids:
            ppo = PurchasePreparation.objects.create(created_by=getattr(request.user, 'employee', None))
            jobs = ProductionOrder.objects.filter(id__in=selected_job_ids)
            ppo.production_orders.set(jobs)
            ppo_code = ppo.code
            virtual_stock_used = {}

            for job in jobs:
                for item in job.materials.all():
                    total_needed = Decimal(str(item.quantity))
                    mat_id = item.raw_material.id
                    actual_stock = max(Decimal('0'), item.raw_material.stock_qty or Decimal('0'))
                    used_stock = virtual_stock_used.get(mat_id, Decimal('0'))
                    available_stock = max(Decimal('0'), actual_stock - used_stock)

                    if available_stock >= total_needed:
                        to_order_qty = Decimal('0')
                        virtual_stock_used[mat_id] = used_stock + total_needed
                    else:
                        to_order_qty = total_needed - available_stock
                        virtual_stock_used[mat_id] = used_stock + available_stock

                    supplier = item.raw_material.supplier
                    sup_id = supplier.id if supplier else "none"
                    sup_name = supplier.name if supplier else "ไม่ได้ระบุร้านค้า"

                    if sup_id not in materials_by_supplier: materials_by_supplier[sup_id] = {'name': sup_name, 'items': {}}
                    if mat_id not in materials_by_supplier[sup_id]['items']:
                        materials_by_supplier[sup_id]['items'][mat_id] = {
                            'product_id': item.raw_material.id, 'product_name': item.raw_material.name, 'product_code': item.raw_material.code,
                            'total_needed': Decimal('0'), 'in_stock': actual_stock, 'qty': Decimal('0'),
                            'cost': item.raw_material.cost_price or Decimal('0'), 'total': Decimal('0')
                        }

                    materials_by_supplier[sup_id]['items'][mat_id]['total_needed'] += total_needed
                    materials_by_supplier[sup_id]['items'][mat_id]['qty'] += to_order_qty
                    materials_by_supplier[sup_id]['items'][mat_id]['total'] = materials_by_supplier[sup_id]['items'][mat_id]['qty'] * materials_by_supplier[sup_id]['items'][mat_id]['cost']

            jobs.update(is_materials_ordered=True, ppo_ref=ppo_code)
            suppliers_to_remove = []

            for sup_id in materials_by_supplier:
                items_list = []
                for v in materials_by_supplier[sup_id]['items'].values():
                    if float(v['qty']) > 0:
                        v['total_needed'] = float(v['total_needed'])
                        v['in_stock'] = float(v['in_stock'])
                        v['qty'] = float(v['qty'])
                        v['cost'] = float(v['cost'])
                        v['total'] = float(v['total'])
                        items_list.append(v)
                if items_list: materials_by_supplier[sup_id]['items'] = items_list
                else: suppliers_to_remove.append(sup_id)

            for sup_id in suppliers_to_remove: del materials_by_supplier[sup_id]

            request.session['ppo_code'] = ppo_code
            request.session['materials_by_supplier'] = materials_by_supplier
            messages.success(request, f"สร้างใบเตรียมการสั่งซื้อสำเร็จ! เลขที่เอกสาร PPO มัดรวม: {ppo_code}")
            return redirect('ppo_prepare')
        else:
            messages.warning(request, "⚠️ กรุณาติ๊กเลือกอย่างน้อย 1 ใบสั่งผลิต (JOB) เพื่อคำนวณวัตถุดิบ")

    display_ppo_code = request.session.pop('ppo_code', '')
    display_materials = request.session.pop('materials_by_supplier', {})
    return render(request, 'manufacturing/ppo_prepare.html', {
        'available_jobs': available_jobs, 'ppo_code': display_ppo_code, 'materials_by_supplier': display_materials,
    })

# ==========================================
# 🌟 ตัดสต็อกวัตถุดิบ (Materials Ready)
# ==========================================
@login_required
@transaction.atomic
def materials_ready(request, pk):
    order = get_object_or_404(ProductionOrder, pk=pk)
    job_materials = order.materials.all()
    if not job_materials:
        messages.error(request, "❌ ไม่พบรายการวัตถุดิบในใบสั่งผลิตนี้")
        return redirect('inventory_board')

    shortage = []
    for item in job_materials:
        required_qty = Decimal(str(item.quantity))
        actual_stock = max(Decimal('0'), item.raw_material.stock_qty or Decimal('0'))
        if actual_stock < required_qty:
            shortage.append(f"{item.raw_material.name} (ขาด {required_qty - actual_stock:.2f})")

    if shortage:
        err_msg = " / ".join(shortage)
        messages.error(request, f"❌ ไม่สามารถตัดสต็อกได้! วัตถุดิบในคลังไม่พอ: {err_msg}")
        return redirect('inventory_board')

    doc_out = InventoryDoc(
        doc_type='GI', reference=f"เบิกผลิต {order.code}",
        description=f"เบิกวัตถุดิบเตรียมผลิต {order.product.name}", created_by=request.user
    )
    doc_out._doc_category = 'RM'
    doc_out.save()
    for item in job_materials:
        StockMovement.objects.create(doc=doc_out, product=item.raw_material, quantity=Decimal(str(item.quantity)), movement_type='OUT', created_by=request.user)

    order.status = 'IN_PROGRESS'
    order.save()
    messages.success(request, f"✅ ตัดสต็อกสำเร็จ! สถานะเปลี่ยนเป็น 'งานอยู่ระหว่างผลิต' เพื่อรอช่างและ QC ตรวจสอบแล้ว")
    return redirect('inventory_board')