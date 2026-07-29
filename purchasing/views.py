import json
import datetime
import openpyxl
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Q, Sum, Count, Max
from django.core.paginator import Paginator
from django.utils.dateparse import parse_date
from django.utils import timezone
from django.forms.models import inlineformset_factory

# จัดบรรทัดใหม่ป้องกัน AI แทรกป้ายกำกับ
from .models import (
    PurchaseOrder, PurchaseOrderItem, PurchaseOrderPayment,
    PurchasePreparation, OverseasPO, OverseasSupplier,
    OverseasDocument, OverseasPOItem
)
from .forms import PurchaseOrderForm, PurchaseOrderItemFormSet, PurchaseOrderItemForm
from master_data.models import CompanyInfo, Supplier
from inventory.models import (
    Product, ProductSupplier, SupplierPriceHistory,
    Category, RawMaterialCategory
)
# 🌟 [NEW] เพิ่มการนำเข้า ProductionOrder เพื่อใช้นับจำนวนงานรอ PPO 🌟
from manufacturing.models import BOM, ProductionOrder 

# ------------------------------------------
# 🛡️ ระบบนายทวาร (Gatekeeper) แบ่งสิทธิ์การทำงาน
# ------------------------------------------
def can_view_and_pay(user):
    if user.is_superuser: return True
    user_groups = list(user.groups.values_list('name', flat=True))
    if 'Purchasing' in user_groups or 'Accounting' in user_groups or 'Executive' in user_groups: return True
    if hasattr(user, 'employee') and user.employee:
        dept = user.employee.department.name if user.employee.department else ''
        if 'จัดซื้อ' in dept or 'Purchasing' in dept or 'บัญชี' in dept or 'Accounting' in dept: return True
    return False

def can_create_po(user):
    if user.is_superuser: return True
    user_groups = list(user.groups.values_list('name', flat=True))
    if 'Purchasing' in user_groups or 'Executive' in user_groups: return True
    if hasattr(user, 'employee') and user.employee:
        dept = user.employee.department.name if user.employee.department else ''
        if 'จัดซื้อ' in dept or 'Purchasing' in dept: return True
    return False

def check_is_approver(user):
    if user.is_superuser: return True
    user_groups = list(user.groups.values_list('name', flat=True))
    if 'Executive' in user_groups: return True
    if hasattr(user, 'employee') and user.employee:
        job_title = user.employee.position.title.lower() if user.employee.position else ""
        rank = user.employee.business_rank.lower() if user.employee.business_rank else ""
        if 'manager' in job_title or 'ผู้จัดการ' in job_title or 'director' in job_title or 'ผู้อำนวยการ' in job_title: return True
        if rank in ['manager', 'director', 'executive']: return True
    return False

# ------------------------------------------
# 🛒 ระบบจัดซื้อ (Purchasing)
# ------------------------------------------
@login_required
def purchasing_dashboard(request):
    if not can_view_and_pay(request.user):
        messages.error(request, "❌ บัญชีของคุณไม่มีสิทธิ์เข้าถึงระบบจัดซื้อ")
        return redirect('dashboard')

    pos = PurchaseOrder.objects.all()
    draft_count = pos.filter(status='DRAFT').count()
    pending_payment_pos = pos.filter(payment_status__in=['PENDING', 'DEPOSIT'], status='APPROVED')
    pending_payment_count = pending_payment_pos.count()
    pending_payment_amount = pending_payment_pos.aggregate(Sum('total_amount'))['total_amount__sum'] or 0

    deposit_paid = PurchaseOrderPayment.objects.filter(po__in=pending_payment_pos).aggregate(Sum('amount'))['amount__sum'] or 0
    actual_pending_amount = float(pending_payment_amount) - float(deposit_paid)

    pending_receipt_count = pos.filter(receipt_status__in=['PENDING', 'PARTIAL'], status='APPROVED').count()
    recent_pos = pos.order_by('-created_at')[:10]
    is_approver = check_is_approver(request.user)

    # 🌟 [NEW] นับจำนวนใบสั่งผลิต (JOB) ที่รอเปิดใบเตรียม (PPO) 🌟
    pending_ppo_count = ProductionOrder.objects.filter(status='WAITING_MATERIALS', is_materials_ordered=False).count()

    context = {
        'draft_count': draft_count, 'pending_payment_count': pending_payment_count,
        'pending_payment_amount': actual_pending_amount, 'pending_receipt_count': pending_receipt_count,
        'recent_pos': recent_pos, 'is_approver': is_approver,
        'pending_ppo_count': pending_ppo_count, # ส่งยอดไปแสดงเป็น Badge แดงๆ
    }
    return render(request, 'purchasing/purchasing_dashboard.html', context)

@login_required
def po_list(request):
    if not can_view_and_pay(request.user): return redirect('dashboard')

    search_query = request.GET.get('q', '')
    status_filter = request.GET.get('status', '')
    payment_filter = request.GET.get('payment_status', '')

    pos = PurchaseOrder.objects.all().order_by('-created_at')

    if search_query:
        pos = pos.filter(Q(code__icontains=search_query) | Q(supplier__name__icontains=search_query))
    if status_filter:
        pos = pos.filter(status=status_filter)
    if payment_filter:
        pos = pos.filter(payment_status=payment_filter)

    # 🌟 [NEW] ปรับการรับค่าว้นที่ ให้ Default เป็น "ช่วง 7 วันก่อนหน้า" 🌟
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')

    # ถ้าย้งไม่มีการเลือกวันที่ (โหลดหน้าเว็บครั้งแรก) ให้ตั้งค่าเป็นย้อนหลัง 6 วัน (รวมวันนี้ = 7 วัน)
    if not start_date or start_date == 'None':
        start_date = (timezone.now().date() - datetime.timedelta(days=6)).strftime('%Y-%m-%d')
    if not end_date or end_date == 'None':
        end_date = timezone.now().date().strftime('%Y-%m-%d')

    pos = pos.filter(date__gte=start_date, date__lte=end_date)

    context = {
        'pos': pos,
        'search_query': search_query,
        'start_date': start_date,
        'end_date': end_date,
        'status_filter': status_filter,
        'payment_filter': payment_filter
    }
    return render(request, 'purchasing/po_list.html', context)

@login_required
def po_create(request):
    if not can_create_po(request.user): return redirect('purchasing_dashboard')

    ppo_ref = request.GET.get('ppo_ref', '')
    supplier_id = request.GET.get('supplier_id')
    items_json = request.GET.get('items_data', '[]')

    initial_items = []
    if items_json:
        try:
            data = json.loads(items_json)
            for item in data:
                initial_items.append({'product': item['id'], 'quantity': item['qty'], 'unit_cost': item['cost'], 'total_cost': item['total']})
        except: pass

    if request.method == 'POST':
        form = PurchaseOrderForm(request.POST)
        formset = PurchaseOrderItemFormSet(request.POST)

        if form.is_valid() and formset.is_valid():
            po = form.save(commit=False)
            po.status = 'DRAFT'
            now = datetime.datetime.now()
            thai_year = (now.year + 543) % 100
            prefix = f"PO-{thai_year:02d}{now.strftime('%m')}"

            last_po = PurchaseOrder.objects.filter(code__startswith=prefix).aggregate(Max('code'))['code__max']
            seq = int(last_po.split('-')[-1]) + 1 if last_po else 1
            po.code = f"{prefix}-{seq:03d}"
            if ppo_ref: po.ppo_ref = ppo_ref
            po.buyer = getattr(request.user, 'employee', None)
            po.save()

            formset.instance = po
            formset.save()

            total = sum(item.total_cost for item in po.items.all() if item.total_cost)
            po.total_amount = total
            po.save()

            messages.success(request, f"✅ สร้างใบสั่งซื้อ {po.code} เรียบร้อยแล้ว")
            if ppo_ref:
                try:
                    ppo_obj = PurchasePreparation.objects.get(code=ppo_ref)
                    return redirect('ppo_detail', pk=ppo_obj.id)
                except PurchasePreparation.DoesNotExist:
                    return redirect('po_list')
            else: return redirect('po_list')
        else: messages.error(request, "❌ กรุณาตรวจสอบข้อมูลให้ครบถ้วน")
    else:
        form = PurchaseOrderForm(initial={'status': 'DRAFT', 'supplier': supplier_id if supplier_id else None})
        extra_rows = len(initial_items) if initial_items else 1
        PurchaseOrderItemFormSetDynamic = inlineformset_factory(PurchaseOrder, PurchaseOrderItem, form=PurchaseOrderItemForm, extra=extra_rows, can_delete=True)
        formset = PurchaseOrderItemFormSetDynamic(initial=initial_items if initial_items else None)

    fg_products = Product.objects.filter(product_type='FG', is_active=True)
    return render(request, 'purchasing/po_create.html', {'form': form, 'formset': formset, 'ppo_ref': ppo_ref, 'fg_products': fg_products})

@login_required
def po_print(request, po_id):
    po = get_object_or_404(PurchaseOrder, id=po_id)
    company = CompanyInfo.objects.first()
    return render(request, 'purchasing/po_print.html', {'po': po, 'company': company})

@login_required
def po_edit(request, po_id):
    if not can_create_po(request.user): return redirect('purchasing_dashboard')
    po = get_object_or_404(PurchaseOrder, id=po_id)
    fg_products = Product.objects.filter(product_type='FG', is_active=True)
    is_approver = check_is_approver(request.user)

    PurchaseOrderItemFormSetEdit = inlineformset_factory(PurchaseOrder, PurchaseOrderItem, form=PurchaseOrderItemForm, extra=1 if not po.items.exists() else 0, can_delete=True)

    if request.method == 'POST':
        form = PurchaseOrderForm(request.POST, instance=po)
        formset = PurchaseOrderItemFormSetEdit(request.POST, instance=po)

        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()

            total = sum(item.total_cost for item in po.items.all() if item.total_cost)
            po.total_amount = total
            po.save()

            messages.success(request, f"✅ แก้ไขและบันทึกใบสั่งซื้อ {po.code} เรียบร้อยแล้ว!")
            if po.ppo_ref:
                try: return redirect('ppo_detail', pk=PurchasePreparation.objects.get(code=po.ppo_ref).id)
                except: return redirect('po_list')
            else: return redirect('po_list')
        else: messages.error(request, "❌ กรุณาตรวจสอบข้อมูลให้ครบถ้วน")
    else:
        form = PurchaseOrderForm(instance=po)
        formset = PurchaseOrderItemFormSetEdit(instance=po)

    return render(request, 'purchasing/po_create.html', {'form': form, 'formset': formset, 'po': po, 'fg_products': fg_products, 'is_approver': is_approver})

@login_required
def po_payment(request, po_id):
    if not can_view_and_pay(request.user):
        messages.error(request, "❌ คุณไม่มีสิทธิ์เข้าถึงหน้าระบบจ่ายเงิน")
        return redirect('dashboard')

    po = get_object_or_404(PurchaseOrder, id=po_id)
    payments = po.payments.all().order_by('-created_at')
    total_paid = payments.aggregate(Sum('amount'))['amount__sum'] or 0
    balance = float(po.total_amount) - float(total_paid)

    if request.method == 'POST':
        amount_str = request.POST.get('amount', '0').replace(',', '')
        try: amount = float(amount_str)
        except ValueError: amount = 0

        if amount > 0 and amount <= balance:
            payment_record = PurchaseOrderPayment(
                po=po,
                payment_date=request.POST.get('payment_date', timezone.now().date()),
                amount=amount,
                payment_method=request.POST.get('payment_method', 'โอนเงินผ่านธนาคาร'),
                reference_no=request.POST.get('reference_no', ''),
                note=request.POST.get('note', '')
            )
            if 'slip_image' in request.FILES:
                 payment_record.slip_image = request.FILES['slip_image']

            payment_record.save()

            new_total_paid = float(total_paid) + float(amount)
            if new_total_paid >= float(po.total_amount): po.payment_status = 'PAID'
            else: po.payment_status = 'DEPOSIT'
            po.save()

            messages.success(request, f"✅ บันทึกชำระเงิน {amount:,.2f} บาท พร้อมแนบหลักฐานสำเร็จ!")
            return redirect('po_payment', po_id=po.id)
        else:
            messages.error(request, "❌ จำนวนเงินไม่ถูกต้อง หรือเกินยอดคงค้าง")

    return render(request, 'purchasing/po_payment.html', {'po': po, 'payments': payments, 'total_paid': total_paid, 'balance': balance})

@login_required
def ppo_list(request):
    if not can_view_and_pay(request.user): return redirect('dashboard')

    ppos = PurchasePreparation.objects.all().order_by('-id')
    for ppo in ppos:
        total_amount = Decimal(0)
        total_needed_qty = Decimal(0)

        mat_needed = {}
        for job in ppo.production_orders.all():
            bom = BOM.objects.filter(product=job.product).first()
            if bom:
                for item in bom.items.all():
                    mat_id = item.raw_material.id
                    if mat_id not in mat_needed: mat_needed[mat_id] = Decimal(0)
                    mat_needed[mat_id] += Decimal(str(item.quantity))
                    total_amount += Decimal(str(item.quantity)) * Decimal(str(item.raw_material.cost_price))
                    total_needed_qty += Decimal(str(item.quantity))

        ordered_qty = Decimal(0)
        created_pos = PurchaseOrder.objects.filter(ppo_ref=ppo.code).exclude(status='CANCELLED')
        for po in created_pos:
            for po_item in po.items.all():
                if po_item.product_id in mat_needed:
                     ordered_qty += Decimal(str(po_item.quantity))

        ppo.total_estimated_cost = total_amount
        ppo.progress_percent = int((ordered_qty / total_needed_qty * 100)) if total_needed_qty > 0 else 0
        if ppo.progress_percent > 100: ppo.progress_percent = 100

        if total_needed_qty == 0: ppo.po_status = 'EMPTY'
        elif ordered_qty == 0: ppo.po_status = 'RED'
        elif ppo.progress_percent >= 100: ppo.po_status = 'GREEN'
        else: ppo.po_status = 'ORANGE'

    return render(request, 'purchasing/ppo_list.html', {'ppos': ppos})

@login_required
def ppo_detail(request, pk):
    if not can_view_and_pay(request.user): return redirect('dashboard')
    ppo = get_object_or_404(PurchasePreparation, pk=pk)

    if request.method == 'POST':
        if not can_create_po(request.user):
            messages.error(request, "❌ คุณไม่มีสิทธิ์สร้างใบสั่งซื้อ")
            return redirect('ppo_detail', pk=pk)

        order_data_json = request.POST.get('order_data', '{}')
        try: order_data = json.loads(order_data_json)
        except:
            messages.error(request, "❌ ข้อมูล JSON ไม่ถูกต้อง")
            return redirect('ppo_detail', pk=pk)

        created_po_codes = []
        for sup_id, items in order_data.items():
             if not items: continue
             supplier = Supplier.objects.filter(id=sup_id).first()
             if not supplier: continue

             now = datetime.datetime.now()
             thai_year = (now.year + 543) % 100
             prefix = f"PO-{thai_year:02d}{now.strftime('%m')}"
             last_po = PurchaseOrder.objects.filter(code__startswith=prefix).aggregate(Max('code'))['code__max']
             seq = int(last_po.split('-')[-1]) + 1 if last_po else 1
             po_code = f"{prefix}-{seq:03d}"

             po = PurchaseOrder.objects.create(code=po_code, supplier=supplier, buyer=getattr(request.user, 'employee', None), ppo_ref=ppo.code, status='DRAFT', total_amount=0)

             total_amount = Decimal('0.00')
             for item in items:
                 prod = Product.objects.filter(id=item['id']).first()
                 if prod:
                     qty = Decimal(str(item['qty']))
                     cost = Decimal(str(item['cost']))
                     line_total = qty * cost
                     PurchaseOrderItem.objects.create(po=po, product=prod, quantity=qty, unit_cost=cost, total_cost=line_total)
                     total_amount += line_total

             po.total_amount = total_amount
             po.save()
             created_po_codes.append(po.code)

        if created_po_codes: messages.success(request, f"✅ สร้างใบสั่งซื้อ (PO) สำเร็จ: {', '.join(created_po_codes)}")
        else: messages.warning(request, "⚠️ ไม่มีการสร้างใบสั่งซื้อใหม่")
        return redirect('ppo_detail', pk=pk)

    material_reqs = {}
    for job in ppo.production_orders.all():
        bom = BOM.objects.filter(product=job.product).first()
        if bom:
            for item in bom.items.all():
                mat_id = item.raw_material.id
                if mat_id not in material_reqs: material_reqs[mat_id] = {'product': item.raw_material, 'needed': Decimal(0), 'ordered': Decimal(0)}
                material_reqs[mat_id]['needed'] += Decimal(str(item.quantity))

    created_pos = PurchaseOrder.objects.filter(ppo_ref=ppo.code).exclude(status='CANCELLED')
    for po in created_pos:
        for po_item in po.items.all():
            if po_item.product_id in material_reqs:
                 material_reqs[po_item.product_id]['ordered'] += Decimal(str(po_item.quantity))

    materials_list = []
    grand_total = Decimal(0)
    all_suppliers = list(Supplier.objects.all().values('id', 'name'))

    for mat_id, data in material_reqs.items():
        mat = data['product']
        needed = float(data['needed'])
        ordered = float(data['ordered'])
        remaining = needed - ordered if needed - ordered > 0 else 0

        suppliers = []
        if hasattr(mat, 'multi_suppliers') and mat.multi_suppliers.exists():
            for ps in mat.multi_suppliers.all():
                suppliers.append({'id': ps.supplier.id, 'name': ps.supplier.name, 'cost': float(ps.cost_price), 'is_default': ps.is_default})
        elif mat.supplier:
            suppliers.append({'id': mat.supplier.id, 'name': mat.supplier.name, 'cost': float(mat.cost_price), 'is_default': True})

        materials_list.append({
             'id': mat.id, 'code': mat.code, 'name': mat.name, 'needed': needed, 'ordered': ordered,
             'remaining': remaining, 'cost': float(mat.cost_price), 'suppliers': suppliers
        })
        grand_total += Decimal(str(needed)) * Decimal(str(mat.cost_price))

    all_suppliers_json = json.dumps(all_suppliers)
    return render(request, 'purchasing/ppo_detail.html', {'ppo': ppo, 'materials_list': materials_list, 'grand_total': grand_total, 'all_suppliers_json': all_suppliers_json, 'all_suppliers': all_suppliers, 'created_pos': created_pos})

@login_required
def po_approve(request, po_id):
    po = get_object_or_404(PurchaseOrder, id=po_id)
    is_approver = check_is_approver(request.user)
    if is_approver and po.status == 'DRAFT':
        po.status = 'APPROVED'
        po.save()
        messages.success(request, f"✅ อนุมัติใบสั่งซื้อ {po.code} เรียบร้อยแล้ว")
    else: messages.error(request, "❌ คุณไม่มีสิทธิ์อนุมัติ หรือสถานะเอกสารไม่ถูกต้อง")
    return redirect('po_list')

@login_required
def po_cancel(request, po_id):
    po = get_object_or_404(PurchaseOrder, id=po_id)
    is_approver = check_is_approver(request.user)
    if is_approver and po.status == 'DRAFT':
         po.status = 'CANCELLED'
         po.save()
         messages.warning(request, f"⚠️ ยกเลิกใบสั่งซื้อ {po.code} เรียบร้อยแล้ว")
    else: messages.error(request, "❌ คุณไม่มีสิทธิ์ยกเลิก หรือสถานะเอกสารไม่ถูกต้อง")
    return redirect('po_list')

# ------------------------------------------
# 🌟 ระบบติดตามสินค้านำเข้า (Overseas PO Tracker)
# ------------------------------------------
@login_required
def overseas_po_list(request):
    if not can_view_and_pay(request.user): return redirect('purchasing_dashboard')

    query = request.GET.get('q', '')
    status_filter = request.GET.get('status', '')
    start_date = request.GET.get('start_date', '')

    overseas_pos = OverseasPO.objects.all().order_by('-id').prefetch_related('documents', 'overseas_items')

    if query:
        overseas_pos = overseas_pos.filter(
            Q(po_number__icontains=query) | Q(supplier__name__icontains=query) | Q(supplier_name__icontains=query) |
            Q(pi_number__icontains=query) |
            Q(overseas_items__description__icontains=query)
        ).distinct()

    if status_filter:
        overseas_pos = overseas_pos.filter(status=status_filter)
    if start_date:
        overseas_pos = overseas_pos.filter(po_date__gte=start_date)

    for po in overseas_pos:
        all_docs = list(po.documents.all())
        po.docs = {
            'PI': [d for d in all_docs if d.doc_type == 'PI'],
            'FE': [d for d in all_docs if d.doc_type == 'FE'],
            'BL': [d for d in all_docs if d.doc_type == 'BL'],
            'PL': [d for d in all_docs if d.doc_type == 'PL'],
            'CI': [d for d in all_docs if d.doc_type == 'CI'],
            'CUSTOMS': [d for d in all_docs if d.doc_type == 'CUSTOMS'],
        }

    suppliers = OverseasSupplier.objects.all().order_by('name')

    products = Product.objects.filter(is_active=True).exclude(product_type='WIP')
    prod_list = []
    for p in products:
        cat_name = p.category.name if p.category else (p.rm_category.name if p.rm_category else "อื่นๆ")

        prod_list.append({
            'id': p.id,
            'name': f"[{p.code}] {p.name}",
            'img_url': p.image.url if p.image else '',
            'type': p.product_type,
            'category': cat_name
        })
    products_json = json.dumps(prod_list)

    return render(request, 'purchasing/overseas_po_list.html', {
        'overseas_pos': overseas_pos,
        'query': query,
        'status_filter': status_filter,
        'start_date': start_date,
        'suppliers': suppliers,
        'products_json': products_json
    })

@login_required
def overseas_po_save(request):
    if not can_create_po(request.user): return redirect('overseas_po_list')
    if request.method == 'POST':
        po_id = request.POST.get('po_id')

        supplier_id = request.POST.get('supplier_id')
        new_supplier_name = request.POST.get('new_supplier_name')
        supplier_obj = None

        if supplier_id:
            supplier_obj = OverseasSupplier.objects.get(id=supplier_id)
        elif new_supplier_name:
            supplier_obj, _ = OverseasSupplier.objects.get_or_create(name=new_supplier_name)

        po = get_object_or_404(OverseasPO, id=po_id) if po_id else OverseasPO()

        po.supplier = supplier_obj

        po.pi_number = request.POST.get('pi_number', '')
        po.ship_to_port = request.POST.get('ship_to_port', '')

        po.po_date = request.POST.get('po_date') or timezone.now().date()
        po.eta_date = request.POST.get('eta_date') or None
        po.item_description = request.POST.get('item_description', '')
        po.status = request.POST.get('status', 'PENDING')

        t_amt = request.POST.get('total_amount', '').replace(',', '').strip()
        po.total_amount = Decimal(t_amt) if t_amt else Decimal('0')

        po.deposit_date = request.POST.get('deposit_date') or None
        d_amt = request.POST.get('deposit_amount', '').replace(',', '').strip()
        po.deposit_amount = Decimal(d_amt) if d_amt else Decimal('0')

        po.balance_date = request.POST.get('balance_date') or None
        b_amt = request.POST.get('balance_amount', '').replace(',', '').strip()
        po.balance_amount = Decimal(b_amt) if b_amt else Decimal('0')

        po.save()

        item_ids = request.POST.getlist('item_id[]')
        item_descs = request.POST.getlist('item_desc[]')
        item_qtys = request.POST.getlist('item_qty[]')
        item_prices = request.POST.getlist('item_price[]')
        item_product_ids = request.POST.getlist('item_product_id[]')

        kept_item_ids = []
        for i in range(len(item_descs)):
            desc = item_descs[i]
            if not desc.strip(): continue

            qty_str = str(item_qtys[i]).replace(',', '').strip() if i < len(item_qtys) else ''
            qty = Decimal(qty_str) if qty_str else Decimal('1')

            price_str = str(item_prices[i]).replace(',', '').strip() if i < len(item_prices) else ''
            price = Decimal(price_str) if price_str else Decimal('0')

            total = qty * price

            i_id = item_ids[i] if i < len(item_ids) else ""

            prod_id_val = item_product_ids[i] if i < len(item_product_ids) else ""
            linked_product = None
            if prod_id_val:
                linked_product = Product.objects.filter(id=prod_id_val).first()

            if i_id:
                item = OverseasPOItem.objects.filter(id=i_id, po=po).first()
                if item:
                    item.description = desc
                    item.quantity = qty
                    item.unit_price = price
                    item.total_price = total
                    item.product = linked_product
                    if f'item_image_{i}' in request.FILES:
                        item.image = request.FILES[f'item_image_{i}']
                    item.save()
                    kept_item_ids.append(item.id)
            else:
                item = OverseasPOItem.objects.create(
                    po=po, description=desc, quantity=qty, unit_price=price, total_price=total
                )
                item.product = linked_product
                if f'item_image_{i}' in request.FILES:
                    item.image = request.FILES[f'item_image_{i}']
                item.save()
                kept_item_ids.append(item.id)

        po.overseas_items.exclude(id__in=kept_item_ids).delete()

        doc_types = ['pi', 'fe', 'bl', 'pl', 'ci', 'customs']
        for dtype in doc_types:
            files = request.FILES.getlist(f'doc_{dtype}')
            for f in files:
                OverseasDocument.objects.create(
                    po=po,
                    doc_type=dtype.upper(),
                    file=f
                )

        messages.success(request, f"✅ บันทึกรายการเอกสาร PQ สำเร็จแล้ว")

    return redirect('overseas_po_list')

@login_required
def request_overseas_payment(request, po_id, payment_type):
    if not can_create_po(request.user): return redirect('overseas_po_list')
    po = get_object_or_404(OverseasPO, id=po_id)

    if payment_type == 'deposit':
        po.is_deposit_requested = True
        messages.success(request, f"📤 ส่งเรื่องขอเบิก 'มัดจำ' สำหรับเอกสาร: {po.po_number or po.pi_number} เรียบร้อยแล้ว")
    elif payment_type == 'balance':
        po.is_balance_requested = True
        messages.success(request, f"📤 ส่งเรื่องขอเบิก 'ส่วนที่เหลือ' สำหรับเอกสาร: {po.po_number or po.pi_number} เรียบร้อยแล้ว")

    po.save()
    return redirect('overseas_po_list')

@login_required
def overseas_po_delete(request, pk):
    if not can_create_po(request.user): return redirect('overseas_po_list')
    po = get_object_or_404(OverseasPO, pk=pk)
    po.delete()
    messages.success(request, "🗑️ ลบรายการสั่งซื้อต่างประเทศเรียบร้อยแล้ว")
    return redirect('overseas_po_list')

@login_required
def overseas_po_print(request, po_id):
    if not can_view_and_pay(request.user): return redirect('overseas_po_list')
    po = get_object_or_404(OverseasPO, id=po_id)
    company = CompanyInfo.objects.first()

    return render(request, 'purchasing/overseas_po_print.html', {
        'po': po,
        'company': company
    })

# ------------------------------------------
# 🌟 ระบบทำเนียบร้านค้าต่างประเทศ
# ------------------------------------------
@login_required
def overseas_supplier_list(request):
    if not can_view_and_pay(request.user): return redirect('dashboard')
    suppliers = OverseasSupplier.objects.all().order_by('-id')
    return render(request, 'purchasing/overseas_supplier_list.html', {'suppliers': suppliers})

@login_required
def overseas_supplier_save(request):
    if not can_create_po(request.user): return redirect('overseas_supplier_list')
    if request.method == 'POST':
        sup_id = request.POST.get('supplier_id')
        sup = get_object_or_404(OverseasSupplier, id=sup_id) if sup_id else OverseasSupplier()
        sup.name = request.POST.get('name')
        sup.country = request.POST.get('country', '')
        sup.contact_name = request.POST.get('contact_name', '')
        sup.phone = request.POST.get('phone', '')
        sup.email = request.POST.get('email', '')
        sup.note = request.POST.get('note', '')
        sup.save()
        messages.success(request, f"✅ บันทึกข้อมูลร้านค้า {sup.name} สำเร็จ")
    return redirect('overseas_supplier_list')

@login_required
def overseas_supplier_delete(request, pk):
    if not can_create_po(request.user): return redirect('overseas_supplier_list')
    sup = get_object_or_404(OverseasSupplier, pk=pk)
    sup.delete()
    messages.success(request, "🗑️ ลบข้อมูลร้านค้าต่างประเทศเรียบร้อยแล้ว")
    return redirect('overseas_supplier_list')


# ------------------------------------------
# 🌟 ทำเนียบซัพพลายเออร์ในประเทศ
# ------------------------------------------
@login_required
def supplier_list(request):
    if not can_view_and_pay(request.user): return redirect('dashboard')

    query = request.GET.get('q', '')
    category_id = request.GET.get('category', '')
    rm_category_id = request.GET.get('rm_category', '')

    suppliers = Supplier.objects.all().order_by('-id')

    if query:
        suppliers = suppliers.filter(
            Q(code__icontains=query) | Q(name__icontains=query) |
            Q(contact_name__icontains=query) | Q(phone__icontains=query)
        )

    if category_id:
        suppliers = suppliers.filter(supplied_products__product__category_id=category_id).distinct()

    if rm_category_id:
        suppliers = suppliers.filter(supplied_products__product__rm_category_id=rm_category_id).distinct()

    categories = Category.objects.all().order_by('name')
    rm_categories = RawMaterialCategory.objects.all().order_by('name')

    context = {
        'suppliers': suppliers, 'query': query,
        'categories': categories, 'rm_categories': rm_categories,
        'selected_cat': category_id, 'selected_rm_cat': rm_category_id
    }

    return render(request, 'purchasing/supplier_list.html', context)

@login_required
def supplier_detail(request, pk):
    if not can_view_and_pay(request.user): return redirect('dashboard')
    supplier = get_object_or_404(Supplier, pk=pk)

    supplied_products = ProductSupplier.objects.filter(supplier=supplier).select_related('product')
    price_history = SupplierPriceHistory.objects.filter(supplier=supplier).order_by('-updated_at')

    return render(request, 'purchasing/supplier_detail.html', {
        'supplier': supplier,
        'supplied_products': supplied_products,
        'price_history': price_history
    })