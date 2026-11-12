import datetime
from decimal import Decimal
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from django.core.paginator import Paginator
from django.db import transaction
from django.http import JsonResponse
from django.urls import reverse

from manufacturing.models import (
    ProductionOrder, ProductionOrderMaterial, BOM, Branch, MfgBranch, Salesperson,
    ProductionStatus, ProductionTeam, DeliveryStatus, QCInspectionLog, QCReceiptDoc,
    QCPassedMedia, QCFailedMedia, BlueprintClaim, BlueprintLog, BlueprintClaimSplit
)
from master_data.models import CompanyInfo
from inventory.models import Product, StockMovement
from accounting.models import Expense

# ==========================================
# 🌟 รายการใบสั่งผลิต (Production List)
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
        'product', 'quotation_ref', 'salesperson', 'production_team', 'delivery_status', 'transporter', 'branch'
    ).prefetch_related('completed_departments').all().order_by('-id')

    if start_date: orders = orders.filter(start_date__gte=start_date)
    if end_date: orders = orders.filter(start_date__lte=end_date)
    if search_status: orders = orders.filter(status=search_status)
    if search_branch: orders = orders.filter(branch_id=search_branch)
    if search_q: orders = orders.filter(Q(code__icontains=search_q) | Q(customer_name__icontains=search_q) | Q(quotation_ref__code__icontains=search_q))
    if search_salesperson: orders = orders.filter(salesperson_id=search_salesperson)
    if search_team: orders = orders.filter(production_team_id=search_team)

    active_qs = orders.filter(is_closed=False)
    closed_qs = orders.filter(is_closed=True)

    active_page_num = request.GET.get('active_page', 1)
    active_orders = Paginator(active_qs, 10).get_page(active_page_num)

    closed_page_num = request.GET.get('closed_page', 1)
    closed_orders = Paginator(closed_qs, 10).get_page(closed_page_num)

    url_params = request.GET.copy()
    if 'active_page' in url_params: del url_params['active_page']
    if 'closed_page' in url_params: del url_params['closed_page']

    context = {
        'active_orders': active_orders, 'closed_orders': closed_orders,
        'branches': MfgBranch.objects.all().order_by('name'), 'prod_statuses': ProductionStatus.objects.all().order_by('sequence', 'id'),
        'prod_teams': ProductionTeam.objects.all().order_by('name'), 'deliv_statuses': DeliveryStatus.objects.all().order_by('name'),
        'salespersons': Salesperson.objects.all().order_by('name'), 'start_date': start_date, 'end_date': end_date,
        'search_q': search_q, 'search_branch': search_branch, 'search_salesperson': search_salesperson,
        'search_team': search_team, 'search_status': search_status, 'system_status_choices': ProductionOrder.STATUS_CHOICES,
        'filter_string': url_params.urlencode(), 'total_departments_count': ProductionStatus.objects.count(),
    }
    return render(request, 'manufacturing/production_list.html', context)

@login_required
def production_create(request):
    fg_with_bom = [bom.product for bom in BOM.objects.select_related('product').all()]
    if request.method == 'POST':
        product_id = request.POST.get('product')
        if product_id:
            order = ProductionOrder(
                product=get_object_or_404(Product, id=product_id), quantity=1, status='NEW_JOB',
                note=request.POST.get('note', ''), customer_name=request.POST.get('customer_name', ''),
                is_onsite=request.POST.get('is_onsite') == 'on', responsible_person=getattr(request.user, 'employee', None)
            )
            if request.POST.get('start_date'): order.start_date = request.POST.get('start_date')
            if request.POST.get('delivery_date'): order.delivery_date = request.POST.get('delivery_date')
            if request.POST.get('salesperson'): order.salesperson_id = request.POST.get('salesperson')
            order.save()
            messages.success(request, f"✅ สร้างใบสั่งผลิต {order.code} สำเร็จ!")
            return redirect('planner_board')
        else: messages.error(request, "❌ กรุณาเลือกแบบบ้านที่ต้องการผลิต")
    return render(request, 'manufacturing/production_form.html', {
        'fg_with_bom': fg_with_bom, 'branches': Branch.objects.all().order_by('name'),
        'salespersons': Salesperson.objects.select_related('branch').all().order_by('name')
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
def start_actual_production(request, pk):
    return redirect('production_list')

@login_required
def production_detail(request, pk):
    order = get_object_or_404(ProductionOrder, pk=pk)
    return render(request, 'manufacturing/production_detail.html', {
        'order': order, 'materials': order.materials.all(),
        'has_bom': BOM.objects.filter(product=order.product).exists(),
        'raw_materials': Product.objects.filter(product_type='RM', is_active=True).order_by('code')
    })

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

    qc_doc = QCReceiptDoc.objects.create(production_order=order, product=main_product, quantity=Decimal(str(order.quantity)), created_by=request.user)
    StockMovement.objects.create(doc=None, reference_doc=qc_doc.doc_no, note=desc_text, product=main_product, quantity=Decimal(str(order.quantity)), movement_type='IN', created_by=request.user)

    order.status = 'COMPLETED'
    order.finish_date = timezone.now().date()
    order.save()

    messages.success(request, f"🎉 สำเร็จ! รับ {main_product.name} ({order.quantity} หลัง) เข้าคลังเรียบร้อยแล้ว!")
    return redirect('production_list')

@login_required
def add_additional_material(request, pk):
    order = get_object_or_404(ProductionOrder, pk=pk)
    if request.method == 'POST':
        product_id = request.POST.get('raw_material')
        try: qty = Decimal(request.POST.get('quantity', '0'))
        except: qty = Decimal('0')
        if product_id and qty > 0:
            rm = get_object_or_404(Product, pk=product_id)
            ProductionOrderMaterial.objects.create(production_order=order, raw_material=rm, quantity=qty, is_additional=True)
            messages.success(request, f"➕ เพิ่มวัตถุดิบส่วนเพิ่ม: {rm.name} จำนวน {qty} ลงในบิลเรียบร้อยแล้ว")
        else: messages.error(request, "❌ กรุณาเลือกวัตถุดิบและใส่จำนวนให้ถูกต้อง")
    return redirect(request.META.get('HTTP_REFERER', 'production_list'))

@login_required
def delete_production_material(request, pk):
    mat = get_object_or_404(ProductionOrderMaterial, pk=pk)
    order_id = mat.production_order.id
    if mat.production_order.status != 'COMPLETED':
        mat.delete()
        messages.success(request, "🗑️ ลบรายการวัตถุดิบออกจากบิลผลิตเรียบร้อยแล้ว")
    else: messages.error(request, "❌ ไม่สามารถลบได้เนื่องจากใบสั่งผลิตนี้ดำเนินการเสร็จสิ้นแล้ว")
    return redirect(request.META.get('HTTP_REFERER', 'production_list'))

@login_required
def production_print(request, po_id):
    po = get_object_or_404(ProductionOrder, id=po_id)
    return render(request, 'manufacturing/production_print.html', {'po': po, 'bom': BOM.objects.filter(product=po.product).first(), 'company': CompanyInfo.objects.first()})

@login_required
def generate_pos_from_production(request, pk):
    messages.info(request, "ฟังก์ชันนี้กำลังอยู่ระหว่างการพัฒนาเพิ่มเติม")
    return redirect('ppo_prepare')

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
            if redirect_to == 'inventory_board': return redirect('inventory_board')

        if 'completed_departments' in request.POST: order.completed_departments.set(request.POST.getlist('completed_departments'))
        elif action in ['update_progress', 'qc_complete_and_receive']: order.completed_departments.clear()

        if 'production_team' in request.POST: order.production_team_id = request.POST.get('production_team') or None
        if 'branch' in request.POST: order.branch_id = request.POST.get('branch') or None

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

            if action == 'qc_complete_and_receive' and order.status != 'COMPLETED':
                qc_doc = QCReceiptDoc.objects.create(production_order=order, product=order.product, quantity=Decimal(str(order.quantity)), created_by=request.user)
                StockMovement.objects.create(doc=None, reference_doc=qc_doc.doc_no, note=f"รับสินค้า {order.product.name} จาก {order.code} (QC Pass)", product=order.product, quantity=Decimal(str(order.quantity)), movement_type='IN', created_by=request.user)
                order.status = 'COMPLETED'
                order.finish_date = timezone.now().date()
                order.is_qc_passed = True
                messages.success(request, f"🎉 ผ่าน QC และรับ {order.product.name} เข้าคลังแล้ว! งานย้ายไปช่อง W4 พร้อมส่ง")
            else: messages.success(request, f"✅ อัปเดตความคืบหน้า {order.code} เรียบร้อยแล้ว!")

        if request.POST.get('is_closed') == 'on':
            order.is_closed = True
            messages.success(request, f"✅ ปิดจ๊อบ {order.code} อย่างสมบูรณ์แล้ว! (ย้ายไปแท็บประวัติ)")
        elif action in ['update_progress', 'qc_complete_and_receive'] and request.POST.get('is_closed') != 'on' and order.status != 'COMPLETED':
            order.is_closed = False
        order.save()
    return redirect(request.META.get('HTTP_REFERER', 'production_list'))

# ==========================================
# 🌟 ระบบ QC (Quality Control)
# ==========================================
@login_required
def submit_to_qc(request, pk):
    order = get_object_or_404(ProductionOrder, pk=pk)
    if order.status in ['IN_PROGRESS', 'REWORK']:
        order.status = 'WAITING_QC'
        order.save()
        messages.success(request, f"✅ ส่งงาน {order.code} ให้แผนก QC ตรวจสอบเรียบร้อยแล้ว!")
    return redirect('production_head_board')

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
            comments = request.POST.get('comments', '')
            for f in request.FILES.getlist('passed_media'): QCPassedMedia.objects.create(production_order=order, uploaded_by=getattr(request.user, 'employee', None), file=f)
            failed_files = request.FILES.getlist('failed_media')
            if failed_files or comments:
                log, created = QCInspectionLog.objects.get_or_create(production_order=order, round_number=order.rework_count + 1, defaults={'inspector': getattr(request.user, 'employee', None), 'status': 'FAILED', 'comments': comments})
                if not created and comments: log.comments = comments; log.save()
                for f in failed_files: QCFailedMedia.objects.create(qc_log=log, file=f)
            order.save()
            messages.success(request, f"💾 บันทึกความคืบหน้าและรูปภาพสำหรับ {order.code} ลงฐานข้อมูลเรียบร้อยแล้ว!")

        elif action == 'pass':
            allocated_product, _ = Product.objects.get_or_create(code=f"{order.product.code}-{order.code}", defaults={'name': f"{order.product.name} [{order.code}]"[:255], 'category': order.product.category, 'product_type': 'FG', 'sell_price': order.product.sell_price, 'cost_price': order.product.cost_price, 'min_level': 0, 'stock_qty': 0, 'is_active': True, 'image': order.product.image})
            qc_doc = QCReceiptDoc.objects.create(production_order=order, product=allocated_product, quantity=Decimal(str(order.quantity)), created_by=request.user)
            StockMovement.objects.create(doc=None, reference_doc=qc_doc.doc_no, note=f"รับสินค้าจากฝ่ายผลิต {order.code} (ผ่าน QC)", product=allocated_product, quantity=Decimal(str(order.quantity)), movement_type='IN', created_by=request.user)

            order.status = 'COMPLETED'
            order.finish_date = timezone.now().date()
            order.is_qc_passed = True
            order.save()
            QCInspectionLog.objects.create(production_order=order, round_number=order.rework_count + 1, inspector=getattr(request.user, 'employee', None), status='PASSED', comments="ผ่านการตรวจสอบเรียบร้อย")
            for f in request.FILES.getlist('passed_media'): QCPassedMedia.objects.create(production_order=order, uploaded_by=getattr(request.user, 'employee', None), file=f)
            messages.success(request, f"🎉 ตรวจผ่านเรียบร้อย! รับ {allocated_product.name} เข้าคลังแล้ว พร้อมบันทึกคลังภาพ/คลิป")

        elif action == 'fail':
            comments = request.POST.get('comments', '')
            order.rework_count += 1
            order.status = 'REWORK'
            log, _ = QCInspectionLog.objects.get_or_create(production_order=order, round_number=order.rework_count, defaults={'inspector': getattr(request.user, 'employee', None), 'status': 'FAILED', 'comments': comments})
            log.comments, log.inspector = comments, getattr(request.user, 'employee', None)
            if 'defect_image_1' in request.FILES: log.defect_image_1 = request.FILES['defect_image_1']
            if 'defect_image_2' in request.FILES: log.defect_image_2 = request.FILES['defect_image_2']
            log.save()
            for f in request.FILES.getlist('failed_media'): QCFailedMedia.objects.create(qc_log=log, file=f)
            order.save()
            messages.warning(request, f"🚨 ตีกลับงาน {order.code} ให้ช่างแก้ไขเรียบร้อย พร้อมแนบรูป/คลิปตำหนิ (รอบที่ {order.rework_count})")

    return redirect('qc_board')

# ==========================================
# 🌟 ศูนย์ตรวจสอบแบบแปลน (Blueprint Hub)
# ==========================================
@login_required
def blueprint_hub(request):
    current_emp = getattr(request.user, 'employee', None)
    date_range = request.GET.get('date_range', '')
    start_date, end_date = '', ''
    if date_range:
        parts = date_range.split(' - ')
        if len(parts) == 2:
            try:
                d1, m1, y1 = parts[0].strip().split('/')
                start_date = f"{y1}-{m1}-{d1}"
                d2, m2, y2 = parts[1].strip().split('/')
                end_date = f"{y2}-{m2}-{d2}"
            except: pass

    q_job = request.GET.get('q_job', '')
    q_customer = request.GET.get('q_customer', '')
    search_sp = request.GET.get('salesperson', '')
    claim_status = request.GET.get('claim_status', '')

    pending_jobs = ProductionOrder.objects.select_related('product', 'salesperson', 'salesperson__branch').filter(status__in=['WAITING_BLUEPRINT', 'PLANNED'], is_closed=False).order_by('start_date')
    history_jobs = ProductionOrder.objects.select_related('product', 'salesperson', 'salesperson__branch', 'blueprint_approved_by', 'blueprint_claim').filter(blueprint_approved_at__isnull=False)

    if start_date: history_jobs = history_jobs.filter(blueprint_approved_at__date__gte=start_date)
    if end_date: history_jobs = history_jobs.filter(blueprint_approved_at__date__lte=end_date)
    if q_job: history_jobs = history_jobs.filter(code__icontains=q_job)
    if q_customer: history_jobs = history_jobs.filter(customer_name__icontains=q_customer)
    if search_sp: history_jobs = history_jobs.filter(salesperson_id=search_sp)
    if claim_status == 'UNCLAIMED': history_jobs = history_jobs.filter(blueprint_claim__isnull=True)
    elif claim_status in ['PENDING', 'PAID', 'REJECTED']: history_jobs = history_jobs.filter(blueprint_claim__status=claim_status)

    history_jobs = history_jobs.order_by('-blueprint_approved_at')[:100]
    claimable_jobs = ProductionOrder.objects.select_related('salesperson', 'quotation_ref', 'quotation_ref__invoice').filter(blueprint_approved_by=current_emp, blueprint_claim__isnull=True, quotation_ref__invoice__isnull=False).order_by('blueprint_approved_at')
    waiting_invoice_jobs = ProductionOrder.objects.select_related('salesperson', 'quotation_ref').filter(blueprint_approved_by=current_emp, blueprint_claim__isnull=True, quotation_ref__invoice__isnull=True).order_by('blueprint_approved_at')

    return render(request, 'manufacturing/blueprint_hub.html', {
        'pending_jobs': pending_jobs, 'history_jobs': history_jobs, 'claimable_jobs': claimable_jobs,
        'waiting_invoice_jobs': waiting_invoice_jobs, 'claims': BlueprintClaim.objects.filter(employee=current_emp).order_by('-created_at'),
        'salespersons': Salesperson.objects.select_related('branch').all().order_by('name'), 'date_range': date_range,
        'q_job': q_job, 'q_customer': q_customer, 'search_sp': search_sp, 'claim_status': claim_status,
    })

@login_required
def blueprint_workspace(request, pk):
    order = get_object_or_404(ProductionOrder, pk=pk)
    return render(request, 'manufacturing/blueprint_workspace.html', {'order': order, 'materials': order.materials.all(), 'has_bom': BOM.objects.filter(product=order.product).exists(), 'raw_materials': Product.objects.filter(product_type='RM', is_active=True).order_by('code'), 'logs': order.blueprint_logs.all()})

@login_required
def blueprint_approve(request, pk):
    order = get_object_or_404(ProductionOrder, pk=pk)
    if request.method == 'POST':
        order.status = 'WAITING_MATERIALS'
        order.blueprint_approved_by = getattr(request.user, 'employee', None)
        order.blueprint_approved_at = timezone.now()
        order.save()
        BlueprintLog.objects.create(production_order=order, action="ตรวจสอบความถูกต้องของแบบแปลนและโครงสร้างวัตถุดิบ (Approve)", employee=getattr(request.user, 'employee', None))
        messages.success(request, f"✅ ยืนยันความถูกต้องของ JOB {order.code} เรียบร้อย! งานถูกส่งต่อไปยังแผนกสั่งวัตถุดิบแล้วค่ะ")
        return redirect(reverse('blueprint_hub') + '#history')
    return redirect('blueprint_workspace', pk=pk)

@login_required
def upload_blueprint(request, pk):
    order = get_object_or_404(ProductionOrder, pk=pk)
    if request.method == 'POST' and 'blueprint_file' in request.FILES:
        order.blueprint_file = request.FILES['blueprint_file']
        order.save()
        messages.success(request, f"📎 แนบไฟล์แบบแปลน (Blueprint) สำหรับ {order.code} เรียบร้อยแล้ว")
    return redirect('production_detail', pk=order.pk)

@login_required
def blueprint_viewer(request, pk):
    return render(request, 'manufacturing/blueprint_viewer.html', {'order': get_object_or_404(ProductionOrder, pk=pk)})

@login_required
@transaction.atomic
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
                total_amount = Decimal(str(jobs.count())) * rate_per_job
                claim = BlueprintClaim.objects.create(employee=current_emp, total_jobs=jobs.count(), total_amount=total_amount)
                jobs.update(blueprint_claim=claim)

                members = group.members.all()
                l1_count, l2_count = members.filter(group_role='LEVEL1').count() or 1, members.filter(group_role='LEVEL2').count() or 1

                for member in members:
                    share_pct = Decimal('0')
                    if member.group_role == 'LEADER': share_pct = Decimal(str(group.share_leader))
                    elif member.group_role == 'LEVEL1': share_pct = Decimal(str(group.share_level1)) / Decimal(str(l1_count))
                    elif member.group_role == 'LEVEL2': share_pct = Decimal(str(group.share_level2)) / Decimal(str(l2_count))

                    if share_pct > 0:
                        BlueprintClaimSplit.objects.create(claim=claim, employee=member, role_name=member.get_group_role_display(), percentage=share_pct, amount=(total_amount * share_pct) / Decimal('100'))
                messages.success(request, f"💰 สร้างใบตั้งเบิก {claim.code} สำเร็จ! และระบบกระจายยอดเงินให้ลูกทีมอัตโนมัติเรียบร้อยค่ะ")
            else: messages.error(request, "❌ ไม่พบงานที่สามารถตั้งเบิกได้ หรือมีการเบิกไปแล้ว")
        else: messages.warning(request, "⚠️ กรุณาเลือกงานอย่างน้อย 1 รายการ")
    return redirect('blueprint_hub')

@login_required
def print_blueprint_claim(request, pk):
    claim = get_object_or_404(BlueprintClaim, pk=pk)
    splits = claim.splits.all()
    total_split_amount = sum([s.amount for s in splits]) if splits else Decimal('0')
    total_split_percent = sum([s.percentage for s in splits]) if splits else Decimal('0')

    # ดึงฟังก์ชันแปลงตัวเลขเป็นตัวอักษรมาจาก logistics.py
    from .logistics import get_thai_baht_text

    return render(request, 'manufacturing/print_blueprint_claim.html', {
        'claim': claim, 'jobs': claim.production_orders.all(), 'company': CompanyInfo.objects.first(),
        'amount_text': get_thai_baht_text(claim.total_amount),
        'fund_amount': claim.total_amount - total_split_amount, 'fund_percentage': Decimal('100') - total_split_percent,
    })

@login_required
@transaction.atomic
def pay_blueprint_claim(request, claim_id):
    claim = get_object_or_404(BlueprintClaim, pk=claim_id)
    if request.method == 'POST' and claim.status == 'PENDING':
        claim.status = 'PAID'
        claim.save()
        emp_name = claim.employee.first_name if claim.employee else 'ไม่ระบุ'
        Expense.objects.create(title=f"จ่ายค่าแบบแปลน/ทีมช่าง (ใบเบิก: {claim.code}) - {emp_name}", amount=claim.total_amount, date=timezone.now().date())
        messages.success(request, f"✅ ทำจ่ายเงินใบเบิก {claim.code} จำนวน ฿{claim.total_amount:,.2f} สำเร็จ! และระบบบันทึกลงบัญชีรายจ่ายให้อัตโนมัติแล้วค่ะ")
    return redirect('blueprint_hub')

# ==========================================
# 🌟 ศูนย์รวมแฟ้มภาพและประวัติ (Media Hub & Logs)
# ==========================================
@login_required
def media_hub(request, pk):
    order = get_object_or_404(ProductionOrder, pk=pk)
    return render(request, 'manufacturing/media_hub.html', {
        'order': order, 'passed_medias': order.passed_media.all().order_by('-id'),
        'qc_logs': order.qc_logs.prefetch_related('failed_media').order_by('-round_number'),
        'service_tickets': order.service_tickets.all().order_by('-created_at'),
    })

@login_required
def media_hub_list(request):
    search_q = request.GET.get('q', '')
    orders = ProductionOrder.objects.select_related('product', 'salesperson', 'production_team').all().order_by('-id')
    if search_q: orders = orders.filter(Q(code__icontains=search_q) | Q(customer_name__icontains=search_q) | Q(product__name__icontains=search_q))
    return render(request, 'manufacturing/media_hub_list.html', {'orders': orders[:100], 'search_q': search_q})

@login_required
def my_production_log(request):
    emp = getattr(request.user, 'employee', None)
    team = emp.production_team if emp else None
    is_manager = request.user.is_superuser or (emp and emp.business_rank and emp.business_rank.lower() in ['manager', 'director', 'executive'])

    if is_manager:
        orders = ProductionOrder.objects.select_related('product', 'salesperson', 'production_team', 'transporter', 'blueprint_approved_by').filter(
            Q(status__in=['COMPLETED', 'CLOSED']) | Q(is_qc_passed=True) | Q(delivery_status__name__in=['ส่งมอบสำเร็จ', 'ลูกค้าเซ็นรับแล้ว', 'จัดส่งเรียบร้อย'])
        ).order_by('-finish_date', '-id')[:100]
    elif team:
        orders = ProductionOrder.objects.select_related('product', 'salesperson', 'production_team').filter(production_team=team, status__in=['COMPLETED', 'CLOSED']).order_by('-finish_date', '-id')[:100]
    else: orders = ProductionOrder.objects.none()
    return render(request, 'manufacturing/my_production_log.html', {'orders': orders, 'is_manager': is_manager})

@login_required
def my_qc_log(request):
    emp = getattr(request.user, 'employee', None)
    is_manager = request.user.is_superuser or (emp and emp.business_rank and emp.business_rank.lower() in ['manager', 'director', 'executive'])

    if is_manager: qc_logs = QCInspectionLog.objects.select_related('production_order', 'production_order__product', 'inspector').all().order_by('-inspected_at')[:100]
    else: qc_logs = QCInspectionLog.objects.select_related('production_order', 'production_order__product', 'inspector').filter(inspector=emp).order_by('-inspected_at')[:100]
    return render(request, 'manufacturing/my_qc_log.html', {'qc_logs': qc_logs, 'is_manager': is_manager})

# ==========================================
# 🌟 ระบบรับค่าทาง AJAX
# ==========================================
@login_required
def ajax_add_branch(request):
    if request.method == 'POST':
        import json
        name = json.loads(request.body).get('name')
        if name:
            obj, _ = Branch.objects.get_or_create(name=name)
            return JsonResponse({'success': True, 'id': obj.id, 'name': obj.name})
    return JsonResponse({'success': False})

@login_required
def ajax_add_salesperson(request):
    if request.method == 'POST':
        import json
        data = json.loads(request.body)
        name, branch_id = data.get('name'), data.get('branch_id')
        if name and branch_id:
            obj, _ = Salesperson.objects.get_or_create(name=name, branch_id=branch_id)
            return JsonResponse({'success': True, 'id': obj.id, 'name': obj.name, 'branch_id': obj.branch.id})
    return JsonResponse({'success': False})

@login_required
def ajax_add_prod_status(request):
    if request.method == 'POST':
        import json
        name = json.loads(request.body).get('name')
        if name:
            obj, _ = ProductionStatus.objects.get_or_create(name=name, defaults={'sequence': 99})
            return JsonResponse({'success': True, 'id': obj.id, 'name': obj.name})
    return JsonResponse({'success': False})

@login_required
def ajax_add_prod_team(request):
    if request.method == 'POST':
        import json
        name = json.loads(request.body).get('name')
        if name:
            obj, _ = ProductionTeam.objects.get_or_create(name=name)
            return JsonResponse({'success': True, 'id': obj.id, 'name': obj.name})
    return JsonResponse({'success': False})

@login_required
def ajax_add_delivery_status(request):
    if request.method == 'POST':
        import json
        name = json.loads(request.body).get('name')
        if name:
            obj, _ = DeliveryStatus.objects.get_or_create(name=name)
            return JsonResponse({'success': True, 'id': obj.id, 'name': obj.name})
    return JsonResponse({'success': False})

@login_required
def ajax_get_fg_by_category(request):
    category_id = request.GET.get('category_id')
    products = Product.objects.filter(product_type='FG', is_active=True).exclude(code__contains='-JOB')
    if category_id: products = products.filter(category_id=category_id)
    return JsonResponse({'products': list(products.values('id', 'name', 'code'))})