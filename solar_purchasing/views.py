import datetime
import json
from decimal import Decimal, InvalidOperation
from solar_inventory.models import SolarStockMovement # ต้อง import เพิ่มเพื่อบันทึกประวัติการเข้าออกคลัง
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from django.utils import timezone
from django.db import transaction

from .models import SolarPurchaseOrder, SolarPurchaseOrderItem
from .models import SolarPurchasePreparation, SolarPurchasePreparationItem
from .forms import SolarPurchaseOrderForm, SolarOrderItemFormSet
from master_data.models import Supplier

# 🌟 [FIXED] นำเข้า SolarProduct และระบบ PPO จากฝั่งโซล่าเซลล์
from solar_inventory.models import SolarProduct

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

def is_inventory_staff(user):
    if user.is_superuser: return True
    if hasattr(user, 'employee') and user.employee:
        dept = getattr(user.employee.department, 'name', '')
        if 'คลังสินค้า' in dept or 'สโตร์' in dept or 'Inventory' in dept or 'Store' in dept:
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

# 🌟 [NEW] ฟังก์ชันสำหรับพิมพ์ "ใบขอเสนอราคา (RFQ)" แบบไม่มีราคา
@login_required
def solar_po_print_rfq(request, po_id):
    if not is_purchasing_staff(request.user):
        return redirect('solar_po_list')

    po = get_object_or_404(SolarPurchaseOrder, id=po_id)

    from master_data.models import CompanyInfo
    company = CompanyInfo.objects.first()

    return render(request, 'solar_purchasing/solar_po_rfq_print.html', {
        'po': po,
        'company': company
    })

# ==========================================
# ☀️ ระบบใบเตรียมสั่งซื้อโซล่าเซลล์ (Solar PPO) - อัปเกรดตะกร้ารวม (แยกใบด้วย Snapshot)
# ==========================================
@login_required
def solar_ppo_list(request):
    if not is_purchasing_staff(request.user): return redirect('dashboard')

    # 🌟 [FIXED] ดึงข้อมูล PPO และ prefetch ตาราง items (Snapshot) ที่เราเพิ่งสร้าง
    ppos = SolarPurchasePreparation.objects.prefetch_related('items').all().order_by('-id')

    for ppo in ppos:
        total_amount = Decimal(0)
        total_needed_qty = Decimal(0)
        ordered_qty = Decimal(0)

        # 🌟 [NEW] วนลูปอ่านข้อมูลจากตาราง PPO Items โดยตรง (เลิกอ่านจาก JOB แล้ว)
        for item in ppo.items.all():
            qty = Decimal(str(item.quantity_needed))
            ord_qty = Decimal(str(item.ordered_qty))
            cost = Decimal(str(item.product.cost_price))

            total_needed_qty += qty
            ordered_qty += ord_qty

            # คำนวณเงินประเมินเฉพาะส่วนที่ "ค้างสั่ง"
            remaining = qty - ord_qty
            if remaining > 0:
                total_amount += remaining * cost

        # นับจำนวน PO ที่เคยเปิดไปแล้วสำหรับ PPO ตะกร้านี้
        created_pos = SolarPurchaseOrder.objects.filter(ppo_ref=ppo.code).exclude(status='CANCELLED')
        ppo.created_pos_list = created_pos
        ppo.created_pos_count = created_pos.count()
        # กรณีมีการผูก JOB ไว้หลายตัว (แบบเดิม) หรือแบบใหม่ที่ผูกตัวเดียว
        ppo.job_count = ppo.solar_jobs.count() if hasattr(ppo, 'solar_jobs') else (1 if getattr(ppo, 'job', None) else 0)

        ppo.total_estimated_cost = total_amount
        ppo.progress_percent = int((ordered_qty / total_needed_qty * 100)) if total_needed_qty > 0 else 0
        if ppo.progress_percent > 100: ppo.progress_percent = 100

        # จัดสีสถานะ
        if total_needed_qty == 0: ppo.po_status = 'EMPTY'
        elif ordered_qty == 0: ppo.po_status = 'RED'
        elif ppo.progress_percent >= 100: ppo.po_status = 'GREEN'
        else: ppo.po_status = 'ORANGE'

    return render(request, 'solar_purchasing/solar_ppo_list.html', {'ppos': ppos})

@login_required
def solar_ppo_detail(request, pk):
    if not is_purchasing_staff(request.user): return redirect('dashboard')
    ppo = get_object_or_404(SolarPurchasePreparation, pk=pk)

    if request.method == 'POST':
        order_data_json = request.POST.get('order_data', '{}')
        try: order_data = json.loads(order_data_json)
        except:
            messages.error(request, "❌ ข้อมูล JSON ไม่ถูกต้อง")
            return redirect('solar_ppo_detail', pk=pk)

        created_po_codes = []
        for sup_id, items in order_data.items():
            if not items: continue
            supplier = Supplier.objects.filter(id=sup_id).first()
            if not supplier: continue

            now = datetime.datetime.now()
            thai_year = (now.year + 543) % 100
            prefix = f"POS-{thai_year:02d}{now.strftime('%m')}"

            last_po = SolarPurchaseOrder.objects.filter(code__startswith=prefix).order_by('code').last()
            if last_po:
                try: seq = int(last_po.code.split('-')[-1]) + 1
                except: seq = 1
            else:
                seq = 1
            po_code = f"{prefix}-{seq:03d}"

            po = SolarPurchaseOrder.objects.create(
                code=po_code, supplier=supplier,
                buyer=getattr(request.user, 'employee', None),
                ppo_ref=ppo.code, status='DRAFT', total_amount=0
            )

            total_amount = Decimal('0.00')
            for item in items:
                prod = SolarProduct.objects.filter(id=item['id']).first()
                if prod:
                    qty = Decimal(str(item['qty']))
                    cost = Decimal(str(item['cost']))
                    line_total = qty * cost
                    SolarPurchaseOrderItem.objects.create(po=po, product=prod, quantity=qty, unit_cost=cost, total_cost=line_total)
                    total_amount += line_total

                    # 🌟 [NEW] อัปเดตยอดสั่งซื้อกลับไปที่ PPO Item ทันที
                    ppo_item = ppo.items.filter(product=prod).first()
                    if ppo_item:
                        ppo_item.ordered_qty += qty
                        ppo_item.save()

            po.total_amount = total_amount
            po.save()
            created_po_codes.append(po.code)

        if created_po_codes:
            messages.success(request, f"✅ สร้างใบสั่งซื้อ (PO) สำเร็จ: {', '.join(created_po_codes)}")

            # 🌟 [NEW] เช็คว่าสั่งครบหมดแล้วหรือยัง ถ้าครบให้เปลี่ยนสถานะ PPO เป็น ORDERED
            all_ordered = True
            for item in ppo.items.all():
                if item.ordered_qty < item.quantity_needed:
                    all_ordered = False
                    break

            if all_ordered:
                ppo.status = 'ORDERED'
                ppo.save()

        else: messages.warning(request, "⚠️ ไม่มีการสร้างใบสั่งซื้อใหม่")
        return redirect('solar_ppo_detail', pk=pk)

    # 🌟 [NEW] ดึงข้อมูลจาก PPO Items โดยตรง (Snapshot)
    materials_list = []
    grand_total = Decimal(0)
    all_suppliers = list(Supplier.objects.all().values('id', 'name'))
    total_remaining_all = Decimal(0)

    for item in ppo.items.all():
        mat = item.product
        needed = float(item.quantity_needed)
        ordered = float(item.ordered_qty)
        remaining = needed - ordered if needed - ordered > 0 else 0

        total_remaining_all += Decimal(str(remaining))

        suppliers = []
        if hasattr(mat, 'supplier') and mat.supplier:
            suppliers.append({'id': mat.supplier.id, 'name': mat.supplier.name, 'cost': float(mat.cost_price), 'is_default': True})

        materials_list.append({
             'id': mat.id, 'code': mat.code, 'name': mat.name, 'needed': needed, 'ordered': ordered,
             'remaining': remaining, 'cost': float(mat.cost_price), 'suppliers': suppliers
        })

        # ค้นหายอดเงินประเมินเฉพาะส่วนที่ "ค้างสั่ง"
        if remaining > 0:
            grand_total += Decimal(str(remaining)) * Decimal(str(mat.cost_price))

    is_fully_ordered = (total_remaining_all == 0)
    all_suppliers_json = json.dumps(all_suppliers)

    created_pos = SolarPurchaseOrder.objects.filter(ppo_ref=ppo.code).exclude(status='CANCELLED')

    return render(request, 'solar_purchasing/solar_ppo_detail.html', {
        'ppo': ppo,
        'materials_list': materials_list,
        'grand_total': grand_total,
        'all_suppliers_json': all_suppliers_json,
        'all_suppliers': all_suppliers,
        'created_pos': created_pos,
        'is_fully_ordered': is_fully_ordered
    })

# 🌟 ฟังก์ชันสำหรับให้จัดซื้อกดยกเลิกใบ PPO
@login_required
def solar_ppo_cancel(request, pk):
    if not is_purchasing_staff(request.user):
        return redirect('dashboard')

    ppo = get_object_or_404(SolarPurchasePreparation, pk=pk)

    if request.method == 'POST':
        ppo.status = 'CANCELLED'
        ppo.save()

        # 🌟 คืนค่าสถานะให้ JOB ในตะกร้านี้ (ปลดล็อกกลับไปที่สโตร์)
        if hasattr(ppo, 'job') and ppo.job:
            ppo.job.is_waiting_purchase = False
            if ppo.job.status == 'WAITING_PURCHASE':
                ppo.job.status = 'WAITING_STORE'
            ppo.job.save()

        messages.success(request, f"✅ ยกเลิกใบขอซื้อ (PPO) รหัส {ppo.code} เรียบร้อยแล้ว (ระบบส่งงานกลับไปให้สโตร์ตรวจสอบใหม่แล้ว)")

    return redirect('solar_ppo_list')

# ==========================================
# 📦 ระบบรับสินค้าเข้าคลัง (Receive PO)
# ==========================================
@login_required
@transaction.atomic  # 🌟 [NEW] เพิ่มบรรทัดนี้เพื่อสร้างตู้เซฟฐานข้อมูล
def solar_po_receive(request, po_id):
    if not is_inventory_staff(request.user):
        messages.error(request, "❌ บัญชีของคุณไม่มีสิทธิ์เข้าถึงระบบรับสินค้า (สำหรับแผนกคลังสินค้าเท่านั้น)")
        return redirect('dashboard')

    po = get_object_or_404(SolarPurchaseOrder, id=po_id)

    if po.status != 'APPROVED' or po.receipt_status == 'COMPLETED':
        messages.error(request, "❌ ไม่สามารถรับสินค้าสำหรับเอกสารใบนี้ได้ (อาจยังไม่อนุมัติ หรือรับของครบแล้ว)")
        return redirect('solar_po_list')

    if request.method == 'POST':
        # 🌟 [NEW] ดักจับการอัปโหลดไฟล์ (บังคับต้องแนบรูปใบส่งของถ้ายังไม่มี)
        if not po.delivery_note_image and 'delivery_note_image' not in request.FILES:
            messages.error(request, "❌ กรุณาแนบไฟล์ภาพใบส่งของก่อนกดยืนยันรับสินค้าเข้าคลัง")
            return redirect('solar_po_receive', po_id=po.id)

        # 🌟 ดักจับการอัปโหลดไฟล์ภาพใบส่งของ (เก็บเข้าฝั่ง PO)
        if 'delivery_note_image' in request.FILES:
            po.delivery_note_image = request.FILES['delivery_note_image']

        all_completed = True
        has_received_any = False

        # นำเข้าโมเดลเอกสารคลังสินค้า
        from solar_inventory.models import SolarInventoryDoc

        # เตรียมตัวแปรหัวเอกสารใบรับของ (GR) ไว้ก่อน
        gr_doc = None

        for item in po.items.all():
            receive_val = request.POST.get(f'receive_qty_{item.id}')

            if receive_val:
                try:
                    qty_to_receive = Decimal(receive_val)
                    if qty_to_receive > 0:

                        # ถ้ายังไม่เคยสร้างหัวบิล GR ในรอบบิลนี้ ให้สร้างขึ้นมาก่อนเลย 1 ใบ
                        if not gr_doc:
                            gr_doc = SolarInventoryDoc.objects.create(
                                doc_type='GR',
                                reference=f"POS: {po.code}",
                                description=f"รับสินค้าเข้าคลังจากใบสั่งซื้อ {po.code}",
                                created_by=request.user
                            )
                            # 🌟 [NEW] สำเนาไฟล์ภาพใบส่งของที่อัปโหลด มาเซฟลงลิ้นชักของ GR ด้วย
                            if 'delivery_note_image' in request.FILES:
                                gr_doc.slip_image = request.FILES['delivery_note_image']
                                gr_doc.save()

                        # บันทึกยอดรับของสะสมในรายการ
                        item.received_qty += qty_to_receive
                        item.save()

                        # บันทึกสต็อกการ์ด (Stock Movement)
                        if item.product:
                            SolarStockMovement.objects.create(
                                doc=gr_doc,  # ผูกประวัติเข้ากับใบ GR
                                product=item.product,
                                quantity=qty_to_receive,
                                movement_type='IN',
                                reference_doc=po.code
                            )
                        has_received_any = True
                except (ValueError, InvalidOperation):
                    pass

            if item.received_qty < item.quantity:
                all_completed = False

        if has_received_any:
            po.receipt_status = 'COMPLETED' if all_completed else 'PARTIAL'
            po.save()
            messages.success(request, f"📦 บันทึกรับสินค้าเข้าคลังและสร้างเอกสาร {gr_doc.doc_no} เรียบร้อยแล้ว")

            # 🚀 AUTOMATION: ปลดล็อกใบสั่งงานโซล่า
            if po.receipt_status == 'COMPLETED' and po.ppo_ref:
                ppo = SolarPurchasePreparation.objects.filter(code=po.ppo_ref).first()
                if ppo:
                    if hasattr(ppo, 'job') and ppo.job:
                        ppo.job.is_waiting_purchase = False
                        if ppo.job.status == 'WAITING_PURCHASE':
                            ppo.job.status = 'WAITING_STORE'
                        ppo.job.save()
                    messages.success(request, f"🚀 ออโต้เมชั่น: สินค้าครบแล้ว! ระบบได้ปลดล็อกใบสั่งงานที่ผูกกับ PPO {ppo.code} กลับไปให้สโตร์เรียบร้อย")

        else:
            # ถ้าไม่ได้กรอกยอดรับของ แต่มีการอัปโหลดรูป ให้เซฟรูปอย่างเดียว
            if 'delivery_note_image' in request.FILES:
                po.save()
                messages.success(request, "✅ อัปโหลดภาพใบส่งของเรียบร้อยแล้ว (ยังไม่มีการรับยอดสินค้า)")
            else:
                messages.warning(request, "⚠️ ไม่มียอดรับสินค้าใหม่ถูกบันทึก")

        return redirect('solar_po_list')

    return render(request, 'solar_purchasing/solar_po_receive.html', {'po': po})


# ==========================================
# 💸 ระบบบันทึกการชำระเงิน (Payment Tracking) โซล่าเซลล์
# ==========================================
@login_required
def solar_po_payment(request, po_id):
    if not (is_purchasing_staff(request.user) or request.user.is_superuser):
        messages.error(request, "❌ บัญชีของคุณไม่มีสิทธิ์เข้าถึงระบบชำระเงิน")
        return redirect('solar_po_list')

    po = get_object_or_404(SolarPurchaseOrder, id=po_id)

    from .models import SolarPurchaseOrderPayment
    payments = po.payments.all().order_by('-created_at')
    total_paid = sum(p.amount for p in payments)
    balance = float(po.total_amount) - float(total_paid)

    if request.method == 'POST':
        amount_str = request.POST.get('amount', '0').replace(',', '')
        try: amount = float(amount_str)
        except ValueError: amount = 0

        if amount > 0 and amount <= balance:
            payment_record = SolarPurchaseOrderPayment(
                po=po,
                payment_date=request.POST.get('payment_date', timezone.now().date()),
                amount=amount,
                payment_method=request.POST.get('payment_method', 'โอนเงินผ่านธนาคาร'),
                note=request.POST.get('note', '')
            )

            if 'slip_image' in request.FILES:
                 payment_record.slip_image = request.FILES['slip_image']

            payment_record.save()

            new_total_paid = float(total_paid) + float(amount)
            if new_total_paid >= float(po.total_amount):
                po.payment_status = 'PAID'
            else:
                po.payment_status = 'DEPOSIT'
            po.save()

            from accounting.models import Expense
            Expense.objects.create(
                title=f"ทำจ่ายใบสั่งซื้อโซล่า #{po.code} (PV: {payment_record.pv_code})",
                amount=amount,
                date=payment_record.payment_date,
                note=f"จ่ายให้ร้าน {po.supplier.name if po.supplier else po.supplier_name_free_text} - {payment_record.note}"
            )

            messages.success(request, f"✅ บันทึกทำจ่ายเงินโซล่าเซลล์ {amount:,.2f} บาท สำเร็จ! ออก PV เลขที่ {payment_record.pv_code} และลงบัญชีเรียบร้อย")
            return redirect('accounting_verification_hub', task_type='solar_po_payments')
        else:
            messages.error(request, "❌ จำนวนเงินไม่ถูกต้อง หรือยอดเกินที่ค้างชำระ")
            return redirect('solar_po_list')

    return render(request, 'solar_purchasing/solar_po_payment.html', {
        'po': po,
        'payments': payments,
        'total_paid': total_paid,
        'balance': balance
    })