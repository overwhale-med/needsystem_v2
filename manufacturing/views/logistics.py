import math
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

from manufacturing.models import ProductionOrder, Transporter, DeliveryStatus, LogisticsClaim
from master_data.models import CompanyInfo
from accounting.models import Expense

# Helper แปลงตัวเลขเป็นตัวหนังสือ (บาทถ้วน)
def get_thai_baht_text(number):
    if number == 0: return "ศูนย์บาทถ้วน"
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
            if val == 0: continue
            if pos == 0 and val == 1 and length > 1: res += "เอ็ด"
            elif pos == 1 and val == 1: res += "สิบ"
            elif pos == 1 and val == 2: res += "ยี่สิบ"
            else: res += numbers[val] + positions[pos]
        return res

    res = ""
    if baht > 0: res += read_num(baht) + "บาท"
    if satang > 0: res += read_num(satang) + "สตางค์"
    else: res += "ถ้วน"
    return res

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
                if delivery_date_str: order.delivery_date = parse_date(delivery_date_str)
                try: order.delivery_fee = Decimal(str(delivery_fee).replace(',', ''))
                except: order.delivery_fee = Decimal('0.00')
                messages.success(request, f"🚛 จ่ายงาน {order.code} ให้ทีมขนส่งและระบุค่าจ้างเรียบร้อยแล้ว!")

        elif action == 'update_status':
            delivery_status_id = request.POST.get('delivery_status')
            if delivery_status_id:
                status_obj = DeliveryStatus.objects.get(id=delivery_status_id)
                is_delivered_success = status_obj.name in ['ส่งมอบสำเร็จ', 'ลูกค้าเซ็นรับแล้ว', 'จัดส่งเรียบร้อย']

                if is_delivered_success:
                    has_proof = order.proof_of_delivery or 'proof_of_delivery' in request.FILES
                    if has_proof:
                        if 'proof_of_delivery' in request.FILES:
                            order.proof_of_delivery = request.FILES['proof_of_delivery']
                        order.delivery_status_id = delivery_status_id
                        messages.success(request, "📦 อัปเดตสถานะการส่งมอบสำเร็จ!")
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
    amount_text = get_thai_baht_text(order.quotation_ref.grand_total) if order.quotation_ref and order.quotation_ref.grand_total else ""
    return render(request, 'manufacturing/print_delivery_note.html', {'order': order, 'company': company, 'amount_text': amount_text})

@login_required
def print_consent_form(request, pk):
    order = get_object_or_404(ProductionOrder, pk=pk)
    company = CompanyInfo.objects.first()
    return render(request, 'manufacturing/print_consent_form.html', {'order': order, 'company': company})

@login_required
def print_site_checklist(request, pk):
    order = get_object_or_404(ProductionOrder, pk=pk)
    company = CompanyInfo.objects.first()
    return render(request, 'manufacturing/print_site_checklist.html', {'order': order, 'company': company})

@login_required
def print_logistics_claim(request, pk):
    claim = get_object_or_404(LogisticsClaim, pk=pk)
    company = CompanyInfo.objects.first()
    jobs = claim.production_orders.all()
    amount_text = get_thai_baht_text(claim.total_amount)
    return render(request, 'manufacturing/print_logistics_claim.html', {'claim': claim, 'jobs': jobs, 'company': company, 'amount_text': amount_text})

@login_required
def logistics_history_log(request):
    orders = ProductionOrder.objects.select_related('product', 'branch', 'transporter', 'delivery_status', 'salesperson').filter(
        Q(delivery_status__name__in=['ส่งมอบสำเร็จ', 'ลูกค้าเซ็นรับแล้ว', 'จัดส่งเรียบร้อย']) | Q(is_onsite=True, status='COMPLETED')
    ).order_by('-delivery_date', '-finish_date', '-id')

    search_q = request.GET.get('q', '')
    search_transporter = request.GET.get('transporter', '')
    start_date = request.GET.get('start_date', '')
    end_date = request.GET.get('end_date', '')

    if search_q: orders = orders.filter(Q(code__icontains=search_q) | Q(customer_name__icontains=search_q) | Q(product__name__icontains=search_q))
    if search_transporter: orders = orders.filter(transporter_id=search_transporter)
    if start_date: orders = orders.filter(delivery_date__gte=start_date)
    if end_date: orders = orders.filter(delivery_date__lte=end_date)

    paginator = Paginator(orders, 30)
    page_obj = paginator.get_page(request.GET.get('page', 1))
    transporters = Transporter.objects.all().order_by('name')

    return render(request, 'manufacturing/logistics_history_log.html', {'page_obj': page_obj, 'search_q': search_q, 'search_transporter': search_transporter, 'start_date': start_date, 'end_date': end_date, 'transporters': transporters})

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
    return render(request, 'manufacturing/logistics_claim_history.html', {'page_obj': page_obj, 'start_date': start_date, 'end_date': end_date, 'q_transporter': q_transporter, 'q_job': q_job, 'q_customer': q_customer})

@login_required
def ajax_add_transporter(request):
    if request.method == 'POST':
        import json
        data = json.loads(request.body)
        name = data.get('name')
        if name:
            obj, _ = Transporter.objects.get_or_create(name=name)
            return JsonResponse({'success': True, 'id': obj.id, 'name': obj.name})
    return JsonResponse({'success': False})

@login_required
def ajax_add_transporter_full(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        if name:
            obj, created = Transporter.objects.get_or_create(name=name, defaults={
                'driver_name': request.POST.get('driver_name', ''), 'vehicle_plate': request.POST.get('vehicle_plate', ''),
                'address': request.POST.get('address', ''), 'bank_account': request.POST.get('bank_account', ''), 'id_card_image': request.FILES.get('id_card_image')
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
        Expense.objects.create(title=f"จ่ายค่าขนส่ง/ทีมรถ (ใบเบิก: {claim.code}) - {claim.transporter.name}", amount=claim.total_amount, date=timezone.now().date())
        messages.success(request, f"✅ ทำจ่ายเงินใบเบิก {claim.code} จำนวน ฿{claim.total_amount:,.2f} สำเร็จ! และระบบบันทึกลงบัญชีรายจ่ายให้อัตโนมัติแล้วค่ะ")
    return redirect('logistics_claim_history')