from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
import openpyxl
import json

# 🌟 Import ข้อมูลจากแอปตัวเอง (เฉพาะเรื่องคลังสินค้า)
from .models import SolarProduct, SolarProductCategory, SolarRawMaterialCategory, SolarStockMovement
from django.core.paginator import Paginator
from .forms import SolarProductForm, SolarStockMovementForm, SolarStandardBOMFormSet

# ==========================================
# 📦 คลังสินค้าโซล่า (Inventory & Excel Import)
# ==========================================
@login_required
def solar_inventory_list(request):
    fg_products = SolarProduct.objects.filter(product_type='FG').order_by('-is_active', '-created_at')
    rm_products = SolarProduct.objects.filter(product_type='RM').order_by('-is_active', '-created_at')
    return render(request, 'solar_inventory/inventory_list.html', {
        'fg_products': fg_products,
        'rm_products': rm_products
    })

@login_required
def solar_product_create(request):
    default_type = request.GET.get('type', 'FG')
    page_title = 'เพิ่มวัตถุดิบ/อุปกรณ์เสริม' if default_type == 'RM' else 'เพิ่มสินค้า/แพ็กเกจใหม่'

    # 🌟 [NEW] ดึงราคาทุนของ RM ทั้งหมด ส่งไปเป็น JSON ให้หน้าเว็บคำนวณ Real-time
    rm_prices = {str(rm.id): float(rm.cost_price) for rm in SolarProduct.objects.filter(product_type='RM', is_active=True)}
    rm_prices_json = json.dumps(rm_prices)

    if request.method == 'POST':
        form = SolarProductForm(request.POST)
        if form.is_valid():
            prod = form.save()
            # 🌟 ถ่ายโอนข้อมูล Formset ไปยังแพ็กเกจนี้
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

    return render(request, 'solar_inventory/product_form.html', {
        'form': form,
        'formset': formset,
        'default_type': default_type,
        'title': page_title,
        'rm_prices_json': rm_prices_json # 🌟 ส่งตัวแปรนี้ไป
    })

@login_required
def solar_product_edit(request, pk):
    product = get_object_or_404(SolarProduct, pk=pk)

    # 🌟 [NEW] ดึงราคาทุนของ RM ทั้งหมด ส่งไปเป็น JSON ให้หน้าเว็บคำนวณ Real-time
    rm_prices = {str(rm.id): float(rm.cost_price) for rm in SolarProduct.objects.filter(product_type='RM', is_active=True)}
    rm_prices_json = json.dumps(rm_prices)

    if request.method == 'POST':
        form = SolarProductForm(request.POST, instance=product)
        formset = SolarStandardBOMFormSet(request.POST, instance=product)
        if form.is_valid() and (product.product_type != 'FG' or formset.is_valid()):
            form.save()
            if product.product_type == 'FG':
                formset.save()
            messages.success(request, f"✅ อัปเดตข้อมูล '{product.name}' เรียบร้อยแล้ว")
            return redirect('solar_inventory_list')
        else:
            messages.error(request, "❌ กรุณาตรวจสอบความถูกต้องของข้อมูล")
    else:
        form = SolarProductForm(instance=product)
        formset = SolarStandardBOMFormSet(instance=product)

    return render(request, 'solar_inventory/product_form.html', {
        'form': form,
        'formset': formset,
        'default_type': product.product_type,
        'product': product,
        'title': f'แก้ไข: {product.name}',
        'rm_prices_json': rm_prices_json # 🌟 ส่งตัวแปรนี้ไป
    })

# ------------------------------------------
# 🌟 API สำหรับเพิ่มหมวดหมู่แบบ Popup (AJAX)
# ------------------------------------------
@login_required
def add_fg_category_ajax(request):
    if request.method == 'POST':
        category_name = request.POST.get('name')
        if category_name:
            # ตรวจสอบว่ามีชื่อนี้อยู่แล้วหรือไม่ ถ้าไม่มีก็สร้างใหม่
            cat, created = SolarProductCategory.objects.get_or_create(name=category_name.strip())
            return JsonResponse({'success': True, 'id': cat.id, 'name': cat.name})
        return JsonResponse({'success': False, 'error': 'กรุณาระบุชื่อหมวดหมู่'})
    return JsonResponse({'success': False, 'error': 'Invalid request'})

# ------------------------------------------
# 🌟 API สำหรับเพิ่มหมวดหมู่ RM แบบ Popup (AJAX)
# ------------------------------------------
@login_required
def add_rm_category_ajax(request):
    if request.method == 'POST':
        category_name = request.POST.get('name')
        if category_name:
            # ตรวจสอบว่ามีชื่อนี้อยู่แล้วหรือไม่ ถ้าไม่มีก็สร้างใหม่
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
# 📊 ระบบ Stock Card (ประวัติความเคลื่อนไหวสินค้า)
# ------------------------------------------
@login_required
def solar_stock_card(request, pk):
    product = get_object_or_404(SolarProduct, pk=pk)

    # ดึงประวัติการเคลื่อนไหวทั้งหมดของสินค้านี้ เรียงจากล่าสุดไปเก่าสุด
    movements = SolarStockMovement.objects.filter(product=product).order_by('-created_at', '-id')

    # ระบบแบ่งหน้า (หน้าละ 20 รายการ)
    paginator = Paginator(movements, 20)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'solar_inventory/stock_card.html', {
        'product': product,
        'page_obj': page_obj
    })

# ------------------------------------------
# 📥/📤 ระบบรับเข้า - เบิกออก แมนนวล
# ------------------------------------------
@login_required
def solar_stock_movement_create(request):
    if request.method == 'POST':
        form = SolarStockMovementForm(request.POST)
        if form.is_valid():
            movement = form.save()
            action = "รับเข้า" if movement.movement_type == 'IN' else "เบิกออก"
            messages.success(request, f"✅ บันทึกรายการ {action} จำนวน {movement.quantity} สำหรับ '{movement.product.name}' เรียบร้อยแล้ว")
            return redirect('solar_inventory_list')
        else:
            messages.error(request, "❌ กรุณาตรวจสอบความถูกต้องของข้อมูล")
    else:
        # สามารถรับค่า product_id จาก URL เพื่อเลือกสินค้าใน Dropdown อัตโนมัติได้
        initial_data = {}
        product_id = request.GET.get('product_id')
        if product_id:
            initial_data['product'] = product_id

        form = SolarStockMovementForm(initial=initial_data)

    return render(request, 'solar_inventory/stock_movement_form.html', {'form': form})