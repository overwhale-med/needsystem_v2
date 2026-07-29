from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.db.models import Count, Sum, F, ExpressionWrapper, DecimalField, Q
from django.db.models.functions import Coalesce
from django.db import transaction
from django.http import JsonResponse
from django.core.paginator import Paginator
from decimal import Decimal, InvalidOperation
import datetime
import calendar
import json
import pandas as pd

from .models import ProductionOrder, ProductionOrderMaterial, BOM, BOMItem, Branch, MfgBranch, Salesperson, ProductionStatus, ProductionTeam, DeliveryStatus, Transporter, QCInspectionLog
from master_data.models import CompanyInfo
from inventory.models import Product, InventoryDoc, StockMovement
from purchasing.models import PurchaseOrder, PurchaseOrderItem, PurchasePreparation
from .forms import BOMForm, BOMItemFormSet
from .models import BlueprintClaimSplit
from .models import LogisticsClaim
from accounting.models import Expense

# ==========================================
# 🌟 ระบบใบสั่งผลิต (Production Order) 🌟
# ==========================================
@login_required
def production_list(request):
    start_date = request.GET.get('start_date', '')
    end_date = request.GET.get('end_date', '')
    search_q = request.GET.get('q', '')
    search_salesperson = request.GET.get('salesperson', '')
    search_team = request.GET.get('team', '')
    search_status = request.GET.get('status', '')
    search_branch = request.GET.get('branch', '')

    orders = ProductionOrder.objects.select_related(
        'product', 'quotation_ref', 'salesperson',
        'production_team', 'delivery_status', 'transporter', 'branch'
    ).prefetch_related('completed_departments').all().order_by('-id')

    if start_date:
        orders = orders.filter(start_date__gte=start_date)
    if end_date:
        orders = orders.filter(start_date__lte=end_date)
    if search_status:
        orders = orders.filter(status=search_status)
    if search_branch:
        orders = orders.filter(branch_id=search_branch)
    if search_q:
        orders = orders.filter(
            Q(code__icontains=search_q) | Q(customer_name__icontains=search_q) | Q(quotation_ref__code__icontains=search_q)
        )
    if search_salesperson:
        orders = orders.filter(salesperson_id=search_salesperson)
    if search_team:
        orders = orders.filter(production_team_id=search_team)

    active_qs = orders.filter(is_closed=False)
    closed_qs = orders.filter(is_closed=True)

    active_paginator = Paginator(active_qs, 10)
    active_page_num = request.GET.get('active_page', 1)
    active_orders = active_paginator.get_page(active_page_num)

    closed_paginator = Paginator(closed_qs, 10)
    closed_page_num = request.GET.get('closed_page', 1)
    closed_orders = closed_paginator.get_page(closed_page_num)

    url_params = request.GET.copy()
    if 'active_page' in url_params: del url_params['active_page']
    if 'closed_page' in url_params: del url_params['closed_page']
    filter_string = url_params.urlencode()

    branches = MfgBranch.objects.all().order_by('name')
    prod_statuses = ProductionStatus.objects.all().order_by('sequence', 'id')
    prod_teams = ProductionTeam.objects.all().order_by('name')
    deliv_statuses = DeliveryStatus.objects.all().order_by('name')
    transporters = Transporter.objects.all().order_by('name')
    salespersons = Salesperson.objects.all().order_by('name')
    total_departments_count = prod_statuses.count()
    system_status_choices = ProductionOrder.STATUS_CHOICES

    can_add_master_data = False
    is_sales = False

    if request.user.is_superuser:
        can_add_master_data = True
    else:
        current_emp = getattr(request.user, 'employee', None)
        is_manager = False
        is_planner = False

        user_groups = list(request.user.groups.values_list('name', flat=True))
        if any('Manager' in g for g in user_groups): is_manager = True
        if any('Planner' in g or 'Production' in g for g in user_groups): is_planner = True

        if current_emp:
            rank = current_emp.business_rank.lower() if current_emp.business_rank else ""
            job_title = current_emp.position.title.lower() if current_emp.position else ""
            dept_name = current_emp.department.name if current_emp.department else ""

            if rank in ['manager', 'director'] or 'manager' in job_title:
                is_manager = True
            if 'วางแผน' in dept_name or 'ผลิต' in dept_name:
                 is_planner = True

            if 'ขาย' in dept_name or 'sales' in dept_name.lower():
                 is_sales = True

        if is_manager and is_planner:
            can_add_master_data = True

    return render(request, 'manufacturing/production_list.html', {
        'active_orders': active_orders,
        'closed_orders': closed_orders,
        'branches': branches,
        'prod_statuses': prod_statuses,
        'prod_teams': prod_teams,
        'deliv_statuses': deliv_statuses,
        'transporters': transporters,
        'salespersons': salespersons,
        'start_date': start_date,
        'end_date': end_date,
        'search_q': search_q,
        'search_branch': search_branch,
        'search_salesperson': search_salesperson,
        'search_team': search_team,
        'search_status': search_status,
        'system_status_choices': system_status_choices,
        'filter_string': filter_string,
        'can_add_master_data': can_add_master_data,
        'is_sales': is_sales,
        'total_departments_count': total_departments_count,
    })

@login_required
def planner_board(request):
    today = timezone.now().date()
    default_start = today - datetime.timedelta(days=30)
    default_end = today + datetime.timedelta(days=30)

    start_date = request.GET.get('start_date', default_start.strftime('%Y-%m-%d'))
    end_date = request.GET.get('end_date', default_end.strftime('%Y-%m-%d'))

    search_q = request.GET.get('q', '')
    search_branch = request.GET.get('branch', '')
    search_team = request.GET.get('team', '')
    search_salesperson = request.GET.get('salesperson', '')

    orders = ProductionOrder.objects.select_related(
        'product', 'branch', 'production_team', 'salesperson', 'salesperson__branch', 'quotation_ref'
    ).all().order_by('-id')

    if start_date: orders = orders.filter(start_date__gte=start_date)
    if end_date: orders = orders.filter(start_date__lte=end_date)
    if search_q:
        orders = orders.filter(Q(code__icontains=search_q) | Q(customer_name__icontains=search_q) | Q(product__name__icontains=search_q))
    if search_branch: orders = orders.filter(branch_id=search_branch)
    if search_team: orders = orders.filter(production_team_id=search_team)
    if search_salesperson: orders = orders.filter(salesperson_id=search_salesperson)

    branches = MfgBranch.objects.all().order_by('name')
    teams = ProductionTeam.objects.all().order_by('name')
    salespersons = Salesperson.objects.select_related('branch').all().order_by('name')

    prod_statuses = ProductionStatus.objects.all().order_by('sequence', 'id')
    deliv_statuses = DeliveryStatus.objects.all().order_by('name')
    transporters = Transporter.objects.all().order_by('name')

    return render(request, 'manufacturing/planner_board.html', {
        'orders': orders,
        'branches': branches,
        'teams': teams,
        'salespersons': salespersons,
        'prod_statuses': prod_statuses,
        'deliv_statuses': deliv_statuses,
        'transporters': transporters,
        'start_date': start_date,
        'end_date': end_date,
        'search_q': search_q,
        'search_branch': search_branch,
        'search_team': search_team,
        'search_salesperson': search_salesperson,
    })

@login_required
def inventory_board(request):
    orders = ProductionOrder.objects.filter(status='WAITING_INVENTORY', is_closed=False).order_by('status', '-id')
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

    return render(request, 'manufacturing/inventory_board.html', {'orders': orders})

@login_required
def production_create(request):
    boms = BOM.objects.select_related('product').all()
    fg_with_bom = [bom.product for bom in boms]
    branches = Branch.objects.all().order_by('name')
    salespersons = Salesperson.objects.select_related('branch').all().order_by('name')

    if request.method == 'POST':
        product_id = request.POST.get('product')
        note = request.POST.get('note', '')
        start_date = request.POST.get('start_date')
        delivery_date = request.POST.get('delivery_date')
        branch_id = request.POST.get('branch')
        salesperson_id = request.POST.get('salesperson')
        customer_name = request.POST.get('customer_name', '')

        if product_id:
            product = get_object_or_404(Product, id=product_id)
            is_onsite = request.POST.get('is_onsite') == 'on'
            order = ProductionOrder(
                product=product,
                quantity=1,
                status='NEW_JOB',
                note=note,
                customer_name=customer_name,
                is_onsite=is_onsite,
                responsible_person=getattr(request.user, 'employee', None)
            )

            if start_date: order.start_date = start_date
            if delivery_date: order.delivery_date = delivery_date
            if salesperson_id: order.salesperson_id = salesperson_id

            order.save()
            messages.success(request, f"✅ สร้างใบสั่งผลิต {order.code} สำเร็จ! งานถูกส่งไปยังคอลัมน์รอจ่ายงาน (W1)")
            return redirect('planner_board')
        else:
            messages.error(request, "❌ กรุณาเลือกแบบบ้านที่ต้องการผลิต")

    return render(request, 'manufacturing/production_form.html', {
        'fg_with_bom': fg_with_bom,
        'branches': branches,
        'salespersons': salespersons
    })

@login_required
def start_production(request, pk):
    order = get_object_or_404(ProductionOrder, pk=pk)
    if not order.materials.exists():
        messages.warning(request, "⚠️ กรุณาดึงรายการวัตถุดิบ (BOM) ก่อนกดยืนยันแผนการผลิต!")
        return redirect('production_detail', pk=order.pk)

    order.status = 'WAITING_MATERIALS'
    order.save()
    messages.success(request, f"🚀 ยืนยันแผนงาน {order.code} แล้ว! งานถูกส่งไปที่ฝ่ายจัดซื้อ")
    return redirect('production_list')

@login_required
def ppo_prepare(request):
    available_jobs = ProductionOrder.objects.filter(status='WAITING_MATERIALS', is_materials_ordered=False).order_by('code')
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
            for job in jobs:
                bom = BOM.objects.filter(product=job.product).first()
                if bom:
                    for item in bom.items.all():
                        total_needed = Decimal(str(item.quantity))
                        supplier = item.raw_material.supplier
                        sup_id = supplier.id if supplier else "none"
                        sup_name = supplier.name if supplier else "ไม่ได้ระบุร้านค้า"
                        mat_id = item.raw_material.id
                        if sup_id not in materials_by_supplier: materials_by_supplier[sup_id] = {'name': sup_name, 'items': {}}

                        if mat_id not in materials_by_supplier[sup_id]['items']:
                            materials_by_supplier[sup_id]['items'][mat_id] = {
                                'product_id': item.raw_material.id,
                                'product_name': item.raw_material.name,
                                'product_code': item.raw_material.code,
                                'qty': Decimal('0'),
                                'cost': item.raw_material.cost_price or Decimal('0'),
                                'total': Decimal('0')
                            }
                        materials_by_supplier[sup_id]['items'][mat_id]['qty'] += total_needed
                        materials_by_supplier[sup_id]['items'][mat_id]['total'] = materials_by_supplier[sup_id]['items'][mat_id]['qty'] * materials_by_supplier[sup_id]['items'][mat_id]['cost']

            for sup_id in materials_by_supplier:
                items_list = []
                for v in materials_by_supplier[sup_id]['items'].values():
                    v['qty'] = float(v['qty'])
                    v['cost'] = float(v['cost'])
                    v['total'] = float(v['total'])
                    items_list.append(v)
                materials_by_supplier[sup_id]['items'] = items_list

            jobs.update(is_materials_ordered=True, status='WAITING_INVENTORY')
        else:
            messages.warning(request, "⚠️ กรุณาติ๊กเลือกอย่างน้อย 1 ใบสั่งผลิต (JOB) เพื่อคำนวณวัตถุดิบ")
    return render(request, 'manufacturing/ppo_prepare.html', {'available_jobs': available_jobs, 'ppo_code': ppo_code, 'materials_by_supplier': materials_by_supplier, 'selected_job_ids': [int(i) for i in selected_job_ids]})

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

    doc_out = InventoryDoc.objects.create(doc_type='GI', reference=f"เบิกผลิต {order.code}", description=f"เบิกวัตถุดิบเตรียมผลิต {order.product.name}", created_by=request.user)
    for item in job_materials:
        StockMovement.objects.create(doc=doc_out, product=item.raw_material, quantity=Decimal(str(item.quantity)), movement_type='OUT', created_by=request.user)

    if order.is_onsite:
        order.status = 'COMPLETED'
        order.finish_date = timezone.now().date()
        order.is_qc_passed = True
        order.save()
        messages.success(request, f"🚀 ตัดสต็อกสำเร็จ! (ประกอบหน้างาน) สถานะกระโดดไป 'รอจัดส่ง' ให้ขนส่งเรียบร้อยแล้ว!")
    else:
        order.status = 'IN_PROGRESS'
        order.save()
        messages.success(request, f"✅ ตัดสต็อกสำเร็จ! สถานะเปลี่ยนเป็น 'งานอยู่ระหว่างผลิต' แล้ว")

    return redirect('inventory_board')

@login_required
def start_actual_production(request, pk):
    return redirect('production_list')

@login_required
@transaction.atomic
def production_process(request, pk):
    order = get_object_or_404(ProductionOrder, pk=pk)
    if order.status == 'COMPLETED':
        messages.warning(request, "⚠️ รายการนี้ผลิตเสร็จและรับเข้าคลังไปแล้ว!")
        return redirect('production_list')

    main_product = order.product

    desc_text = f"รับสินค้า {main_product.name} จากการผลิต {order.code}"
    if order.customer_name:
        desc_text += f" (ลค. {order.customer_name})"

    doc_in = InventoryDoc.objects.create(doc_type='GR', reference=f"รับจาก {order.code}", description=desc_text, created_by=request.user)
    StockMovement.objects.create(doc=doc_in, product=main_product, quantity=Decimal(str(order.quantity)), movement_type='IN', created_by=request.user)

    order.status = 'COMPLETED'
    order.finish_date = timezone.now().date()
    order.save()

    messages.success(request, f"🎉 สำเร็จ! รับ {main_product.name} ({order.quantity} หลัง) เข้าคลังเรียบร้อยแล้ว!")
    return redirect('production_list')

@login_required
def production_detail(request, pk):
    order = get_object_or_404(ProductionOrder, pk=pk)
    materials = order.materials.all()
    has_bom = BOM.objects.filter(product=order.product).exists()
    raw_materials = Product.objects.filter(product_type='RM', is_active=True).order_by('code')

    return render(request, 'manufacturing/production_detail.html', {
        'order': order,
        'materials': materials,
        'has_bom': has_bom,
        'raw_materials': raw_materials
    })

@login_required
def print_bom(request, pk):
    order = get_object_or_404(ProductionOrder, pk=pk)
    materials = order.materials.all()
    company = CompanyInfo.objects.first()
    return render(request, 'manufacturing/print_bom.html', {'order': order, 'materials': materials, 'company': company})

@login_required
def upload_blueprint(request, pk):
    order = get_object_or_404(ProductionOrder, pk=pk)
    if request.method == 'POST' and 'blueprint_file' in request.FILES:
        order.blueprint_file = request.FILES['blueprint_file']
        order.save()
        messages.success(request, f"📎 แนบไฟล์แบบแปลน (Blueprint) สำหรับ {order.code} เรียบร้อยแล้ว")
    return redirect('production_detail', pk=order.pk)

@login_required
def load_standard_bom(request, pk):
    order = get_object_or_404(ProductionOrder, pk=pk)
    referer = request.META.get('HTTP_REFERER')

    if order.materials.exists():
        messages.warning(request, "⚠️ มีการดึงรายการสูตรผลิตในใบสั่งผลิตนี้ไปแล้ว")
        return redirect(referer) if referer else redirect('production_detail', pk=order.pk)

    bom = BOM.objects.filter(product=order.product).first()
    if not bom:
        messages.error(request, "❌ ไม่พบสูตรผลิตมาตรฐาน (BOM) สำหรับสินค้ารุ่นนี้")
        return redirect(referer) if referer else redirect('production_detail', pk=order.pk)

    for item in bom.items.all():
        ProductionOrderMaterial.objects.create(
            production_order=order,
            raw_material=item.raw_material,
            quantity=item.quantity * order.quantity,
            is_additional=False
        )
    messages.success(request, "📋 ดึงรายการวัตถุดิบจากสูตรมาตรฐานเรียบร้อยแล้ว!")
    return redirect(referer) if referer else redirect('production_detail', pk=order.pk)

@login_required
def add_additional_material(request, pk):
    order = get_object_or_404(ProductionOrder, pk=pk)
    referer = request.META.get('HTTP_REFERER')

    if request.method == 'POST':
        product_id = request.POST.get('raw_material')
        try:
            qty = Decimal(request.POST.get('quantity', '0'))
        except:
            qty = Decimal('0')

        if product_id and qty > 0:
            rm = get_object_or_404(Product, pk=product_id)
            ProductionOrderMaterial.objects.create(
                production_order=order,
                raw_material=rm,
                quantity=qty,
                is_additional=True
            )
            messages.success(request, f"➕ เพิ่มวัตถุดิบส่วนเพิ่ม: {rm.name} จำนวน {qty} ลงในบิลเรียบร้อยแล้ว")
        else:
            messages.error(request, "❌ กรุณาเลือกวัตถุดิบและใส่จำนวนให้ถูกต้อง")
    return redirect(referer) if referer else redirect('production_detail', pk=order.pk)

@login_required
def delete_production_material(request, pk):
    mat = get_object_or_404(ProductionOrderMaterial, pk=pk)
    order_id = mat.production_order.id
    referer = request.META.get('HTTP_REFERER')

    if mat.production_order.status != 'COMPLETED':
        mat.delete()
        messages.success(request, "🗑️ ลบรายการวัตถุดิบออกจากบิลผลิตเรียบร้อยแล้ว")
    else:
        messages.error(request, "❌ ไม่สามารถลบได้เนื่องจากใบสั่งผลิตนี้ดำเนินการเสร็จสิ้นแล้ว")
    return redirect(referer) if referer else redirect('production_detail', pk=order_id)

@login_required
def blueprint_viewer(request, pk):
    order = get_object_or_404(ProductionOrder, pk=pk)
    return render(request, 'manufacturing/blueprint_viewer.html', {'order': order})

@login_required
def generate_pos_from_production(request, pk):
    messages.info(request, "ฟังก์ชันนี้กำลังอยู่ระหว่างการพัฒนาเพิ่มเติม")
    return redirect('ppo_prepare')

@login_required
def production_print(request, po_id):
    po = get_object_or_404(ProductionOrder, id=po_id)
    bom = BOM.objects.filter(product=po.product).first()
    company = CompanyInfo.objects.first()
    return render(request, 'manufacturing/production_print.html', {'po': po, 'bom': bom, 'company': company})

@login_required
def bom_create(request):
    if request.method == 'POST':
        form = BOMForm(request.POST)
        formset = BOMItemFormSet(request.POST)
        if form.is_valid() and formset.is_valid():
             bom = form.save()
             formset.instance = bom
             formset.save()
             messages.success(request, f"✅ สร้างสูตรผลิตสำหรับ {bom.product.name} เรียบร้อยแล้ว!")
             return redirect('bom_detail', pk=bom.pk)
    else:
        form = BOMForm()
        formset = BOMItemFormSet()
    return render(request, 'manufacturing/bom_form.html', {'form': form, 'formset': formset, 'title': 'สร้างสูตรผลิตใหม่ (New BOM)'})

@login_required
def bom_detail(request, pk):
    bom = get_object_or_404(BOM, pk=pk)
    items = bom.items.select_related('raw_material', 'raw_material__supplier').all()

    total_cost = Decimal('0')
    for item in items:
        item.calculated_total_cost = Decimal(str(item.quantity)) * (item.raw_material.cost_price or Decimal('0'))
        total_cost += item.calculated_total_cost

    return render(request, 'manufacturing/bom_detail.html', {'bom': bom, 'items': items, 'total_cost': total_cost})

@login_required
def bom_edit(request, pk):
    bom = get_object_or_404(BOM.objects.prefetch_related('items'), pk=pk)

    if request.method == 'POST':
        form = BOMForm(request.POST, instance=bom)
        formset = BOMItemFormSet(request.POST, instance=bom)
        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            messages.success(request, f"✅ แก้ไขสูตรผลิต {bom.product.name} เรียบร้อยแล้ว!")
            return redirect('bom_detail', pk=bom.pk)
    else:
        form = BOMForm(instance=bom)
        formset = BOMItemFormSet(instance=bom)

    return render(request, 'manufacturing/bom_form.html', {'form': form, 'formset': formset, 'title': f'แก้ไขสูตรผลิต: {bom.product.code}'})

@login_required
def print_master_bom(request, pk):
    bom = get_object_or_404(BOM, pk=pk)
    items = bom.items.select_related('raw_material', 'raw_material__supplier').all()

    total_cost = Decimal('0')
    for item in items:
        item.calculated_total_cost = Decimal(str(item.quantity)) * (item.raw_material.cost_price or Decimal('0'))
        total_cost += item.calculated_total_cost

    company = CompanyInfo.objects.first()
    return render(request, 'manufacturing/print_master_bom.html', {
        'bom': bom,
        'items': items,
        'total_cost': total_cost,
        'company': company
    })

@login_required
def update_production_board(request, pk):
    if request.method == 'POST':
        order = get_object_or_404(ProductionOrder, pk=pk)
        action = request.POST.get('action')
        redirect_to = request.POST.get('redirect_to') 

        if action == 'update_note':
            order.note = request.POST.get('note', '')
            order.save()
            messages.success(request, f"💾 บันทึกหมายเหตุสำหรับ {order.code} เรียบร้อยแล้ว")
            if redirect_to == 'inventory_board':
                return redirect('inventory_board')

        if 'completed_departments' in request.POST:
            selected_depts = request.POST.getlist('completed_departments')
            order.completed_departments.set(selected_depts)
        elif action in ['update_progress', 'qc_complete_and_receive']:
             order.completed_departments.clear()

        if 'production_team' in request.POST:
            order.production_team_id = request.POST.get('production_team') or None
        
        if 'branch' in request.POST:
            order.branch_id = request.POST.get('branch') or None

        if action == 'dispatch' and order.status == 'NEW_JOB':
            order.status = 'WAITING_BLUEPRINT'
            messages.success(request, f"✅ จ่ายงาน {order.code} ไปยัง {order.branch.name if order.branch else 'ไม่ระบุโรงงาน'} เรียบร้อยแล้ว! (สถานะ: ตรวจแบบแปลน)")

        elif action in ['update_progress', 'qc_complete_and_receive']:
            order.qc_paint = request.POST.get('qc_paint') == 'on'
            order.qc_internal = request.POST.get('qc_internal') == 'on'
            order.qc_external = request.POST.get('qc_external') == 'on'
            order.qc_electrical = request.POST.get('qc_electrical') == 'on'
            order.qc_plumbing = request.POST.get('qc_plumbing') == 'on'
            order.qc_aircon = request.POST.get('qc_aircon') == 'on'

            if action == 'qc_complete_and_receive':
                if order.status != 'COMPLETED':
                    main_product = order.product

                    desc_text = f"รับสินค้า {main_product.name} จาก {order.code} (QC Pass)"
                    if order.customer_name:
                        desc_text += f" (ลค. {order.customer_name})"

                    doc_in = InventoryDoc.objects.create(doc_type='GR', reference=f"รับจาก {order.code}", description=desc_text, created_by=request.user)
                    StockMovement.objects.create(doc=doc_in, product=main_product, quantity=Decimal(str(order.quantity)), movement_type='IN', created_by=request.user)

                    order.status = 'COMPLETED'
                    order.finish_date = timezone.now().date()
                    order.is_qc_passed = True
                    messages.success(request, f"🎉 ผ่าน QC และรับ {main_product.name} เข้าคลังแล้ว! งานย้ายไปช่อง W4 พร้อมส่ง")
            else:
                messages.success(request, f"✅ อัปเดตความคืบหน้า {order.code} เรียบร้อยแล้ว!")

        is_closed = request.POST.get('is_closed')
        if is_closed == 'on':
            order.is_closed = True
            messages.success(request, f"✅ ปิดจ๊อบ {order.code} อย่างสมบูรณ์แล้ว! (ย้ายไปแท็บประวัติ)")
        elif action in ['update_progress', 'qc_complete_and_receive'] and not is_closed:
            if order.status != 'COMPLETED':
                order.is_closed = False

        order.save()

    return redirect(request.META.get('HTTP_REFERER', 'production_list'))

@login_required
def ajax_add_branch(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        name = data.get('name')
        if name:
            obj, created = Branch.objects.get_or_create(name=name)
            return JsonResponse({'success': True, 'id': obj.id, 'name': obj.name})
    return JsonResponse({'success': False})

@login_required
def ajax_add_salesperson(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        name = data.get('name')
        branch_id = data.get('branch_id')
        if name and branch_id:
            obj, created = Salesperson.objects.get_or_create(name=name, branch_id=branch_id)
            return JsonResponse({'success': True, 'id': obj.id, 'name': obj.name, 'branch_id': obj.branch.id})
    return JsonResponse({'success': False})

@login_required
def ajax_add_prod_status(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        name = data.get('name')
        if name:
            obj, _ = ProductionStatus.objects.get_or_create(name=name, defaults={'sequence': 99})
            return JsonResponse({'success': True, 'id': obj.id, 'name': obj.name})
    return JsonResponse({'success': False})

@login_required
def ajax_add_prod_team(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        name = data.get('name')
        if name:
            obj, _ = ProductionTeam.objects.get_or_create(name=name)
            return JsonResponse({'success': True, 'id': obj.id, 'name': obj.name})
    return JsonResponse({'success': False})

@login_required
def ajax_add_delivery_status(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        name = data.get('name')
        if name:
            obj, _ = DeliveryStatus.objects.get_or_create(name=name)
            return JsonResponse({'success': True, 'id': obj.id, 'name': obj.name})
    return JsonResponse({'success': False})

@login_required
def ajax_add_transporter(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        name = data.get('name')
        if name:
            obj, _ = Transporter.objects.get_or_create(name=name)
            return JsonResponse({'success': True, 'id': obj.id, 'name': obj.name})
    return JsonResponse({'success': False})

@login_required
def ajax_get_fg_by_category(request):
    category_id = request.GET.get('category_id')
    products = Product.objects.filter(product_type='FG', is_active=True).exclude(code__contains='-JOB')
    if category_id:
        products = products.filter(category_id=category_id)
    product_list = list(products.values('id', 'name', 'code'))
    return JsonResponse({'products': product_list})

@login_required
def import_bom_excel(request):
    if request.method == 'POST' and request.FILES.get('excel_file'):
        excel_file = request.FILES['excel_file']
        try:
            df = pd.read_excel(excel_file)
            required_columns = ['FG SKU', 'RM SKU', 'Quantity']
            if not all(col in df.columns for col in required_columns):
                messages.error(request, "❌ รูปแบบไฟล์ไม่ถูกต้อง กรุณาใช้คอลัมน์: FG SKU, RM SKU, Quantity")
                return redirect('import_bom_excel')
            with transaction.atomic():
                 import_count = 0
                 for _, row in df.iterrows():
                    fg_sku = str(row['FG SKU']).strip()
                    rm_sku = str(row['RM SKU']).strip()
                    try:
                        qty = Decimal(str(row['Quantity']))
                    except (ValueError, TypeError, InvalidOperation):
                        continue
                    fg_product = Product.objects.filter(code=fg_sku, product_type='FG').first()
                    if not fg_product:
                        continue
                    bom_obj, _ = BOM.objects.get_or_create(
                        product=fg_product,
                        defaults={'name': f"สูตรมาตรฐาน - {fg_product.name}"}
                     )
                    rm_product = Product.objects.filter(code=rm_sku, product_type='RM').first()
                    if rm_product:
                        BOMItem.objects.update_or_create(
                            bom=bom_obj,
                            raw_material=rm_product,
                            defaults={'quantity': qty}
                        )
                        import_count += 1
            messages.success(request, f"✅ นำเข้าข้อมูลสูตรผลิตสำเร็จทั้งหมด {import_count} รายการ")
            return redirect('import_bom_excel')
        except Exception as e:
            messages.error(request, f"❌ เกิดข้อผิดพลาด: {str(e)}")
    return render(request, 'manufacturing/import_bom.html')

@login_required
def ajax_search_raw_material(request):
    q = request.GET.get('q', '')
    products = Product.objects.filter(product_type='RM', is_active=True)
    if q: products = products.filter(Q(code__icontains=q) | Q(name__icontains=q))
    products = products.order_by('code')[:30]
    results = [{'id': p.id, 'text': f"{p.code} - {p.name}"} for p in products]
    return JsonResponse({'results': results})

# ==========================================
# 🌟 [NEW] กระดานสำหรับหัวหน้าแผนกผลิต (ช่าง) 🌟
# ==========================================
@login_required
def production_head_board(request):
    today = timezone.now().date()
    default_start = today - datetime.timedelta(days=30)
    default_end = today + datetime.timedelta(days=30)

    current_monday = today - datetime.timedelta(days=today.weekday())
    current_sunday = current_monday + datetime.timedelta(days=6)
    next_monday = current_monday + datetime.timedelta(days=7)
    next_sunday = next_monday + datetime.timedelta(days=6)

    thai_year_curr = str(current_sunday.year + 543)[-2:]
    thai_year_next = str(next_sunday.year + 543)[-2:]

    if current_monday.month == current_sunday.month:
        str_current_week = f"{current_monday.day}-{current_sunday.day}/{current_monday.month}/{thai_year_curr}"
    else:
        str_current_week = f"{current_monday.day}/{current_monday.month}-{current_sunday.day}/{current_sunday.month}/{thai_year_curr}"

    if next_monday.month == next_sunday.month:
        str_next_week = f"{next_monday.day}-{next_sunday.day}/{next_monday.month}/{thai_year_next}"
    else:
        str_next_week = f"{next_monday.day}/{next_monday.month}-{next_sunday.day}/{next_sunday.month}/{thai_year_next}"

    start_date = request.GET.get('start_date', default_start.strftime('%Y-%m-%d'))
    end_date = request.GET.get('end_date', default_end.strftime('%Y-%m-%d'))
    search_q = request.GET.get('q', '')
    search_branch = request.GET.get('branch', '')
    search_team = request.GET.get('team', '')
    search_salesperson = request.GET.get('salesperson', '')

    orders = ProductionOrder.objects.select_related(
        'product', 'branch', 'production_team', 'salesperson', 'salesperson__branch', 'quotation_ref'
    ).prefetch_related('completed_departments', 'qc_logs').filter(
        status__in=['PLANNED', 'IN_PROGRESS', 'REWORK'], is_closed=False
    ).order_by('start_date', '-id')

    emp = getattr(request.user, 'employee', None)
    is_manager = False

    if request.user.is_superuser:
        is_manager = True
    elif emp:
        rank = emp.business_rank.lower() if emp.business_rank else ""
        job_title = emp.position.title.lower() if emp.position else ""
        if rank in ['manager', 'director'] or 'manager' in job_title:
            is_manager = True

    if not is_manager and emp and emp.production_team:
        orders = orders.filter(production_team=emp.production_team)

    if start_date: orders = orders.filter(start_date__gte=start_date)
    if end_date: orders = orders.filter(start_date__lte=end_date)
    if search_q:
        orders = orders.filter(Q(code__icontains=search_q) | Q(customer_name__icontains=search_q) | Q(product__name__icontains=search_q))
    if search_branch: orders = orders.filter(branch_id=search_branch)
    if search_team: orders = orders.filter(production_team_id=search_team)
    if search_salesperson: orders = orders.filter(salesperson_id=search_salesperson)

    def format_week_range(d):
        iso_y, iso_w, _ = d.isocalendar()
        monday = datetime.date.fromisocalendar(iso_y, iso_w, 1)
        sunday = monday + datetime.timedelta(days=6)
        y_str = str(sunday.year + 543)[-2:]
        if monday.month == sunday.month:
            return f"จ.{monday.day}-อา.{sunday.day}/{monday.month}/{y_str}"
        else:
            return f"จ.{monday.day}/{monday.month}-อา.{sunday.day}/{sunday.month}/{y_str}"

    col1_upcoming = []  
    col2_current = []   
    col3_overdue = []   
    col4_rework = []    

    for order in orders:
        order.display_cohort = format_week_range(order.start_date)

        if order.status == 'PLANNED':
            col1_upcoming.append(order)
        elif order.status == 'REWORK':
            col4_rework.append(order)
        elif order.status == 'IN_PROGRESS':
            if order.start_date < current_monday:
                col3_overdue.append(order)
            else:
                col2_current.append(order)

    branches = MfgBranch.objects.all().order_by('name')
    teams = ProductionTeam.objects.all().order_by('name')
    salespersons = Salesperson.objects.select_related('branch').all().order_by('name')
    prod_statuses = ProductionStatus.objects.all().order_by('sequence', 'id')

    return render(request, 'manufacturing/production_head_board.html', {
        'orders': orders, 
        'col1_upcoming': col1_upcoming,
        'col2_current': col2_current,
        'col3_overdue': col3_overdue,
        'col4_rework': col4_rework,
        'str_current_week': str_current_week,
        'str_next_week': str_next_week,
        'branches': branches,
        'teams': teams,
        'salespersons': salespersons,
        'prod_statuses': prod_statuses,
        'start_date': start_date,
        'end_date': end_date,
        'search_q': search_q,
        'search_branch': search_branch,
        'search_team': search_team,
        'search_salesperson': search_salesperson,
    })

@login_required
def submit_to_qc(request, pk):
    order = get_object_or_404(ProductionOrder, pk=pk)
    if order.status in ['IN_PROGRESS', 'REWORK']:
        order.status = 'WAITING_QC'
        order.save()
        messages.success(request, f"✅ ส่งงาน {order.code} ให้แผนก QC ตรวจสอบเรียบร้อยแล้ว!")
    return redirect('production_head_board')

# ==========================================
# 🌟 [NEW] กระดานสำหรับหัวหน้าแผนก QC (ตรวจสอบคุณภาพ) 🌟
# ==========================================
@login_required
def qc_board(request):
    today = timezone.now().date()
    default_start = today - datetime.timedelta(days=30)
    default_end = today + datetime.timedelta(days=30)

    current_monday = today - datetime.timedelta(days=today.weekday())
    current_sunday = current_monday + datetime.timedelta(days=6)
    thai_year_curr = str(current_sunday.year + 543)[-2:]

    if current_monday.month == current_sunday.month:
        str_current_week = f"{current_monday.day}-{current_sunday.day}/{current_monday.month}/{thai_year_curr}"
    else:
        str_current_week = f"{current_monday.day}/{current_monday.month}-{current_sunday.day}/{current_sunday.month}/{thai_year_curr}"

    start_date = request.GET.get('start_date', default_start.strftime('%Y-%m-%d'))
    end_date = request.GET.get('end_date', default_end.strftime('%Y-%m-%d'))
    search_q = request.GET.get('q', '')
    search_branch = request.GET.get('branch', '')
    search_team = request.GET.get('team', '')
    search_salesperson = request.GET.get('salesperson', '')

    orders = ProductionOrder.objects.select_related(
        'product', 'branch', 'production_team', 'salesperson', 'salesperson__branch', 'quotation_ref'
    ).prefetch_related('qc_logs').filter(
        status__in=['WAITING_QC', 'REWORK'], is_closed=False
    ).order_by('start_date', '-id')

    if start_date: orders = orders.filter(start_date__gte=start_date)
    if end_date: orders = orders.filter(start_date__lte=end_date)
    if search_q:
        orders = orders.filter(Q(code__icontains=search_q) | Q(customer_name__icontains=search_q) | Q(product__name__icontains=search_q))
    if search_branch: orders = orders.filter(branch_id=search_branch)
    if search_team: orders = orders.filter(production_team_id=search_team)
    if search_salesperson: orders = orders.filter(salesperson_id=search_salesperson)

    def format_week_range(d):
        iso_y, iso_w, _ = d.isocalendar()
        monday = datetime.date.fromisocalendar(iso_y, iso_w, 1)
        sunday = monday + datetime.timedelta(days=6)
        y_str = str(sunday.year + 543)[-2:]
        if monday.month == sunday.month:
            return f"จ.{monday.day}-อา.{sunday.day}/{monday.month}/{y_str}"
        else:
            return f"จ.{monday.day}/{monday.month}-อา.{sunday.day}/{sunday.month}/{y_str}"

    col1_current = []   
    col2_overdue = []   
    col3_rework = []    

    for order in orders:
        order.display_cohort = format_week_range(order.start_date)

        if order.status == 'REWORK':
            col3_rework.append(order)
        elif order.status == 'WAITING_QC':
            if order.start_date < current_monday:
                col2_overdue.append(order)
            else:
                col1_current.append(order)

    branches = MfgBranch.objects.all().order_by('name')
    teams = ProductionTeam.objects.all().order_by('name')
    salespersons = Salesperson.objects.select_related('branch').all().order_by('name')

    return render(request, 'manufacturing/qc_board.html', {
        'orders': orders,
        'col1_current': col1_current,
        'col2_overdue': col2_overdue,
        'col3_rework': col3_rework,
        'str_current_week': str_current_week,
        'branches': branches,
        'teams': teams,
        'salespersons': salespersons,
        'start_date': start_date,
        'end_date': end_date,
        'search_q': search_q,
        'search_branch': search_branch,
        'search_team': search_team,
        'search_salesperson': search_salesperson,
    })

@login_required
@transaction.atomic
def process_qc(request, pk):
    order = get_object_or_404(ProductionOrder, pk=pk)

    if request.method == 'POST':
        action = request.POST.get('action')

        order.qc_paint = request.POST.get('qc_paint') == 'on'
        order.qc_internal = request.POST.get('qc_internal') == 'on'
        order.qc_external = request.POST.get('qc_external') == 'on'
        order.qc_electrical = request.POST.get('qc_electrical') == 'on'
        order.qc_plumbing = request.POST.get('qc_plumbing') == 'on'
        order.qc_aircon = request.POST.get('qc_aircon') == 'on'

        if action == 'save_progress':
            order.save()
            messages.success(request, f"💾 บันทึกความคืบหน้าการตรวจ QC สำหรับ {order.code} เรียบร้อยแล้ว! (รอตรวจต่อ)")
            return redirect('qc_board')

        elif action == 'pass':
            alloc_code = f"{order.product.code}-{order.code}"
            alloc_name = f"{order.product.name} [{order.code}]"
            if order.customer_name: alloc_name += f" (ลค. {order.customer_name})"

            allocated_product, created = Product.objects.get_or_create(
                code=alloc_code,
                defaults={
                    'name': alloc_name[:255], 'category': order.product.category,
                    'product_type': 'FG', 'sell_price': order.product.sell_price,
                    'cost_price': order.product.cost_price, 'min_level': 0,
                    'stock_qty': 0, 'is_active': True,
                }
            )

            doc_in = InventoryDoc.objects.create(doc_type='GR', reference=f"รับจาก {order.code}", description=f"รับสินค้าจากฝ่ายผลิต {order.code} (ผ่าน QC)", created_by=request.user)
            StockMovement.objects.create(doc=doc_in, product=allocated_product, quantity=Decimal(str(order.quantity)), movement_type='IN', created_by=request.user)

            order.status = 'COMPLETED'
            order.finish_date = timezone.now().date()
            order.is_qc_passed = True
            order.save()

            messages.success(request, f"🎉 ตรวจผ่านเรียบร้อย! รับ {allocated_product.name} เข้าคลังแล้ว งานย้ายไปช่อง W4 พร้อมส่ง")

        elif action == 'fail':
            comments = request.POST.get('comments', '')
            order.rework_count += 1
            order.status = 'REWORK' 

            log = QCInspectionLog.objects.create(
                production_order=order,
                round_number=order.rework_count,
                inspector=getattr(request.user, 'employee', None),
                status='FAILED',
                comments=comments
            )

            if 'defect_image_1' in request.FILES:
                log.defect_image_1 = request.FILES['defect_image_1']
            if 'defect_image_2' in request.FILES:
                log.defect_image_2 = request.FILES['defect_image_2']

            log.save()
            order.save()

            messages.warning(request, f"🚨 ตีกลับงาน {order.code} ให้ช่างแก้ไขเรียบร้อยแล้ว (การตีกลับรอบที่ {order.rework_count})")

    return redirect('qc_board')

# ==========================================
# 🌟 [NEW] ศูนย์ตรวจสอบแบบแปลนและตั้งเบิก (Blueprint Hub) 🌟
# ==========================================
from .models import BlueprintClaim, BlueprintLog

@login_required
def blueprint_hub(request):
    current_emp = getattr(request.user, 'employee', None)

    start_date = request.GET.get('start_date', '')
    end_date = request.GET.get('end_date', '')
    q_job = request.GET.get('q_job', '')
    q_customer = request.GET.get('q_customer', '')
    search_sp = request.GET.get('salesperson', '')
    claim_status = request.GET.get('claim_status', '')

    pending_jobs = ProductionOrder.objects.select_related('product', 'salesperson', 'salesperson__branch').filter(
        status__in=['WAITING_BLUEPRINT', 'PLANNED'],
        is_closed=False
    ).order_by('start_date')

    history_jobs = ProductionOrder.objects.select_related(
        'product', 'salesperson', 'salesperson__branch', 'blueprint_approved_by', 'blueprint_claim'
    ).filter(blueprint_approved_by__isnull=False)

    if start_date:
        history_jobs = history_jobs.filter(blueprint_approved_at__date__gte=start_date)
    if end_date:
        history_jobs = history_jobs.filter(blueprint_approved_at__date__lte=end_date)
    if q_job:
        history_jobs = history_jobs.filter(code__icontains=q_job)
    if q_customer:
        history_jobs = history_jobs.filter(customer_name__icontains=q_customer)
    if search_sp:
        history_jobs = history_jobs.filter(salesperson_id=search_sp)

    if claim_status == 'UNCLAIMED':
        history_jobs = history_jobs.filter(blueprint_claim__isnull=True)
    elif claim_status in ['PENDING', 'PAID', 'REJECTED']:
        history_jobs = history_jobs.filter(blueprint_claim__status=claim_status)

    history_jobs = history_jobs.order_by('-blueprint_approved_at')[:100] 

    claimable_jobs = ProductionOrder.objects.filter(
        blueprint_approved_by=current_emp,
        blueprint_claim__isnull=True,
        quotation_ref__invoice__isnull=False 
    ).order_by('blueprint_approved_at')

    waiting_invoice_jobs = ProductionOrder.objects.filter(
        blueprint_approved_by=current_emp,
        blueprint_claim__isnull=True,
        quotation_ref__invoice__isnull=True 
    ).order_by('blueprint_approved_at')

    claims = BlueprintClaim.objects.filter(employee=current_emp).order_by('-created_at')

    salespersons = Salesperson.objects.select_related('branch').all().order_by('name')

    return render(request, 'manufacturing/blueprint_hub.html', {
        'pending_jobs': pending_jobs,
        'history_jobs': history_jobs,
        'claimable_jobs': claimable_jobs,
        'waiting_invoice_jobs': waiting_invoice_jobs, 
        'claims': claims,
        'salespersons': salespersons,
        'start_date': start_date,
        'end_date': end_date,
        'q_job': q_job,
        'q_customer': q_customer,
        'search_sp': search_sp,
        'claim_status': claim_status,
    })

@login_required
def blueprint_workspace(request, pk):
    order = get_object_or_404(ProductionOrder, pk=pk)
    materials = order.materials.all()
    has_bom = BOM.objects.filter(product=order.product).exists()
    raw_materials = Product.objects.filter(product_type='RM', is_active=True).order_by('code')
    logs = order.blueprint_logs.all()

    return render(request, 'manufacturing/blueprint_workspace.html', {
        'order': order,
        'materials': materials,
        'has_bom': has_bom,
        'raw_materials': raw_materials,
        'logs': logs
    })

@login_required
def blueprint_approve(request, pk):
    order = get_object_or_404(ProductionOrder, pk=pk)
    current_emp = getattr(request.user, 'employee', None)

    if request.method == 'POST':
        order.status = 'WAITING_MATERIALS'
        order.blueprint_approved_by = current_emp
        order.blueprint_approved_at = timezone.now()
        order.save()

        BlueprintLog.objects.create(
            production_order=order,
            action="ตรวจสอบความถูกต้องของแบบแปลนและโครงสร้างวัตถุดิบ (Approve)",
            employee=current_emp
        )

        messages.success(request, f"✅ ยืนยันความถูกต้องของ JOB {order.code} เรียบร้อย! งานถูกส่งต่อไปยังแผนกสั่งวัตถุดิบแล้วค่ะ")
        return redirect('blueprint_hub')
    return redirect('blueprint_workspace', pk=pk)

@login_required
def blueprint_create_claim(request):
    if request.method == 'POST':
        job_ids = request.POST.getlist('job_ids')
        current_emp = getattr(request.user, 'employee', None)

        if job_ids and current_emp:
            group = current_emp.sales_group
            if not group or group.flat_rate_amount <= 0:
                messages.error(request, "❌ ไม่สามารถตั้งเบิกได้: คุณยังไม่มีสังกัดทีม หรือ ทีมยังไม่ได้ตั้งค่า 'ค่าตอบแทนเหมาจ่าย'")
                return redirect('blueprint_hub')

            jobs = ProductionOrder.objects.filter(id__in=job_ids, blueprint_approved_by=current_emp, blueprint_claim__isnull=True)
            if jobs.exists():
                rate_per_job = Decimal(str(group.flat_rate_amount))
                total_jobs = jobs.count()
                total_amount = Decimal(str(total_jobs)) * rate_per_job

                claim = BlueprintClaim.objects.create(employee=current_emp, total_jobs=total_jobs, total_amount=total_amount)
                jobs.update(blueprint_claim=claim)

                members = group.members.all()
                l1_count = members.filter(group_role='LEVEL1').count() or 1
                l2_count = members.filter(group_role='LEVEL2').count() or 1

                for member in members:
                    share_pct = Decimal('0')
                    if member.group_role == 'LEADER':
                        share_pct = Decimal(str(group.share_leader))
                    elif member.group_role == 'LEVEL1':
                        share_pct = Decimal(str(group.share_level1)) / Decimal(str(l1_count))
                    elif member.group_role == 'LEVEL2':
                        share_pct = Decimal(str(group.share_level2)) / Decimal(str(l2_count))

                    if share_pct > 0:
                        split_amount = (total_amount * share_pct) / Decimal('100')
                        BlueprintClaimSplit.objects.create(
                            claim=claim, employee=member, role_name=member.get_group_role_display(),
                            percentage=share_pct, amount=split_amount
                        )

                messages.success(request, f"💰 สร้างใบตั้งเบิก {claim.code} สำเร็จ! และระบบกระจายยอดเงินให้ลูกทีมอัตโนมัติเรียบร้อยค่ะ")
            else:
                messages.error(request, "❌ ไม่พบงานที่สามารถตั้งเบิกได้ หรือมีการเบิกไปแล้ว")
        else:
            messages.warning(request, "⚠️ กรุณาเลือกงานอย่างน้อย 1 รายการ")
    return redirect('blueprint_hub')

def get_thai_baht_text(number):
    if number == 0: return "ศูนย์บาทถ้วน"
    import math
    number = round(number, 2)
    baht = math.floor(number)
    satang = int((number - baht) * 100)

    def read_num(n):
        if n == 0: return ""
        numbers = ["", "หนึ่ง", "สอง", "สาม", "สี่", "ห้า", "หก", "เจ็ด", "แปด", "เก้า"]
        positions = ["", "สิบ", "ร้อย", "พัน", "หมื่น", "แสน", "ล้าน"]
        s = str(n)
        length = len(s)
        res = ""
        for i, digit in enumerate(s):
            val = int(digit)
            pos = length - i - 1
            if val == 0:
                continue
            if pos == 0 and val == 1 and length > 1:
                res += "เอ็ด"
            elif pos == 1 and val == 1:
                res += "สิบ"
            elif pos == 1 and val == 2:
                res += "ยี่สิบ"
            else:
                res += numbers[val] + positions[pos]
        return res

    res = ""
    if baht > 0:
        res += read_num(baht) + "บาท"
    if satang > 0:
        res += read_num(satang) + "สตางค์"
    else:
        res += "ถ้วน"
    return res

@login_required
def print_blueprint_claim(request, pk):
    claim = get_object_or_404(BlueprintClaim, pk=pk)
    company = CompanyInfo.objects.first()
    jobs = claim.production_orders.all()
    amount_text = get_thai_baht_text(claim.total_amount)

    splits = claim.splits.all()

    total_split_amount = sum([s.amount for s in splits]) if splits else Decimal('0')
    fund_amount = claim.total_amount - total_split_amount 

    total_split_percent = sum([s.percentage for s in splits]) if splits else Decimal('0')
    fund_percentage = Decimal('100') - total_split_percent 

    return render(request, 'manufacturing/print_blueprint_claim.html', {
        'claim': claim,
        'jobs': jobs,
        'company': company,
        'amount_text': amount_text,
        'fund_amount': fund_amount,
        'fund_percentage': fund_percentage, 
    })

# ==========================================
# 🌟 [NEW] กระดานสำหรับแผนกจัดส่งสินค้า (Logistics Board) 🌟
# ==========================================
@login_required
def logistics_board(request):
    orders = ProductionOrder.objects.select_related(
        'product', 'branch', 'transporter', 'delivery_status', 'quotation_ref', 'logistics_claim'
    ).filter(
        Q(status='COMPLETED') | Q(status='WAITING_QC') | Q(is_onsite=True)
    ).order_by('delivery_date', '-id')

    col1_pending, col2_delivering, col3_delivered = [], [], []

    for order in orders:
        # 🌟 [NEW] ลอจิกตรวจสอบยอดค้างชำระที่แท้จริงจาก Invoice (ถ้ามี) 🌟
        order.actual_balance = Decimal('0')
        if order.quotation_ref:
            inv = None
            if hasattr(order.quotation_ref, 'invoice_set'):
                inv = order.quotation_ref.invoice_set.first()
            elif hasattr(order.quotation_ref, 'invoice'):
                inv = order.quotation_ref.invoice
            
            if inv:
                # ถ้ามีการเปิด Invoice แล้ว ยึดยอดคงเหลือจาก Invoice เป็นหลัก
                order.actual_balance = getattr(inv, 'balance_amount', Decimal('0'))
            else:
                # ถ้ายังไม่เปิด Invoice ให้ดูยอดคงค้างจาก Quotation
                grand_total = getattr(order.quotation_ref, 'grand_total', Decimal('0'))
                deposit = getattr(order.quotation_ref, 'deposit_amount', Decimal('0'))
                order.actual_balance = getattr(order.quotation_ref, 'balance_due', grand_total - deposit)

        # จัดกลุ่มลงคอลัมน์
        if order.transporter is None:
            col1_pending.append(order)
        elif order.delivery_status and order.delivery_status.name in ['ส่งมอบสำเร็จ', 'ลูกค้าเซ็นรับแล้ว', 'จัดส่งเรียบร้อย']:
            col3_delivered.append(order)
        else:
             col2_delivering.append(order)

    transporters = Transporter.objects.all().order_by('name')
    delivery_statuses = DeliveryStatus.objects.all().order_by('name')
    claims = LogisticsClaim.objects.all().order_by('-created_at')[:20]

    return render(request, 'manufacturing/logistics_board.html', {
        'orders': orders, 'col1_pending': col1_pending, 'col2_delivering': col2_delivering,
        'col3_delivered': col3_delivered, 'transporters': transporters,
        'delivery_statuses': delivery_statuses, 'claims': claims
    })

@login_required
@transaction.atomic
def process_logistics(request, pk):
    order = get_object_or_404(ProductionOrder, pk=pk)
    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'assign_truck':
            transporter_id = request.POST.get('transporter')
            delivery_fee = request.POST.get('delivery_fee', 0)
            delivery_date_str = request.POST.get('delivery_date') 

            if transporter_id:
                order.transporter_id = transporter_id

                if delivery_date_str:
                    order.delivery_date = parse_date(delivery_date_str)

                try:
                    order.delivery_fee = Decimal(str(delivery_fee).replace(',', ''))
                except:
                    order.delivery_fee = Decimal('0.00')

                messages.success(request, f"🚛 จ่ายงาน {order.code} ให้ทีมขนส่งและระบุค่าจ้างเรียบร้อยแล้ว!")

        elif action == 'update_status':
            delivery_status_id = request.POST.get('delivery_status')
            if delivery_status_id:
                status_obj = DeliveryStatus.objects.get(id=delivery_status_id)
                if status_obj.name in ['ส่งมอบสำเร็จ', 'ลูกค้าเซ็นรับแล้ว', 'จัดส่งเรียบร้อย']:
                    if 'proof_of_delivery' in request.FILES:
                        order.proof_of_delivery = request.FILES['proof_of_delivery']
                        order.delivery_status_id = delivery_status_id
                        messages.success(request, "📸 อัปโหลดรูปลายเซ็นและปิดงานส่งสำเร็จ!")
                    elif order.proof_of_delivery:
                        order.delivery_status_id = delivery_status_id
                        messages.success(request, "📦 อัปเดตสถานะการส่งมอบสำเร็จ")
                    else:
                        messages.error(request, "❌ กรุณาแนบรูปภาพใบส่งมอบสินค้า (ที่มีลายเซ็นลูกค้า) ก่อนปิดงาน!")
                        return redirect('logistics_board')
                else:
                    order.delivery_status_id = delivery_status_id
                    messages.success(request, f"📦 อัปเดตสถานะการจัดส่ง {order.code} เรียบร้อยแล้ว!")
        order.save()
    return redirect('logistics_board')

@login_required
def create_logistics_claim(request):
    if request.method == 'POST':
        job_ids = request.POST.getlist('job_ids')
        if job_ids:
            jobs = ProductionOrder.objects.filter(id__in=job_ids, logistics_claim__isnull=True)
            if jobs.exists():
                transporter = jobs.first().transporter
                total_amt = sum([j.delivery_fee for j in jobs])
                claim = LogisticsClaim.objects.create(transporter=transporter, total_jobs=jobs.count(), total_amount=total_amt)
                jobs.update(logistics_claim=claim)
                messages.success(request, f"💰 สร้างใบตั้งเบิกค่ารถ {claim.code} สำเร็จ!")
            else: messages.error(request, "❌ ไม่พบงาน หรือมีการตั้งเบิกไปแล้ว")
        else: messages.warning(request, "⚠️ กรุณาติ๊กเลือกอย่างน้อย 1 งาน")
    return redirect('logistics_claim_history') 

@login_required
def print_delivery_note(request, pk):
    order = get_object_or_404(ProductionOrder, pk=pk)
    company = CompanyInfo.objects.first()

    amount_text = ""
    if order.quotation_ref and order.quotation_ref.grand_total:
        amount_text = get_thai_baht_text(order.quotation_ref.grand_total)

    return render(request, 'manufacturing/print_delivery_note.html', {
        'order': order,
        'company': company,
        'amount_text': amount_text 
    })

@login_required
def print_logistics_claim(request, pk):
    claim = get_object_or_404(LogisticsClaim, pk=pk)
    company = CompanyInfo.objects.first()
    jobs = claim.production_orders.all()
    amount_text = get_thai_baht_text(claim.total_amount)
    return render(request, 'manufacturing/print_logistics_claim.html', {'claim': claim, 'jobs': jobs, 'company': company, 'amount_text': amount_text})

@login_required
def logistics_claim_history(request):
    claims = LogisticsClaim.objects.select_related('transporter').prefetch_related('production_orders', 'production_orders__quotation_ref').all().order_by('-created_at')

    start_date = request.GET.get('start_date', '')
    end_date = request.GET.get('end_date', '')
    q_transporter = request.GET.get('q_transporter', '')
    q_job = request.GET.get('q_job', '')
    q_customer = request.GET.get('q_customer', '')

    if start_date: claims = claims.filter(created_at__date__gte=start_date)
    if end_date: claims = claims.filter(created_at__date__lte=end_date)
    if q_transporter: claims = claims.filter(Q(transporter__name__icontains=q_transporter) | Q(transporter__driver_name__icontains=q_transporter))
    if q_job: claims = claims.filter(production_orders__code__icontains=q_job).distinct()
    if q_customer: claims = claims.filter(production_orders__customer_name__icontains=q_customer).distinct()

    paginator = Paginator(claims, 20)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'manufacturing/logistics_claim_history.html', {
        'page_obj': page_obj, 'start_date': start_date, 'end_date': end_date,
        'q_transporter': q_transporter, 'q_job': q_job, 'q_customer': q_customer
    })

@login_required
def ajax_add_transporter_full(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        driver_name = request.POST.get('driver_name', '')
        vehicle_plate = request.POST.get('vehicle_plate', '')
        address = request.POST.get('address', '')
        bank_account = request.POST.get('bank_account', '')
        id_card_image = request.FILES.get('id_card_image')

        if name:
            obj, created = Transporter.objects.get_or_create(name=name, defaults={
                'driver_name': driver_name, 'vehicle_plate': vehicle_plate,
                'address': address, 'bank_account': bank_account, 'id_card_image': id_card_image
            })
            return JsonResponse({'success': True, 'id': obj.id, 'name': obj.name})
    return JsonResponse({'success': False})

@login_required
@transaction.atomic
def pay_logistics_claim(request, claim_id):
    claim = get_object_or_404(LogisticsClaim, pk=claim_id)

    if request.method == 'POST' and claim.status == 'PENDING':
        claim.status = 'PAID'
        claim.save()

        Expense.objects.create(
            title=f"จ่ายค่าขนส่ง/ทีมรถ (ใบเบิก: {claim.code}) - {claim.transporter.name}",
            amount=claim.total_amount,
            date=timezone.now().date(),
        )

        messages.success(request, f"✅ ทำจ่ายเงินใบเบิก {claim.code} จำนวน ฿{claim.total_amount:,.2f} สำเร็จ! และระบบบันทึกลงบัญชีรายจ่ายให้อัตโนมัติแล้วค่ะ")

    return redirect('logistics_claim_history')

@login_required
@transaction.atomic
def pay_blueprint_claim(request, claim_id):
    claim = get_object_or_404(BlueprintClaim, pk=claim_id)

    if request.method == 'POST' and claim.status == 'PENDING':
        claim.status = 'PAID'
        claim.save()

        emp_name = claim.employee.first_name if claim.employee else 'ไม่ระบุ'
        Expense.objects.create(
            title=f"จ่ายค่าแบบแปลน/ทีมช่าง (ใบเบิก: {claim.code}) - {emp_name}",
            amount=claim.total_amount,
            date=timezone.now().date(),
        )

        messages.success(request, f"✅ ทำจ่ายเงินใบเบิก {claim.code} จำนวน ฿{claim.total_amount:,.2f} สำเร็จ! และระบบบันทึกลงบัญชีรายจ่ายให้อัตโนมัติแล้วค่ะ")

    return redirect('blueprint_hub')

@login_required
def update_bom_labor_cost(request, pk):
    if request.method == 'POST':
        bom = get_object_or_404(BOM, pk=pk)
        try:
            labor_val = request.POST.get('labor_cost', '0').replace(',', '')
            bom.labor_cost = Decimal(labor_val)
            bom.save()
            messages.success(request, f"✅ บันทึกค่าแรงประกอบสำหรับ {bom.product.code} เรียบร้อยแล้ว")
        except (ValueError, InvalidOperation):
            messages.error(request, "❌ เกิดข้อผิดพลาดในการบันทึกตัวเลขค่าแรงประกอบ")
    return redirect('bom_list')

@login_required
def bom_list(request):
    boms = BOM.objects.select_related('product').annotate(
        item_count=Count('items', distinct=True),
        total_rm_cost=Coalesce(
            Sum(F('items__quantity') * F('items__raw_material__cost_price')),
            0,
            output_field=DecimalField(max_digits=12, decimal_places=2)
        )
    ).annotate(
        estimated_profit=ExpressionWrapper(
            F('product__sell_price') - (F('total_rm_cost') + F('labor_cost')),
            output_field=DecimalField(max_digits=12, decimal_places=2)
        )
    ).order_by('-id')

    return render(request, 'manufacturing/bom_list.html', {'boms': boms})