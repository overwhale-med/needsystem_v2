from django import forms
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import models, transaction
from django.db.models import Sum, Q, F, Subquery, OuterRef, IntegerField, Case, When
from django.db.models.functions import Coalesce
from django.utils.dateparse import parse_date
from django.http import JsonResponse
from django.urls import reverse
import json
from decimal import Decimal, InvalidOperation
import pandas as pd
import math

from .models import (
    Product, StockMovement, InventoryDoc, ProductSupplier,
    SupplierPriceHistory, Category, RawMaterialCategory, Supplier, SubCategory
)
from .forms import StockInForm, StockOutForm, ProductForm, ProductSupplierFormSet
from master_data.models import CompanyInfo
from purchasing.models import PurchaseOrder, PurchaseOrderItem, OverseasPO, OverseasPOItem
# 🌟 [NEW] นำเข้าโมเดล QCReceiptDoc จากแอปผลิต
from manufacturing.models import QCReceiptDoc, ProductionOrder
from django.core.paginator import Paginator

# ==========================================
# 1. Dashboard & Lists
# ==========================================
@login_required
def inventory_dashboard(request):
    fg_qs = Product.objects.filter(is_active=True, product_type='FG')
    rm_qs = Product.objects.filter(is_active=True, product_type='RM')
    all_products = Product.objects.filter(is_active=True)
    low_stock_count = all_products.filter(stock_qty__lte=models.F('min_level')).count()
    pending_po_count = PurchaseOrder.objects.filter(status='APPROVED', receipt_status__in=['PENDING', 'PARTIAL']).count()
    pending_pq_count = OverseasPO.objects.filter(status__in=['FULLY_PAID', 'DEPOSITED']).count()
    fg_products = fg_qs.order_by('code')[:5]
    rm_products = rm_qs.order_by('code')[:5]
    recent_docs = InventoryDoc.objects.all().order_by('-doc_no')[:10]
    return render(request, 'inventory/dashboard.html', {
        'fg_products': fg_products, 'rm_products': rm_products,
        'fg_count': fg_qs.count(), 'rm_count': rm_qs.count(),
        'low_stock_count': low_stock_count, 'recent_docs': recent_docs,
        'pending_po_count': pending_po_count, 'pending_pq_count': pending_pq_count
    })

@login_required
def product_list(request):
    p_type = request.GET.get('type', 'FG')
    search_query = request.GET.get('q', '')
    rm_category_id = request.GET.get('rm_category', '')
    stock_status = request.GET.get('stock_status', '')
    stock_column = request.GET.get('stock_column', '')

    # 🌟 1. ดึงยอด "รอจัดส่ง" (Pending Delivery)
    # หมายถึง: สินค้าที่มี JOB คลุม + มีใบเสนอราคา + เปิดบิลแล้ว (มี Invoice) + Invoice สถานะชำระแล้ว (PAID) + แต่ช่างยังไม่กดส่งมอบสำเร็จ (สถานะไม่ใช่ COMPLETED หรือ DISPATCH)
    pending_delivery_subquery = ProductionOrder.objects.filter(
        product=OuterRef('pk'),
        is_qc_passed=True,
        quotation_ref__invoice__isnull=False,  # เปิดบิลแล้ว
        quotation_ref__invoice__status='PAID', # ชำระเงินครบแล้ว
    ).exclude(
        delivery_status__name__in=['ส่งมอบสำเร็จ', 'ลูกค้าเซ็นรับแล้ว', 'จัดส่งเรียบร้อย'] # ยังไม่ส่ง
    ).values('product').annotate(
        total_delivery=Sum('quantity')
    ).values('total_delivery')

    # 🌟 2. ดึงยอด "รอเปิดบิล" (Pending Invoice)
    # หมายถึง: สินค้าที่มี JOB คลุม + มีใบเสนอราคา + รับมัดจำแล้ว + แต่เซลส์ยังไม่ได้กดเปิดบิล (Invoice ว่างเปล่า)
    pending_invoice_subquery = ProductionOrder.objects.filter(
        product=OuterRef('pk'),
        is_qc_passed=True,
        quotation_ref__is_deposit_paid=True,
        quotation_ref__status='APPROVED',
        quotation_ref__invoice__isnull=True    # ยังไม่เปิดบิล
    ).values('product').annotate(
        total_pending=Sum('quantity')
    ).values('total_pending')

    # 🌟 [FIXED] อัปเดตสมการหลัก (Annotate) เข้าไปใน Products
    products = Product.objects.filter(is_active=True, product_type=p_type).annotate(
        # คำนวณค่าย่อย
        base_pending_inv=Coalesce(Subquery(pending_invoice_subquery, output_field=IntegerField()), 0),
        base_pending_del=Coalesce(Subquery(pending_delivery_subquery, output_field=IntegerField()), 0),
    ).annotate(
        # คอลัมน์ 1: "รอจัดส่ง"
        pending_delivery_qty=Case(
            When(code__contains='-JOB', then=F('base_pending_del')),
            default=0,
            output_field=IntegerField()
        ),
        # คอลัมน์ 2: "รอเปิดบิล" (เฉพาะสินค้ามี -JOB ที่ยอดรอส่งเป็น 0)
        pending_invoice_qty=Case(
            When(code__contains='-JOB', base_pending_del=0, then=F('base_pending_inv')),
            default=0,
            output_field=IntegerField()
        )
    ).annotate(
        # คอลัมน์ 3: "พร้อมขาย" (ถ้าเป็น -JOB และมียอดในรอเปิดบิล/รอส่งแล้ว ให้พร้อมขายเป็น 0, ถ้าเป็น -JOB ลอยๆ ที่ไม่มีใบเสนอราคา ให้เอาสต็อกมาโชว์พร้อมขาย)
        available_qty=Case(
            When(code__contains='-JOB', pending_invoice_qty__gt=0, then=0),
            When(code__contains='-JOB', pending_delivery_qty__gt=0, then=0),
            default=F('stock_qty'),
            output_field=IntegerField()
        )
    ).annotate(
        # คอลัมน์ 4: "สินค้าในลาน" (ยอด Physical Stock จริงๆ ที่ยังไม่ถูกตัด GI ออกไป)
        physical_yard_qty=F('stock_qty')
    ).order_by('code')

    # 1. กรองด้วยข้อความ และ แผนก
    if search_query:
        products = products.filter(Q(code__icontains=search_query) | Q(name__icontains=search_query) | Q(category__name__icontains=search_query))
    if rm_category_id:
        products = products.filter(rm_category_id=rm_category_id)

    # 2. กรองด้วยสถานะสินค้า
    if stock_status == 'in_stock':
        products = products.filter(stock_qty__gt=0)
    elif stock_status == 'out_of_stock':
        products = products.filter(stock_qty__lte=0)

    paginator = Paginator(products, 15)
    page_obj = paginator.get_page(request.GET.get('page'))
    # ... (โค้ดส่วนที่เหลือด้านล่างปล่อยไว้เหมือนเดิมครับ) ...
    title = '📦 คลังสินค้าสำเร็จรูป (FG)' if p_type == 'FG' else '🧱 คลังวัตถุดิบ (RM)'

    rm_categories = RawMaterialCategory.objects.all().order_by('name') if p_type == 'RM' else None

    return render(request, 'inventory/product_list.html', {
        'page_obj': page_obj,
        'p_type': p_type,
        'title': title,
        'search_query': search_query,
        'rm_categories': rm_categories,
        'selected_rm_cat': rm_category_id,
        'stock_status': stock_status,
        'stock_column': stock_column # 🌟 ส่งค่ากลับไปให้หน้าจอจำค่าที่เลือกไว้
    })

@login_required
def document_list_in(request): return document_list_base(request, doc_type='GR', title='ประวัติใบรับสินค้า/วัตถุดิบ (Stock In)')

@login_required
def document_list_out(request): return document_list_base(request, doc_type='GI', title='ประวัติใบเบิกสินค้า/วัตถุดิบ (Stock Out)')

def document_list_base(request, doc_type, title):
    search_query = request.GET.get('q', '')
    product_type = request.GET.get('product_type', '')
    date_start = request.GET.get('start', '')
    date_end = request.GET.get('end', '')

    # 1. ดึงข้อมูลใบรับ/เบิก ปกติ (InventoryDoc)
    docs = InventoryDoc.objects.filter(doc_type=doc_type).order_by('-doc_no')
    if product_type: docs = docs.filter(movements__product__product_type=product_type).distinct()
    if date_start: docs = docs.filter(created_at__date__gte=parse_date(date_start))
    if date_end: docs = docs.filter(created_at__date__lte=parse_date(date_end))
    if search_query: docs = docs.filter(Q(doc_no__icontains=search_query) | Q(reference__icontains=search_query) | Q(created_by__first_name__icontains=search_query))

    # 🌟 [NEW] 2. ถ้าเป็นหน้าใบรับของ (GR) ให้ดึงข้อมูลใบรับจาก QC ผลิต (QCReceiptDoc) มาด้วย
    qc_docs = []
    if doc_type == 'GR':
        qc_qs = QCReceiptDoc.objects.all().order_by('-doc_no')
        if date_start: qc_qs = qc_qs.filter(created_at__date__gte=parse_date(date_start))
        if date_end: qc_qs = qc_qs.filter(created_at__date__lte=parse_date(date_end))
        if search_query: qc_qs = qc_qs.filter(Q(doc_no__icontains=search_query) | Q(production_order__code__icontains=search_query) | Q(product__name__icontains=search_query))
        qc_docs = qc_qs

    return render(request, 'inventory/document_list.html', {
        'docs': docs,
        'qc_docs': qc_docs, # 🌟 ส่งข้อมูล QC ไปหน้าจอ
        'title': title,
        'doc_type': doc_type,
        'search_query': search_query,
        'product_type': product_type,
        'date_start': date_start,
        'date_end': date_end
    })

# ==========================================
# 2. CRUD Products
# ==========================================
@login_required
@transaction.atomic
def product_create(request):
    p_type = request.GET.get('type')
    if not p_type: return render(request, 'inventory/product_type_select.html')
    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES)
        formset = ProductSupplierFormSet(request.POST)
        if form.is_valid() and formset.is_valid():
            product = form.save(commit=False)
            product.product_type = p_type
            product.save()
            formset.instance = product
            formset.save()
            for sup in product.multi_suppliers.all():
                SupplierPriceHistory.objects.create(product=product, supplier=sup.supplier, old_price=0, new_price=sup.cost_price, updated_by=request.user)
            messages.success(request, f"✅ สร้าง '{product.name}' เรียบร้อย")
            return redirect(f"{reverse('product_list')}?type={p_type}")
    else:
        form = ProductForm(initial={'product_type': p_type})
        formset = ProductSupplierFormSet()
    return render(request, 'inventory/product_form.html', {'form': form, 'formset': formset, 'title': 'เพิ่มสินค้า', 'p_type': p_type})

@login_required
@transaction.atomic
def product_update(request, pk):
    product = get_object_or_404(Product, pk=pk)
    p_type = product.product_type
    old_prices = {sup.id: sup.cost_price for sup in product.multi_suppliers.all()}
    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES, instance=product)
        formset = ProductSupplierFormSet(request.POST, instance=product)
        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            for sup in product.multi_suppliers.all():
                old_p = old_prices.get(sup.id, 0)
                if old_p != sup.cost_price:
                    SupplierPriceHistory.objects.create(product=product, supplier=sup.supplier, old_price=old_p, new_price=sup.cost_price, updated_by=request.user)
            messages.success(request, f"💾 บันทึกแก้ไข '{product.name}' เรียบร้อย")
            return redirect(f"{reverse('product_list')}?type={p_type}")
    else:
        form = ProductForm(instance=product)
        formset = ProductSupplierFormSet(instance=product)
    return render(request, 'inventory/product_form.html', {'form': form, 'formset': formset, 'title': f'✏️ แก้ไข: {product.name}', 'p_type': p_type})

# ==========================================
# 3. AJAX Adders
# ==========================================
@login_required
def ajax_add_category(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            obj, _ = Category.objects.get_or_create(name=data.get('name'))
            return JsonResponse({'success': True, 'id': obj.id, 'name': obj.name})
        except Exception as e: return JsonResponse({'success': False, 'error': str(e)})
    return JsonResponse({'success': False})

@login_required
def ajax_add_rm_category(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            obj, _ = RawMaterialCategory.objects.get_or_create(name=data.get('name'))
            return JsonResponse({'success': True, 'id': obj.id, 'name': obj.name})
        except Exception as e: return JsonResponse({'success': False, 'error': str(e)})
    return JsonResponse({'success': False})

@login_required
def ajax_add_sub_category(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            obj, _ = SubCategory.objects.get_or_create(name=data.get('name'))
            return JsonResponse({'success': True, 'id': obj.id, 'name': obj.name})
        except Exception as e: return JsonResponse({'success': False, 'error': str(e)})
    return JsonResponse({'success': False})

@login_required
def ajax_add_supplier(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            obj, _ = Supplier.objects.get_or_create(
                name=data.get('name'),
                defaults={
                    'tax_id': data.get('tax_id', ''),
                    'contact_name': data.get('contact_name', ''),
                    'phone': data.get('phone', ''),
                    'email': data.get('email', ''),
                    'address': data.get('address', ''),
                    'credit_term': data.get('credit_term') or 0
                }
            )
            return JsonResponse({'success': True, 'id': obj.id, 'name': obj.name})
        except Exception as e: return JsonResponse({'success': False, 'error': str(e)})
    return JsonResponse({'success': False, 'error': 'Invalid request'})

# ==========================================
# 4. Import & Tools
# ==========================================
@login_required
def inventory_tools(request):
    return render(request, 'inventory/inventory_tools.html', {'title': '🛠 เครื่องมือจัดการคลังสินค้า'})

@login_required
def import_product_images(request):
    if request.method == 'POST':
        excel_file = request.FILES.get('excel_file')
        image_files = request.FILES.getlist('image_files')
        if not excel_file or not image_files:
            messages.error(request, "❌ กรุณาแนบไฟล์ให้ครบถ้วน")
            return redirect('import_product_images')
        try:
            df = pd.read_excel(excel_file)
            uploaded_images = {img.name: img for img in image_files}
            success = 0
            with transaction.atomic():
                for _, row in df.iterrows():
                    product = Product.objects.filter(code=str(row['SKU']).strip()).first()
                    if product and str(row['Filename']).strip() in uploaded_images:
                        product.image = uploaded_images[str(row['Filename']).strip()]
                        product.save()
                        success += 1
            messages.success(request, f"✅ อัปโหลดสำเร็จ {success} รายการ")
        except Exception as e: messages.error(request, f"❌ Error: {e}")
        return redirect('inventory_tools')
    return render(request, 'inventory/import_images.html')

@login_required
def import_rm_excel(request):
    if request.method == 'POST' and request.FILES.get('excel_file'):
        try:
            df = pd.read_excel(request.FILES['excel_file'])
            with transaction.atomic():
                for _, row in df.iterrows():
                    # ดึงข้อมูลจากคอลัมน์ Excel (เช็คกรณีค่าว่างเปล่าด้วย pd.notna)
                    main_cat_name = str(row['Main_Category']).strip() if 'Main_Category' in row and pd.notna(row['Main_Category']) else None
                    rm_cat_name = str(row['RM_Category']).strip() if 'RM_Category' in row and pd.notna(row['RM_Category']) else None
                    sub_cat_name = str(row['Sub_Category']).strip() if 'Sub_Category' in row and pd.notna(row['Sub_Category']) else None
                    sup_name = str(row['Supplier']).strip() if 'Supplier' in row and pd.notna(row['Supplier']) else None

                    # บันทึกหรือดึงค่าหมวดหมู่
                    main_cat = Category.objects.get_or_create(name=main_cat_name)[0] if main_cat_name and main_cat_name != 'nan' else None
                    rm_cat = RawMaterialCategory.objects.get_or_create(name=rm_cat_name)[0] if rm_cat_name and rm_cat_name != 'nan' else None
                    sub_cat = SubCategory.objects.get_or_create(name=sub_cat_name)[0] if sub_cat_name and sub_cat_name != 'nan' else None
                    sup = Supplier.objects.get_or_create(name=sup_name)[0] if sup_name and sup_name != 'nan' else None

                    # บันทึกข้อมูลลงฐานข้อมูล Product
                    Product.objects.update_or_create(
                        code=str(row['Code']).strip(),
                        defaults={
                            'name': str(row['Name']).strip(),
                            'cost_price': row['Cost_Price'] if pd.notna(row['Cost_Price']) else 0,
                            'min_level': row['Min_Level'] if pd.notna(row['Min_Level']) else 0,
                            'product_type': 'RM',
                            'category': main_cat,      # 🌟 เข้าวงกลมแดงช่องที่ 1 (หมวดหมู่สินค้า)
                            'rm_category': rm_cat,     # 🌟 เข้าวงกลมแดงช่องที่ 2 (แผนก)
                            'sub_category': sub_cat,   # 🌟 เข้าวงกลมแดงช่องที่ 3 (หมวดหมู่ย่อย)
                            'supplier': sup            # 🌟 ผูกร้านค้า
                        }
                    )
            messages.success(request, "✅ นำเข้าข้อมูลวัตถุดิบสำเร็จและผูกหมวดหมู่ครบถ้วน!")
            return redirect('product_list')
        except Exception as e:
            messages.error(request, f"❌ Error: {e}")
    return render(request, 'inventory/import_rm.html')

# ==========================================
# 5. Inventory Operations (Stock In/Out/Docs)
# ==========================================
@login_required
def stock_in(request):
    if request.method == 'POST':
        form = StockInForm(request.POST)
        if form.is_valid():
            doc = InventoryDoc.objects.create(doc_type='GR', reference=form.cleaned_data['doc_reference'], description=form.cleaned_data['doc_note'], created_by=request.user)
            move = form.save(commit=False)
            move.doc = doc; move.movement_type = 'IN'; move.created_by = request.user; move.save()
            messages.success(request, f"✅ เปิดใบรับ {doc.doc_no} สำเร็จ!")
            return redirect('inventory_dashboard')
    else: form = StockInForm()
    return render(request, 'inventory/stock_form.html', {'form': form, 'title': '📥 รับสินค้าเข้า', 'btn_color': 'success', 'btn_icon': 'fa-download'})

@login_required
def stock_out(request):
    if request.method == 'POST':
        form = StockOutForm(request.POST)
        if form.is_valid():
            move = form.save(commit=False)
            if move.product.stock_qty >= move.quantity:
                doc = InventoryDoc.objects.create(doc_type='GI', reference=form.cleaned_data['doc_reference'], description=form.cleaned_data['doc_note'], created_by=request.user)
                move.doc = doc; move.movement_type = 'OUT'; move.created_by = request.user; move.save()
                messages.warning(request, f"📤 เปิดใบเบิก {doc.doc_no} สำเร็จ!")
                return redirect('inventory_dashboard')
            else: messages.error(request, f"❌ สต็อกไม่พอ! มีแค่ {move.product.stock_qty} ชิ้น")
    else: form = StockOutForm()
    return render(request, 'inventory/stock_form.html', {'form': form, 'title': '📦 เบิกสินค้าออก', 'btn_color': 'warning', 'btn_icon': 'fa-upload'})

@login_required
def print_barcode(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    return render(request, 'inventory/barcode_print.html', {'product': product, 'barcode_val': product.barcode or product.code, 'sticker_range': range(30)})

@login_required
def print_document(request, doc_no):
    doc = get_object_or_404(InventoryDoc, doc_no=doc_no)
    company = CompanyInfo.objects.first()
    return render(request, 'inventory/doc_print.html', {'doc': doc, 'company': company})


# ==========================================
# ระบบรับสินค้าจาก PO (GR)
# ==========================================
@login_required
def po_receive_list(request):
    pending_pos = PurchaseOrder.objects.filter(status='APPROVED', receipt_status__in=['PENDING', 'PARTIAL']).order_by('expected_date', '-id')
    return render(request, 'inventory/po_receive_list.html', {'pos': pending_pos})

@login_required
@transaction.atomic
def po_receive_process(request, po_id):
    po = get_object_or_404(PurchaseOrder, id=po_id, status='APPROVED')
    if request.method == 'POST':
        reference_doc = request.POST.get('reference_doc', '')
        note = request.POST.get('note', '')
        items_to_receive = []
        has_error = False
        for item in po.items.all():
            input_name = f"qty_{item.id}"
            receive_val = request.POST.get(input_name, '0')
            try: receive_qty = Decimal(receive_val.replace(',', ''))
            except (ValueError, InvalidOperation): receive_qty = Decimal('0')

            if receive_qty > 0:
                remaining = Decimal(str(item.quantity)) - Decimal(str(item.received_qty))
                if receive_qty > remaining:
                    messages.error(request, f"❌ รับของเกิน! {item.product.name} (รับได้ไม่เกิน {remaining})")
                    has_error = True
                    break
                items_to_receive.append({'item_obj': item, 'receive_qty': receive_qty})

        if not has_error and items_to_receive:
            slip_file = request.FILES.get('slip_image')

            doc = InventoryDoc.objects.create(
                doc_type='GR',
                po_reference=po,
                reference=reference_doc,
                description=note,
                created_by=request.user,
                slip_image=slip_file
            )
            for data in items_to_receive:
                item = data['item_obj']
                qty = data['receive_qty']
                StockMovement.objects.create(doc=doc, product=item.product, quantity=qty, movement_type='IN', created_by=request.user)
                item.received_qty = Decimal(str(item.received_qty)) + qty
                item.save()
            po.refresh_from_db()
            all_completed = True
            any_received = False
            for item in po.items.all():
                if Decimal(str(item.received_qty)) > 0: any_received = True
                if Decimal(str(item.received_qty)) < Decimal(str(item.quantity)): all_completed = False

            if all_completed:
                po.receipt_status = 'COMPLETED'
            elif any_received:
                po.receipt_status = 'PARTIAL'
            po.save()

            # 🌟 [NEW] สมองกลอัปเดตสถานะ JOB อัตโนมัติเมื่อรับของเข้าคลัง (Trigger) 🌟
            if po.ppo_ref:
                try:
                    from purchasing.models import PurchasePreparation
                    from manufacturing.models import ProductionOrder, BOM

                    ppo = PurchasePreparation.objects.get(code=po.ppo_ref)
                    related_jobs = ppo.production_orders.filter(status='WAITING_MATERIALS')

                    # เช็ค JOB แต่ละตัวว่าของในคลังพอเบิกหรือยัง
                    for job in related_jobs:
                        is_ready = True
                        bom = BOM.objects.filter(product=job.product).first()
                        if bom:
                            for bom_item in bom.items.all():
                                req_qty = Decimal(str(bom_item.quantity))
                                stock = Decimal(str(bom_item.raw_material.stock_qty or 0))
                                if stock < req_qty:
                                    is_ready = False
                                    break # ขาดชิ้นเดียวก็ถือว่ายังไม่พร้อม

                        # ถ้าของครบทุกรายการ ให้เด้งสถานะ JOB ไปให้คลังเบิกของได้เลย!
                        if is_ready:
                            job.status = 'WAITING_INVENTORY'
                            job.save()

                except Exception as e:
                    print(f"เกิดข้อผิดพลาดในการอัปเดตสถานะ JOB: {e}")

            messages.success(request, f"✅ รับสินค้าจาก PO: {po.code} สำเร็จ! และระบบได้อัปเดตสถานะให้แผนกคลังสินค้าทราบแล้ว")
            return redirect('print_document', doc_no=doc.doc_no)

    return render(request, 'inventory/po_receive_form.html', {'po': po})

# ==========================================
# ระบบรับสินค้าจาก PQ (ต่างประเทศ)
# ==========================================
@login_required
def pq_receive_list(request):
    pending_pqs = OverseasPO.objects.filter(status__in=['FULLY_PAID', 'DEPOSITED']).order_by('eta_date', '-id')
    return render(request, 'inventory/pq_receive_list.html', {'pos': pending_pqs})

@login_required
@transaction.atomic
def pq_receive_process(request, pq_id):
    pq = get_object_or_404(OverseasPO, id=pq_id, status__in=['FULLY_PAID', 'DEPOSITED'])
    if request.method == 'POST':
        reference_doc = request.POST.get('reference_doc', pq.pi_number)
        note = request.POST.get('note', f'รับสินค้าจาก PQ {pq.po_number}')
        doc = InventoryDoc.objects.create(doc_type='GR', reference=reference_doc, description=note, created_by=request.user)
        for item in pq.overseas_items.all():
            if item.product and item.quantity > 0:
                qty_decimal = Decimal(str(item.quantity))
                StockMovement.objects.create(doc=doc, product=item.product, quantity=qty_decimal, movement_type='IN', created_by=request.user)
        pq.status = 'COMPLETED'
        pq.save()
        messages.success(request, f"✅ รับสินค้าจาก PQ: {pq.po_number} สำเร็จ!")
        return redirect('print_document', doc_no=doc.doc_no)
    return render(request, 'inventory/pq_receive_form.html', {'po': pq})


# ==========================================
# Delete Product
# ==========================================
@login_required
def product_delete(request, pk):
    product = get_object_or_404(Product, pk=pk)
    p_type = product.product_type
    product_name = product.name
    product.delete()
    messages.success(request, f"🗑️ ลบข้อมูล '{product_name}' เรียบร้อยแล้วค่ะ")
    return redirect(f"{reverse('product_list')}?type={p_type}")

# ==========================================
# 🌟 [NEW] ระบบสต็อกการ์ด (Stock Card) 🌟
# ==========================================
@login_required
def product_stock_card(request, pk):
    product = get_object_or_404(Product, pk=pk)

    # ดึงประวัติทั้งหมด เรียงจากเก่าไปใหม่ เพื่อคำนวณยอดยกมา (Running Balance)
    movements = StockMovement.objects.filter(product=product).select_related('doc', 'created_by').order_by('created_at', 'id')

    history = []
    running_balance = Decimal('0.00')

    for mov in movements:
        # 🌟 [FIXED] จัดกลุ่มประเภทการรับเข้าและเบิกออกให้ครอบคลุม
        is_in = mov.movement_type in ['IN', 'RETURN']
        is_out = mov.movement_type in ['OUT', 'DISPATCH', 'RESERVE']

        if is_in:
            running_balance += mov.quantity
        elif is_out:
            running_balance -= mov.quantity

        # 🌟 [FIXED] ดึงข้อมูลมาแสดงให้ครบ แม้จะไม่มี InventoryDoc (doc=None)
        doc_no_display = mov.doc.doc_no if mov.doc else (mov.reference_doc or '-')
        doc_type_display = mov.doc.get_doc_type_display() if mov.doc and hasattr(mov.doc, 'get_doc_type_display') else mov.get_movement_type_display()

        # ถ้าระบุ Note ไว้ที่ตัว Movement โดยตรง ให้ใช้ Note ถ้าไม่มีให้ไปดึง Description จาก Doc
        desc_display = mov.note if mov.note else (mov.doc.description if mov.doc else '-')

        # สร้างพจนานุกรมเก็บประวัติแต่ละบรรทัด
        history.append({
            'date': mov.created_at,
            'doc_no': doc_no_display,
            'doc_type': doc_type_display,
            'description': desc_display,
            'in_qty': mov.quantity if is_in else None,
            'out_qty': mov.quantity if is_out else None,
            'balance': running_balance,
            'user': mov.created_by.first_name if mov.created_by else 'System'
        })

    # สลับเอาข้อมูลล่าสุด (ปัจจุบัน) ขึ้นด้านบนสุดของตาราง
    history.reverse()

    # 🌟 [FIXED] อัปเดต Physical Stock (ยอดในลาน) ให้ตรงกับสต็อกการ์ด
    if product.stock_qty != running_balance:
        product.stock_qty = running_balance
        product.save()

    paginator = Paginator(history, 20)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'inventory/stock_card.html', {
        'product': product,
        'page_obj': page_obj
    })

# ==========================================
# 🌟 [NEW] ระบบพิมพ์ใบตรวจนับสต็อก (Stock Count Sheet) 🌟
# ==========================================
@login_required
def print_stock_count_sheet(request):
    p_type = request.GET.get('type', 'FG')
    search_query = request.GET.get('q', '')
    rm_category_id = request.GET.get('rm_category', '')
    stock_status = request.GET.get('stock_status', '')

    products = Product.objects.filter(is_active=True, product_type=p_type).order_by('code')

    if search_query:
        products = products.filter(Q(code__icontains=search_query) | Q(name__icontains=search_query) | Q(category__name__icontains=search_query))
    if rm_category_id:
        products = products.filter(rm_category_id=rm_category_id)
    if stock_status == 'in_stock':
        products = products.filter(stock_qty__gt=0)
    elif stock_status == 'out_of_stock':
        products = products.filter(stock_qty__lte=0)

    # ดึงชื่อแผนกมาแสดงที่หัวกระดาษ (ถ้ามีการเลือก)
    category_name = "ทั้งหมด"
    if rm_category_id:
        try: category_name = RawMaterialCategory.objects.get(id=rm_category_id).name
        except: pass

    company = CompanyInfo.objects.first()
    title = 'คลังสินค้าสำเร็จรูป (FG)' if p_type == 'FG' else 'คลังวัตถุดิบ (RM)'

    return render(request, 'inventory/stock_count_print.html', {
        'products': products,
        'title': title,
        'p_type': p_type,
        'category_name': category_name,
        'company': company
    })