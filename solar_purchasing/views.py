import datetime
from decimal import Decimal, InvalidOperation
from solar_inventory.models import SolarStockMovement # ต้อง import เพิ่มเพื่อบันทึกประวัติการเข้าออกคลัง
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from django.utils import timezone

from .models import SolarPurchaseOrder, SolarPurchaseOrderItem
from .forms import SolarPurchaseOrderForm, SolarOrderItemFormSet
from master_data.models import Supplier

# 🌟 [FIXED] นำเข้า SolarProduct และระบบ PPO จากฝั่งโซล่าเซลล์
from solar_inventory.models import SolarProduct
from solar_jobs.models import SolarPurchasePreparation, SolarPurchasePreparationItem

# ------------------------------------------
# 🛡️ ระบบเช็คสิทธิ์ (Gatekeeper)
# ------------------------------------------
def is_purchasing_staff(user):
    if user.is_superuser: return True
    if hasattr(user, 'employee') and user.employee:
        dept = getattr(user.employee.department, 'name', '')
        if 'จัดซื้อ' in dept or 'Purchasing' in dept: return True
    return False

def is_purchasing_manager(user):
    if user.is_superuser: return True
    if hasattr(user, 'employee') and user.employee:
        job_title = getattr(user.employee.position, 'title', '').lower()
        rank = getattr(user.employee, 'business_rank', '').lower()
        if 'manager' in job_title or 'ผู้จัดการ' in job_title or rank in ['manager', 'director', 'executive']:
            return True
    return False

# ------------------------------------------
# 🛒 Views สำหรับระบบจัดซื้อโซล่าเซลล์
# ------------------------------------------
@login_required
def solar_po_list(request):
    if not is_purchasing_staff(request.user):
        messages.error(request, "❌ บัญชีของคุณไม่มีสิทธิ์เข้าถึงระบบจัดซื้อโซล่า")
        return redirect('dashboard')

    search_query = request.GET.get('q', '')
    status_filter = request.GET.get('status', '')

    pos = SolarPurchaseOrder.objects.all().order_by('-created_at')

    if search_query:
        pos = pos.filter(
            Q(code__icontains=search_query) |
            Q(supplier__name__icontains=search_query) |
            Q(supplier_name_free_text__icontains=search_query)
        )
    if status_filter:
        pos = pos.filter(status=status_filter)

    is_manager = is_purchasing_manager(request.user)

    pending_solar_ppo_count = SolarPurchasePreparation.objects.filter(status='PENDING').count()

    context = {
        'pos': pos,
        'search_query': search_query,
        'status_filter': status_filter,
        'is_manager': is_manager,
        'pending_solar_ppo_count': pending_solar_ppo_count,
    }
    return render(request, 'solar_purchasing/solar_po_list.html', context)

@login_required
def solar_po_create(request):
    if not is_purchasing_staff(request.user): return redirect('solar_po_list')

    if request.method == 'POST':
        form = SolarPurchaseOrderForm(request.POST)
        formset = SolarOrderItemFormSet(request.POST)

        if form.is_valid() and formset.is_valid():
            po = form.save(commit=False)
            po.status = 'DRAFT'
            po.buyer = getattr(request.user, 'employee', None)
            po.save()

            formset.instance = po
            formset.save()

            total = sum(item.total_cost for item in po.items.all() if item.total_cost)
            po.total_amount = total
            po.save()

            messages.success(request, f"✅ สร้างใบสั่งซื้อโซล่า {po.code} เรียบร้อยแล้ว (รอผู้จัดการอนุมัติ)")
            return redirect('solar_po_list')
        else:
            messages.error(request, "❌ กรุณาตรวจสอบข้อมูลให้ครบถ้วน")
    else:
        form = SolarPurchaseOrderForm(initial={'date': timezone.now().date()})
        formset = SolarOrderItemFormSet()

    # 🌟 [NEW] รับพารามิเตอร์ประเภทสินค้าจาก URL (ค่าเริ่มต้นเป็น RM)
    po_type = request.GET.get('type', 'RM')

    # 🌟 [FIXED] ดึงข้อมูลสินค้าโดยกรองตาม product_type
    solar_products = SolarProduct.objects.filter(is_active=True, product_type=po_type)
    suppliers = Supplier.objects.all()

    return render(request, 'solar_purchasing/solar_po_form.html', {
        'form': form,
        'formset': formset,
        'products': solar_products,
        'suppliers': suppliers,
        'po_type': po_type  # ส่งค่าให้ HTML ใช้แสดงผล
    })

@login_required
def solar_po_edit(request, po_id):
    if not is_purchasing_staff(request.user): return redirect('solar_po_list')

    po = get_object_or_404(SolarPurchaseOrder, id=po_id)
    is_manager = is_purchasing_manager(request.user)

    # 🌟 [NEW] เช็คว่าเอกสารถูกล็อกหรือไม่ (มีการรับของไปแล้ว)
    is_readonly = po.receipt_status != 'PENDING'

    if request.method == 'POST':
        # 🛑 [NEW] ถ้าเอกสารถูกล็อก ห้ามเซฟเด็ดขาด!
        if is_readonly:
            messages.error(request, "❌ ไม่อนุญาตให้แก้ไขใบสั่งซื้อที่มีการรับสินค้าเข้าคลังแล้ว")
            return redirect('solar_po_list')

        form = SolarPurchaseOrderForm(request.POST, instance=po)
        formset = SolarOrderItemFormSet(request.POST, instance=po)

        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()

            total = sum(item.total_cost for item in po.items.all() if item.total_cost)
            po.total_amount = total
            po.save()

            messages.success(request, f"✅ แก้ไขใบสั่งซื้อ {po.code} เรียบร้อยแล้ว")
            return redirect('solar_po_list')
        else:
            messages.error(request, "❌ กรุณาตรวจสอบข้อมูลให้ครบถ้วน")
    else:
        form = SolarPurchaseOrderForm(instance=po)
        formset = SolarOrderItemFormSet(instance=po)

    first_item = po.items.first()
    po_type = first_item.product.product_type if first_item and first_item.product else 'RM'

    solar_products = SolarProduct.objects.filter(is_active=True, product_type=po_type)
    suppliers = Supplier.objects.all()

    return render(request, 'solar_purchasing/solar_po_form.html', {
        'form': form,
        'formset': formset,
        'po': po,
        'is_manager': is_manager,
        'products': solar_products,
        'suppliers': suppliers,
        'po_type': po_type,
        'is_readonly': is_readonly  # 🌟 [NEW] ส่งค่าตัวแปรนี้ไปบอกหน้าจอ HTML ว่าให้ล็อกฟอร์ม
    })

@login_required
def solar_po_approve(request, po_id):
    po = get_object_or_404(SolarPurchaseOrder, id=po_id)
    if is_purchasing_manager(request.user) and po.status == 'DRAFT':
        po.status = 'APPROVED'
        po.save()
        messages.success(request, f"✅ อนุมัติใบสั่งซื้อ {po.code} เรียบร้อยแล้ว! (แจ้งเตือนแผนกคลังสินค้าและบัญชีแล้ว)")
    else:
        messages.error(request, "❌ คุณไม่มีสิทธิ์อนุมัติ หรือสถานะเอกสารไม่ถูกต้อง")
    return redirect('solar_po_list')

@login_required
def solar_po_cancel(request, po_id):
    po = get_object_or_404(SolarPurchaseOrder, id=po_id)
    if is_purchasing_manager(request.user) and po.status in ['DRAFT', 'APPROVED']:
        po.status = 'CANCELLED'
        po.save()
        messages.warning(request, f"⚠️ ยกเลิกใบสั่งซื้อ {po.code} เรียบร้อยแล้ว")
    else:
        messages.error(request, "❌ คุณไม่มีสิทธิ์ยกเลิกเอกสารนี้")
    return redirect('solar_po_list')

@login_required
def solar_po_print(request, po_id):
    if not is_purchasing_staff(request.user):
        return redirect('solar_po_list')

    po = get_object_or_404(SolarPurchaseOrder, id=po_id)

    # 🌟 ดึงข้อมูลบริษัท เพื่อไปทำเป็นหัวกระดาษแบบ Official
    from master_data.models import CompanyInfo
    company = CompanyInfo.objects.first()

    return render(request, 'solar_purchasing/solar_po_print.html', {
        'po': po,
        'company': company
    })

# ==========================================
# ☀️ ระบบใบเตรียมสั่งซื้อโซล่าเซลล์ (Solar PPO)
# ==========================================
@login_required
def solar_ppo_list(request):
    if not is_purchasing_staff(request.user): return redirect('dashboard')
    ppos = SolarPurchasePreparation.objects.all().order_by('-id')
    return render(request, 'solar_purchasing/solar_ppo_list.html', {'ppos': ppos})

@login_required
def solar_ppo_detail(request, pk):
    if not is_purchasing_staff(request.user): return redirect('dashboard')
    ppo = get_object_or_404(SolarPurchasePreparation, pk=pk)

    if request.method == 'POST':
        item_ids = request.POST.getlist('item_id[]')
        supplier_ids = request.POST.getlist('supplier_id[]')
        unit_costs = request.POST.getlist('unit_cost[]')
        quantities = request.POST.getlist('quantity[]')

        supplier_orders = {}
        for i in range(len(item_ids)):
            sup_id = supplier_ids[i]
            if not sup_id: continue
            if sup_id not in supplier_orders: supplier_orders[sup_id] = []
            supplier_orders[sup_id].append({
                'item_id': item_ids[i],
                'cost': unit_costs[i],
                'qty': quantities[i]
            })

        created_po_codes = []
        for sup_id, items in supplier_orders.items():
            supplier = Supplier.objects.filter(id=sup_id).first()
            if not supplier: continue

            now = datetime.datetime.now()
            thai_year = (now.year + 543) % 100
            prefix = f"POS-{thai_year:02d}{now.strftime('%m')}"

            # 🌟 [FIXED] ใช้รหัสของ SolarPurchaseOrder แบบ POS-
            last_po = SolarPurchaseOrder.objects.filter(code__startswith=prefix).order_by('code').last()
            if last_po:
                try: seq = int(last_po.code.split('-')[-1]) + 1
                except: seq = 1
            else:
                seq = 1
            po_code = f"{prefix}-{seq:03d}"

            po = SolarPurchaseOrder.objects.create(
                code=po_code,
                supplier=supplier,
                buyer=getattr(request.user, 'employee', None),
                status='DRAFT',
                total_amount=0,
                note=f"อ้างอิงจากใบขอซื้อ (PPO): {ppo.code}"
            )

            total_amount = Decimal('0.00')
            for item in items:
                ppo_item = SolarPurchasePreparationItem.objects.get(id=item['item_id'])
                qty = Decimal(str(item['qty']).replace(',', ''))
                cost = Decimal(str(item['cost']).replace(',', ''))
                line_total = qty * cost

                SolarPurchaseOrderItem.objects.create(
                    po=po, product=ppo_item.product, quantity=qty,
                    unit_cost=cost, total_cost=line_total
                )
                total_amount += line_total

            po.total_amount = total_amount
            po.save()
            created_po_codes.append(po.code)

        if created_po_codes:
            ppo.status = 'ORDERED'
            ppo.save()
            messages.success(request, f"✅ สร้างใบสั่งซื้อโซล่า (Solar PO) สำเร็จ: {', '.join(created_po_codes)}")
        else:
            messages.warning(request, "⚠️ ไม่มีการสร้างใบสั่งซื้อ กรุณาเลือกร้านค้าและกรอกข้อมูลให้ครบ")

        return redirect('solar_ppo_list')

    suppliers = Supplier.objects.all().order_by('name')
    return render(request, 'solar_purchasing/solar_ppo_detail.html', {'ppo': ppo, 'suppliers': suppliers})

@login_required
def solar_po_receive(request, po_id):
    # เช็คสิทธิ์ว่าใช่พนักงานจัดซื้อ/คลังสินค้าหรือไม่
    if not is_purchasing_staff(request.user):
        messages.error(request, "❌ บัญชีของคุณไม่มีสิทธิ์เข้าถึงระบบรับสินค้า")
        return redirect('solar_po_list')

    # ดึงข้อมูล PO ใบที่ต้องการรับของ
    po = get_object_or_404(SolarPurchaseOrder, id=po_id)

    # 🛑 ดักจับ: ต้องเป็น PO ที่อนุมัติแล้ว และยังรับของไม่ครบเท่านั้น
    if po.status != 'APPROVED' or po.receipt_status == 'COMPLETED':
        messages.error(request, "❌ ไม่สามารถรับสินค้าสำหรับเอกสารใบนี้ได้ (อาจยังไม่อนุมัติ หรือรับของครบแล้ว)")
        return redirect('solar_po_list')

    if request.method == 'POST':
        all_completed = True
        has_received_any = False

        for item in po.items.all():
            # ดึงจำนวนที่สโตร์กรอกมาจากหน้าฟอร์มรับของ HTML
            receive_val = request.POST.get(f'receive_qty_{item.id}')

            if receive_val:
                try:
                    qty_to_receive = Decimal(receive_val)
                    if qty_to_receive > 0:
                        # 1. อัปเดตยอดรับสะสมใน PO Item
                        item.received_qty += qty_to_receive
                        item.save()

                        # 2. บันทึก Stock Movement และบวกยอดสต็อกคงเหลืออัตโนมัติ
                        if item.product:
                            SolarStockMovement.objects.create(
                                product=item.product,
                                quantity=qty_to_receive,
                                movement_type='IN',
                                reference_doc=po.code
                            )
                        has_received_any = True
                except (ValueError, InvalidOperation):
                    pass # ข้ามไปหากกรอกตัวเลขไม่ถูกต้อง

            # ตรวจสอบว่าหลังจากรับของรอบนี้แล้ว ไอเทมนี้รับครบตามจำนวนสั่งหรือยัง
            if item.received_qty < item.quantity:
                all_completed = False

        if has_received_any:
            # 3. อัปเดตสถานะภาพรวมของ PO
            po.receipt_status = 'COMPLETED' if all_completed else 'PARTIAL'
            po.save()
            messages.success(request, f"📦 บันทึกรับสินค้าเข้าคลังสำหรับ {po.code} เรียบร้อยแล้ว")

            # =========================================================
            # 🚀 [NEW] AUTOMATION: ปลดล็อกใบสั่งงานโซล่า (Unlocking Solar Job)
            # =========================================================
            if po.receipt_status == 'COMPLETED' and po.note:
                # นำเข้าโมเดลใบเตรียมสั่งซื้อเพื่อวิ่งย้อนกลับไปหางานต้นทาง
                from solar_jobs.models import SolarPurchasePreparation

                # เช็คว่ามีโค้ด PPO ไหนบ้างที่อยู่ในหมายเหตุของใบสั่งซื้อนี้
                ppos = SolarPurchasePreparation.objects.all()
                for ppo in ppos:
                    if ppo.code in po.note:
                        job = ppo.job
                        # ถ้างานต้นทางติดสถานะรอของอยู่ ให้ปลดล็อกทันที!
                        if job and job.status == 'WAITING_PURCHASE':
                            job.status = 'WAITING_STORE'
                            job.save()
                            messages.success(request, f"🚀 ออโต้เมชั่น: สินค้าครบแล้ว! ระบบได้ปลดล็อกใบสั่งงาน {job.code} กลับไปรอเบิกเรียบร้อย")
                        break # เจอใบที่ตรงแล้ว หยุดการค้นหาลูปนี้ได้เลย
            # =========================================================

        else:
            messages.warning(request, "⚠️ ไม่มียอดรับสินค้าใหม่ถูกบันทึก")

        return redirect('solar_po_list')

    # 🌟 นี่คือบรรทัดที่หายไปครับ ต้องมีบรรทัดนี้เพื่อเปิดหน้าจอ 🌟
    return render(request, 'solar_purchasing/solar_po_receive.html', {'po': po})