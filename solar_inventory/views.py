from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.db.models import F, Q
import openpyxl
import json

# 🌟 Import ข้อมูลจากแอปตัวเอง (เฉพาะเรื่องคลังสินค้า)
from .models import SolarProduct, SolarProductCategory, SolarRawMaterialCategory, SolarStockMovement, SolarInventoryDoc
from django.core.paginator import Paginator
from .forms import SolarProductForm, SolarStockMovementForm, SolarStandardBOMFormSet

# 🌟 [NEW] นำเข้าโมเดลใบสั่งงานมาใช้ตัดสต็อก
from solar_jobs.models import SolarJob, SolarJobBOM

# ==========================================
# 📦 คลังสินค้าโซล่า (Dashboard & แยกลิสต์ FG/RM)
# ==========================================
@login_required
def solar_inventory_list(request):
    # 🌟 1. ดึงข้อมูลตัวเลขสรุปสำหรับหน้า Dashboard (ไม่มีการโหลดตารางให้หนักเครื่อง)
    rm_products = SolarProduct.objects.filter(product_type='RM', is_active=True)
    fg_products = SolarProduct.objects.filter(product_type='FG', is_active=True)

    # คำนวณสรุปข้อมูล
    low_stock_count = sum(1 for rm in rm_products if rm.stock_qty <= rm.min_level)
    total_rm_value = sum(rm.total_value for rm in rm_products)
    total_fg_value = sum(fg.total_value for fg in fg_products)

    # นับจำนวนงานที่รอสโตร์จ่ายของ
    requisition_count = SolarJob.objects.filter(
        Q(status='WAITING_STORE') |
        Q(status='IN_PROGRESS', job_boms__planned_quantity__gt=F('job_boms__actual_used_quantity'))
    ).distinct().count()

    return render(request, 'solar_inventory/dashboard.html', {
        'rm_count': rm_products.count(),
        'fg_count': fg_products.count(),
        'low_stock_count': low_stock_count,
        'total_rm_value': total_rm_value,
        'total_fg_value': total_fg_value,
        'requisition_count': requisition_count
    })

# 🌟 2. หน้าแสดงตาราง แพ็กเกจหลัก (FG) เท่านั้น
@login_required
def solar_fg_list(request):
    fg_products = SolarProduct.objects.filter(product_type='FG').order_by('-is_active', '-created_at')
    return render(request, 'solar_inventory/fg_list.html', {'fg_products': fg_products})

# 🌟 3. หน้าแสดงตาราง อุปกรณ์เสริม (RM) เท่านั้น
@login_required
def solar_rm_list(request):
    rm_products = SolarProduct.objects.filter(product_type='RM').order_by('-is_active', '-created_at')
    return render(request, 'solar_inventory/rm_list.html', {'rm_products': rm_products})

@login_required
def solar_product_create(request):
    default_type = request.GET.get('type', 'FG')
    page_title = 'เพิ่มวัตถุดิบ/อุปกรณ์เสริม' if default_type == 'RM' else 'เพิ่มสินค้า/แพ็กเกจใหม่'

    rm_prices = {str(rm.id): float(rm.cost_price) for rm in SolarProduct.objects.filter(product_type='RM', is_active=True)}
    rm_prices_json = json.dumps(rm_prices)

    # 🌟 [NEW] สวิตช์สลับราง: เลือกไฟล์ Template ตามประเภทที่รับมา
    template_name = 'solar_inventory/product_fg_form.html' if default_type == 'FG' else 'solar_inventory/product_rm_form.html'

    if request.method == 'POST':
        form = SolarProductForm(request.POST, request.FILES)
        if form.is_valid():
            prod = form.save(commit=False)
            prod.product_type = default_type # 🌟 บังคับเซ็ตค่าประเภทสินค้าเพื่อความชัวร์ (เพราะเราซ่อนช่องนี้ไว้)
            prod.save()

            formset = SolarStandardBOMFormSet(request.POST, instance=prod)
            if formset.is_valid() and default_type == 'FG':
                formset.save()

            messages.success(request, f"✅ เพิ่มรายการ '{prod.name}' ลงในคลังสินค้าเรียบร้อยแล้ว")
            return redirect('solar_inventory_list')
        else:
            messages.error(request, "❌ กรุณาตรวจสอบความถูกต้องของข้อมูล")
            formset = SolarStandardBOMFormSet(request.POST)
    else:
        form = SolarProductForm(initial={'product_type': default_type})
        formset = SolarStandardBOMFormSet()

    return render(request, template_name, {
        'form': form,
        'formset': formset,
        'default_type': default_type,
        'title': page_title,
        'rm_prices_json': rm_prices_json
    })

@login_required
def solar_product_edit(request, pk):
    product = get_object_or_404(SolarProduct, pk=pk)
    p_type = product.product_type # เก็บประเภทสินค้าปัจจุบันไว้

    rm_prices = {str(rm.id): float(rm.cost_price) for rm in SolarProduct.objects.filter(product_type='RM', is_active=True)}
    rm_prices_json = json.dumps(rm_prices)

    # 🌟 [NEW] สวิตช์สลับราง: เลือกไฟล์ Template ตามประเภทของสินค้าที่กำลังแก้ไข
    template_name = 'solar_inventory/product_fg_form.html' if p_type == 'FG' else 'solar_inventory/product_rm_form.html'

    if request.method == 'POST':
        form = SolarProductForm(request.POST, request.FILES, instance=product)
        formset = SolarStandardBOMFormSet(request.POST, instance=product)
        if form.is_valid() and (p_type != 'FG' or formset.is_valid()):
            form.save()
            if p_type == 'FG':
                formset.save()
            messages.success(request, f"✅ อัปเดตข้อมูล '{product.name}' เรียบร้อยแล้ว")
            return redirect('solar_inventory_list')
        else:
            messages.error(request, "❌ กรุณาตรวจสอบความถูกต้องของข้อมูล")
    else:
        form = SolarProductForm(instance=product)
        formset = SolarStandardBOMFormSet(instance=product)

    return render(request, template_name, {
        'form': form,
        'formset': formset,
        'default_type': p_type,
        'product': product,
        'title': f'แก้ไข: {product.name}',
        'rm_prices_json': rm_prices_json
    })

# ------------------------------------------
# 🌟 API สำหรับเพิ่มหมวดหมู่แบบ Popup (AJAX)
# ------------------------------------------
@login_required
def add_fg_category_ajax(request):
    if request.method == 'POST':
        category_name = request.POST.get('name')
        if category_name:
            cat, created = SolarProductCategory.objects.get_or_create(name=category_name.strip())
            return JsonResponse({'success': True, 'id': cat.id, 'name': cat.name})
        return JsonResponse({'success': False, 'error': 'กรุณาระบุชื่อหมวดหมู่'})
    return JsonResponse({'success': False, 'error': 'Invalid request'})

@login_required
def add_rm_category_ajax(request):
    if request.method == 'POST':
        category_name = request.POST.get('name')
        if category_name:
            cat, created = SolarRawMaterialCategory.objects.get_or_create(name=category_name.strip())
            return JsonResponse({'success': True, 'id': cat.id, 'name': cat.name})
        return JsonResponse({'success': False, 'error': 'กรุณาระบุชื่อหมวดหมู่'})
    return JsonResponse({'success': False, 'error': 'Invalid request'})

@login_required
def solar_inventory_download_template(request):
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename="inventory_template.xlsx"'
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Solar Inventory"
    headers = ['ประเภท (FG หรือ RM)', 'รหัสสินค้า (เว้นว่างได้)', 'หมวดหมู่ (Category)', 'ชื่อสินค้า/แพ็กเกจ', 'หน่วยนับ', 'ราคาทุน', 'ราคาขาย', 'จำนวนคงเหลือ', 'จุดสั่งซื้อ']
    ws.append(headers)
    ws.append(['RM', 'RM-001', 'อุปกรณ์สายไฟ', 'สายไฟ DC 4mm (ตัวอย่าง)', 'เมตร', 15, 25, 100, 20])
    ws.append(['FG', '', 'แพ็กเกจ 5kW', 'แพ็กเกจ 5kW 1 Phase (ตัวอย่าง)', 'ชุด', 100000, 150000, 5, 2])
    wb.save(response)
    return response

@login_required
def solar_inventory_import(request):
    if request.method == 'POST' and request.FILES.get('excel_file'):
        excel_file = request.FILES['excel_file']
        if not excel_file.name.endswith('.xlsx'):
            messages.error(request, '❌ ไฟล์ไม่ถูกต้อง กรุณาอัปโหลดไฟล์นามสกุล .xlsx เท่านั้น')
            return redirect('solar_inventory_list')

        try:
            wb = openpyxl.load_workbook(excel_file, data_only=True)
            sheet = wb.active
            count_created, count_updated = 0, 0

            for row in sheet.iter_rows(min_row=2, values_only=True):
                product_type = str(row[0]).strip().upper() if row[0] else 'RM'
                code = str(row[1]).strip() if row[1] else None
                cat_name = str(row[2]).strip() if row[2] else None
                name = str(row[3]).strip() if row[3] else None
                unit = str(row[4]).strip() if row[4] else 'ชิ้น'
                cost_price = float(row[5]) if row[5] else 0.0
                sell_price = float(row[6]) if row[6] else 0.0
                stock_qty = float(row[7]) if row[7] else 0.0
                min_level = float(row[8]) if row[8] else 0.0

                if name and name != 'None':
                    if product_type not in ['FG', 'RM']: product_type = 'RM'
                    fg_cat, rm_cat = None, None
                    if cat_name and cat_name != 'None':
                        if product_type == 'FG': fg_cat, _ = SolarProductCategory.objects.get_or_create(name=cat_name)
                        else: rm_cat, _ = SolarRawMaterialCategory.objects.get_or_create(name=cat_name)

                    defaults_data = {
                        'product_type': product_type, 'name': name, 'category': fg_cat, 'rm_category': rm_cat,
                        'unit': unit, 'cost_price': cost_price, 'sell_price': sell_price, 'stock_qty': stock_qty,
                        'min_level': min_level, 'is_active': True
                    }
                    if code and code != 'None':
                        obj, created = SolarProduct.objects.update_or_create(code=code, defaults=defaults_data)
                        if created: count_created += 1
                        else: count_updated += 1
                    else:
                        SolarProduct.objects.create(**defaults_data)
                        count_created += 1

            messages.success(request, f'✅ นำเข้าข้อมูลสำเร็จ! สร้างใหม่ {count_created} รายการ, อัปเดต {count_updated} รายการ')
        except Exception as e:
            messages.error(request, f'❌ เกิดข้อผิดพลาดในการอ่านไฟล์: {str(e)}')
    return redirect('solar_inventory_list')

# ------------------------------------------
# 📥/📤 ระบบรับเข้า - เบิกออก แมนนวล
# ------------------------------------------
@login_required
def solar_stock_movement_create(request):
    if request.method == 'POST':
        form = SolarStockMovementForm(request.POST)
        if form.is_valid():
            movement = form.save(commit=False)

            # 🌟 [NEW] สร้างหัวเอกสารอัตโนมัติก่อนบันทึกรายการ
            doc_type = 'GR' if movement.movement_type == 'IN' else 'GI'
            doc = SolarInventoryDoc.objects.create(
                doc_type=doc_type,
                reference=movement.reference_doc,
                description=f"บันทึกรับเข้า/เบิกออก (Manual)",
                created_by=request.user
            )

            movement.doc = doc # ผูกรายการเข้ากับหัวเอกสารเลขใหม่
            movement.save()

            action = "รับเข้า" if movement.movement_type == 'IN' else "เบิกออก"
            messages.success(request, f"✅ บันทึกรายการ{action} และสร้างเอกสารเลขที่ {doc.doc_no} เรียบร้อยแล้ว")
            return redirect('solar_inventory_list')
        else:
            messages.error(request, "❌ กรุณาตรวจสอบความถูกต้องของข้อมูล")
    else:
        initial_data = {}
        product_id = request.GET.get('product_id')
        if product_id:
            initial_data['product'] = product_id
        form = SolarStockMovementForm(initial=initial_data)

    return render(request, 'solar_inventory/stock_movement_form.html', {'form': form})

# ------------------------------------------
# 📊 ระบบ Stock Card (ประวัติความเคลื่อนไหวสินค้าพร้อม Running Balance)
# ------------------------------------------
@login_required
def solar_stock_card(request, pk):
    product = get_object_or_404(SolarProduct, pk=pk)

    # 🌟 [NEW] ดึงประวัติทั้งหมดโดยเรียงจาก 'เก่าสุด' ไป 'ใหม่สุด' เพื่อคำนวณยอดสะสม
    movements_asc = SolarStockMovement.objects.filter(product=product).order_by('created_at', 'id')

    # 🌟 [NEW] ลอจิกคำนวณยอดคงเหลือสะสม (Running Balance)
    running_balance = 0
    calculated_movements = []

    for move in movements_asc:
        if move.movement_type == 'IN':
            running_balance += move.quantity
        elif move.movement_type == 'OUT':
            running_balance -= move.quantity

        # แปะค่ายอดสะสม (running_balance) ไว้ที่ object แต่ละตัว
        move.current_balance = running_balance
        calculated_movements.append(move)

    # 🌟 [NEW] กลับด้านข้อมูล (Reverse) ให้รายการ 'ล่าสุด' ขึ้นมาอยู่บนสุดเหมือนเดิม
    calculated_movements.reverse()

    # นำรายการที่คำนวณเสร็จแล้วไปแบ่งหน้า (Pagination)
    paginator = Paginator(calculated_movements, 20)
    page_obj = paginator.get_page(request.GET.get('page'))

    # 🌟 [NEW] สวิตช์สลับราง: ตรวจสอบประเภทสินค้าเพื่อเลือกไฟล์หน้าจอให้ถูกต้อง
    if product.product_type == 'FG':
        template_name = 'solar_inventory/stock_card_fg.html'
    else:
        template_name = 'solar_inventory/stock_card_rm.html'

    return render(request, template_name, {
        'product': product,
        'page_obj': page_obj
    })

# ==========================================
# 📦 หน้าจอสำหรับสโตร์: จัดการใบขอเบิกวัสดุ (Requisitions)
# ==========================================
@login_required
def store_requisition_list(request):
    # 🌟 [FIXED] ดึงงานที่รอสโตร์จ่ายของ หรือ งานที่ขอเบิกเพิ่ม (แต่ต้องยังไม่ถูกส่งไปรอจัดซื้อ)
    jobs_waiting = SolarJob.objects.filter(
        Q(status='WAITING_STORE') |
        Q(status='IN_PROGRESS', job_boms__planned_quantity__gt=F('job_boms__actual_used_quantity'))
    ).filter(is_waiting_purchase=False).prefetch_related('job_boms__product').distinct().order_by('created_at')

    return render(request, 'solar_inventory/store_requisition_list.html', {
        'jobs_waiting': jobs_waiting
    })

# 🌟 [FIXED] ฟังก์ชันแสดงหน้า Detail พร้อมระบบคำนวณของขาดอัตโนมัติ
@login_required
def store_requisition_detail(request, job_id):
    job = get_object_or_404(SolarJob, id=job_id)

    has_shortage = False
    bom_list = []

    # 🌟 ลูปเพื่อคำนวณว่ามีวัสดุตัวไหนบ้างที่ "สต็อกไม่พอ"
    for bom in job.job_boms.all():
        # 🌟 [แก้ไขใหม่] คำนวณเฉพาะ "ส่วนต่าง" ที่ต้องเบิกเพิ่ม
        qty_to_deduct = bom.planned_quantity - bom.actual_used_quantity
        missing_qty = 0

        # ถ้าส่วนต่างมากกว่า 0 (แปลว่ามีการขอของเพิ่มจริงๆ) ค่อยเอาไปโชว์สโตร์
        if qty_to_deduct > 0:
            if qty_to_deduct > bom.product.stock_qty:
                missing_qty = qty_to_deduct - bom.product.stock_qty
                has_shortage = True # เจอของขาดแล้ว! แจ้งเตือนสโตร์

            bom.qty_to_deduct = qty_to_deduct
            bom.missing_qty = missing_qty
            bom_list.append(bom)

    return render(request, 'solar_inventory/store_requisition_detail.html', {
        'job': job,
        'bom_list': bom_list,
        'has_shortage': has_shortage
    })

# 🌟 [NEW] ฟังก์ชันสำหรับให้สโตร์กด "ส่งใบขอซื้อ (PR)" ให้จัดซื้อ
@login_required
def store_trigger_pr(request, job_id):
    if request.method == 'POST':
        # 🌟 [FIXED] ปลดล็อคสถานะ เพื่อให้กดส่ง PR สำหรับงานที่กำลัง IN_PROGRESS (เบิกเพิ่ม) ได้ 🌟
        job = get_object_or_404(SolarJob, id=job_id)

        from solar_jobs.models import SolarPurchasePreparation, SolarPurchasePreparationItem

        # 1. สร้างใบเตรียมสั่งซื้อ (PPO) อัตโนมัติ
        ppo = SolarPurchasePreparation.objects.create(
            job=job,
            created_by=getattr(request.user, 'employee', None)
        )

        # 2. คัดเฉพาะของที่ "ขาด" ใส่เข้าไปในเอกสาร PPO
        for bom in job.job_boms.all():
            # 🌟 [แก้ไขใหม่] ใช้สูตรหาส่วนต่าง
            qty_to_deduct = bom.planned_quantity - bom.actual_used_quantity

            if qty_to_deduct > 0: # ดึงเฉพาะรายการที่เบิกเพิ่ม
                if qty_to_deduct > bom.product.stock_qty:
                    missing_qty = qty_to_deduct - bom.product.stock_qty
                    SolarPurchasePreparationItem.objects.create(
                        ppo=ppo,
                        product=bom.product,
                        quantity_needed=missing_qty
                    )

        # 🌟 [FIXED] เช็คก่อนว่างานเริ่มติดตั้งไปหรือยัง? ถ้าเริ่มแล้ว ห้ามถอยหลัง! แต่ให้เปิดสวิตช์รอจัดซื้อแทน
        if job.status != 'IN_PROGRESS':
            job.status = 'WAITING_PURCHASE'

        # 🌟 เปิดสวิตช์ความจำว่างานนี้กำลังรอจัดซื้อซื้อของมาเติมให้ (การ์ดจะหายไปจากหน้าสโตร์ชั่วคราว)
        job.is_waiting_purchase = True
        job.save()

        messages.success(request, f"✅ ระบบได้สร้างใบขอซื้อ (PPO) รหัส {ppo.code} สำหรับวัสดุที่ขาด และส่งเรื่องให้แผนกจัดซื้อเรียบร้อยแล้ว!")
        return redirect('store_requisition_list')

@login_required
def store_confirm_deduction(request, job_id):
    if request.method == 'POST':
        job = get_object_or_404(SolarJob, id=job_id)

        # 🌟 ลูปที่ 1: เช็คก่อนว่ามีของชิ้นไหนที่สต็อกไม่พอหรือจะทำให้ติดลบหรือไม่
        has_items_to_deduct = False
        for bom in job.job_boms.all():
            qty_to_deduct = bom.planned_quantity - bom.actual_used_quantity
            if qty_to_deduct > 0:
                has_items_to_deduct = True
                if bom.product and bom.product.stock_qty < qty_to_deduct:
                    messages.error(request, f"❌ ไม่สามารถจ่ายของได้! วัตถุดิบ '{bom.product.name}' มีจำนวนไม่เพียงพอ (ต้องการเบิก {qty_to_deduct}, มีอยู่ {bom.product.stock_qty})")
                    return redirect('store_requisition_list')

        # 🌟 [NEW] สร้างหัวเอกสารใบเบิก (GI) 1 ใบคลุมรายการทั้งหมดที่จะจ่าย
        gi_doc = None
        if has_items_to_deduct:
            gi_doc = SolarInventoryDoc.objects.create(
                doc_type='GI',
                reference=f"JOB: {job.code}",
                description=f"เบิกจ่ายวัตถุดิบ/อุปกรณ์ สำหรับงานติดตั้ง {job.code}",
                created_by=request.user
            )

            # 🌟 ลูปที่ 2: ถ้ารอดเงื่อนไขด้านบนมาได้ แสดงว่าของครบ ค่อยดึงรายการเพื่อตัดสต็อกจริง
            for bom in job.job_boms.all():
                qty_to_deduct = bom.planned_quantity - bom.actual_used_quantity

                if qty_to_deduct > 0 and bom.product:
                    # 🌟 สร้างประวัติเพื่อตัดสต็อก พร้อมผูกรหัสใบเบิก (GI) เข้าไปด้วย
                    SolarStockMovement.objects.create(
                        doc=gi_doc,  # <--- พระเอกของเรา ผูกเข้ากับหัวบิล
                        product=bom.product,
                        quantity=qty_to_deduct,
                        movement_type='OUT',
                        reference_doc=f"จ่ายของสำหรับงาน: {job.code}"
                    )

                    # 🌟 อัปเดตยอดเบิกจริงใน BOM ให้รวมกับยอดที่เพิ่งเบิกไป
                    bom.actual_used_quantity += qty_to_deduct
                    bom.save()

        # 🌟 คืนสถานะงานกลับไปเป็น "กำลังติดตั้ง (IN_PROGRESS)"
        job.status = 'IN_PROGRESS'
        job.save()

        if gi_doc:
            messages.success(request, f"✅ ตัดสต็อกและสร้างใบเบิกเลขที่ {gi_doc.doc_no} สำหรับงาน {job.code} เรียบร้อยแล้ว!")
        else:
            messages.warning(request, f"⚠️ ไม่มีรายการเบิกเพิ่มเติมสำหรับงาน {job.code}")

    return redirect('store_requisition_list')

# ==========================================
# 🌟 [NEW] ระบบจัดการเอกสารคลังสินค้า (Stock In / Print A4)
# ==========================================
@login_required
def solar_document_list_in(request):
    # ดึงประวัติใบรับของ (GR) ทั้งหมดเรียงจากใหม่ไปเก่า
    docs = SolarInventoryDoc.objects.filter(doc_type='GR').order_by('-created_at')
    return render(request, 'solar_inventory/document_list_in.html', {
        'docs': docs,
        'title': 'ประวัติใบรับสินค้า/วัตถุดิบ (Stock In)'
    })

@login_required
def solar_print_document(request, doc_no):
    # ดึงข้อมูลหัวเอกสารตามเลขที่ส่งมา
    doc = get_object_or_404(SolarInventoryDoc, doc_no=doc_no)

    # ลองดึงข้อมูลบริษัทมาใช้พิมพ์บนหัวกระดาษ (ถ้ามี)
    company = None
    try:
        from master_data.models import CompanyInfo
        company = CompanyInfo.objects.first()
    except ImportError:
        pass

    return render(request, 'solar_inventory/doc_print.html', {
        'doc': doc,
        'company': company
    })

@login_required
def solar_document_list_out(request):
    # ดึงประวัติใบเบิกของ (GI) ทั้งหมดเรียงจากใหม่ไปเก่า
    docs = SolarInventoryDoc.objects.filter(doc_type='GI').order_by('-created_at')
    return render(request, 'solar_inventory/document_list_out.html', {
        'docs': docs,
        'title': 'ประวัติใบเบิกสินค้า (Stock Out / GI)'
    })