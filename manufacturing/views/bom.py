import pandas as pd
from decimal import Decimal, InvalidOperation
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.db.models import Count, Sum, F, DecimalField
from django.db.models.functions import Coalesce
from django.http import JsonResponse, HttpResponse
from django.db.models import Q

from manufacturing.models import BOM, BOMItem, ProductionOrder, ProductionOrderMaterial
from inventory.models import Product
from master_data.models import CompanyInfo
from manufacturing.forms import BOMForm, BOMItemFormSet

@login_required
def bom_list(request):
    boms = BOM.objects.select_related('product').annotate(
        item_count=Count('items', distinct=True),
        total_rm_cost=Coalesce(Sum(F('items__quantity') * F('items__raw_material__cost_price')), 0, output_field=DecimalField(max_digits=12, decimal_places=2))
    ).order_by('-id')

    for bom in boms:
        sell_price = bom.product.sell_price or Decimal('0.00')
        total_rm = bom.total_rm_cost or Decimal('0.00')
        labor = bom.labor_cost or Decimal('0.00')

        sales_admin = Decimal('0.00')
        if bom.sales_admin_type == 'PERCENT': sales_admin = (sell_price * Decimal('0.90')) * (bom.sales_admin_value / Decimal('100'))
        else: sales_admin = bom.sales_admin_value

        freight = sell_price * (bom.freight_value / Decimal('100')) if bom.freight_type == 'PERCENT' else bom.freight_value
        misc = sell_price * (bom.misc_expense_value / Decimal('100')) if bom.misc_expense_type == 'PERCENT' else bom.misc_expense_value

        bom.estimated_profit = sell_price - (total_rm + labor + sales_admin + freight + misc)
        bom.calculated_sales_admin = sales_admin
        bom.calculated_freight = freight
        bom.calculated_misc = misc
        bom.profit_percentage = (bom.estimated_profit / sell_price) * Decimal('100') if sell_price > 0 else Decimal('0.00')

    return render(request, 'manufacturing/bom_list.html', {'boms': boms})

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
def update_bom_labor_cost(request, pk):
    if request.method == 'POST':
        bom = get_object_or_404(BOM, pk=pk)
        try:
            bom.labor_cost = Decimal(request.POST.get('labor_cost', '0').replace(',', ''))
            bom.sales_admin_type = request.POST.get('sales_admin_type', 'PERCENT')
            bom.sales_admin_value = Decimal(request.POST.get('sales_admin_value', '0').replace(',', ''))
            bom.freight_type = request.POST.get('freight_type', 'THB')
            bom.freight_value = Decimal(request.POST.get('freight_value', '0').replace(',', ''))
            bom.misc_expense_type = request.POST.get('misc_expense_type', 'THB')
            bom.misc_expense_value = Decimal(request.POST.get('misc_expense_value', '0').replace(',', ''))
            bom.save()
            messages.success(request, f"✅ บันทึกต้นทุนการผลิตสำหรับ {bom.product.code} เรียบร้อยแล้ว")
        except (ValueError, InvalidOperation):
            messages.error(request, "❌ เกิดข้อผิดพลาดในการบันทึกตัวเลขต้นทุน")
    return redirect('bom_list')

@login_required
def print_master_bom(request, pk):
    bom = get_object_or_404(BOM, pk=pk)
    items = bom.items.select_related('raw_material', 'raw_material__supplier').all()
    total_cost = sum([Decimal(str(i.quantity)) * (i.raw_material.cost_price or Decimal('0')) for i in items])
    company = CompanyInfo.objects.first()
    return render(request, 'manufacturing/print_master_bom.html', {'bom': bom, 'items': items, 'total_cost': total_cost, 'company': company})

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
        ProductionOrderMaterial.objects.create(production_order=order, raw_material=item.raw_material, quantity=item.quantity * order.quantity, is_additional=False)
    messages.success(request, "📋 ดึงรายการวัตถุดิบจากสูตรมาตรฐานเรียบร้อยแล้ว!")
    return redirect(referer) if referer else redirect('production_detail', pk=order.pk)

@login_required
def print_bom(request, pk):
    order = get_object_or_404(ProductionOrder, pk=pk)
    company = CompanyInfo.objects.first()
    return render(request, 'manufacturing/print_bom.html', {'order': order, 'materials': order.materials.all(), 'company': company})

@login_required
def download_bom_template(request):
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "BOM_Template"
    headers = ['FG SKU', 'RM SKU', 'Quantity']
    ws.append(headers)
    
    header_fill = PatternFill(start_color="4CAF50", end_color="4CAF50", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True)
    align_center = Alignment(horizontal="center", vertical="center")

    for col_num, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_num)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = align_center

    ws.column_dimensions['A'].width, ws.column_dimensions['B'].width, ws.column_dimensions['C'].width = 25, 25, 15
    ws.append(['ตัวอย่าง: SD169', 'ตัวอย่าง: RM-6910-001', 1])
    sample_font = Font(italic=True, color="808080")
    for col_num in range(1, 4): ws.cell(row=2, column=col_num).font = sample_font

    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename="BOM_Import_Template.xlsx"'
    wb.save(response)
    return response

@login_required
def import_bom_excel(request):
    if request.method == 'POST' and request.FILES.get('excel_file'):
        try:
            df = pd.read_excel(request.FILES['excel_file'])
            if not all(col in df.columns for col in ['FG SKU', 'RM SKU', 'Quantity']):
                messages.error(request, "❌ รูปแบบไฟล์ไม่ถูกต้อง กรุณาใช้คอลัมน์: FG SKU, RM SKU, Quantity")
                return redirect('import_bom_excel')
            with transaction.atomic():
                 import_count = 0
                 for _, row in df.iterrows():
                    fg_sku, rm_sku = str(row['FG SKU']).strip(), str(row['RM SKU']).strip()
                    try: qty = Decimal(str(row['Quantity']))
                    except: continue
                    fg_product = Product.objects.filter(code=fg_sku, product_type='FG').first()
                    if not fg_product: continue
                    bom_obj, _ = BOM.objects.get_or_create(product=fg_product, defaults={'name': f"สูตรมาตรฐาน - {fg_product.name}"})
                    rm_product = Product.objects.filter(code=rm_sku, product_type='RM').first()
                    if rm_product:
                        BOMItem.objects.update_or_create(bom=bom_obj, raw_material=rm_product, defaults={'quantity': qty})
                        import_count += 1
            messages.success(request, f"✅ นำเข้าข้อมูลสูตรผลิตสำเร็จทั้งหมด {import_count} รายการ")
            return redirect('import_bom_excel')
        except Exception as e: messages.error(request, f"❌ เกิดข้อผิดพลาด: {str(e)}")
    return render(request, 'manufacturing/import_bom.html')

@login_required
def ajax_search_raw_material(request):
    q = request.GET.get('q', '')
    products = Product.objects.filter(product_type='RM', is_active=True)
    if q: products = products.filter(Q(code__icontains=q) | Q(name__icontains=q))
    results = [{'id': p.id, 'text': f"{p.code} - {p.name}", 'cost_price': float(p.cost_price or 0)} for p in products.order_by('code')[:30]]
    return JsonResponse({'results': results})