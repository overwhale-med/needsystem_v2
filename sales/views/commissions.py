from decimal import Decimal, ROUND_DOWN
from datetime import timedelta
import pytz
import datetime
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum, Q
from django.db import transaction
from django.core.paginator import Paginator
from django.utils import timezone
from django.utils.dateparse import parse_date

# Models
from sales.models import CommissionClaim, CommissionTicket, CommissionAllocation
from hr.models import Employee
from master_data.models import CompanyInfo

# Services
from sales.services import is_sales_authorized, get_thai_baht_text

@login_required
def commission_board(request):
    if not is_sales_authorized(request.user):
        messages.error(request, "❌ บัญชีของคุณไม่มีสิทธิ์เข้าถึงหน้านี้")
        return redirect('dashboard')

    current_emp = getattr(request.user, 'employee', None)
    is_manager_view = False
    is_supervisor_view = False
    user_groups = list(request.user.groups.values_list('name', flat=True))

    # 🌟 [NEW] เช็กสิทธิ์ Manager จากสวิตช์หน้าเว็บแทนการดมกลิ่นชื่อแผนก "บริหาร"
    if request.user.is_superuser or 'Manager_Team' in user_groups or 'Executive' in user_groups or 'Accounting_Team' in user_groups:
        is_manager_view = True
    elif current_emp:
        rank = current_emp.business_rank.lower() if current_emp.business_rank else ""
        if rank == 'supervisor':
            is_supervisor_view = True

    search_query = request.GET.get('q', '').strip()

    if is_manager_view:
        # 1. ผู้จัดการแผนก: เห็นเฉพาะ 0.5% (ได้คนเดียว ไม่ต้องจัดสรรให้ใคร ไม่มีใครเห็นยอดนี้นอกจากผู้จัดการ)
        tickets_05 = CommissionTicket.objects.filter(ticket_type='0.5%', status='AVAILABLE').select_related('quotation_ref', 'quotation_ref__employee').order_by('-created_at')
        tickets_2 = CommissionTicket.objects.none()
        tickets_3 = CommissionTicket.objects.none()

        if request.user.is_superuser:
            claims_qs = CommissionClaim.objects.all().select_related('requester').order_by('-created_at')
        else:
            claims_qs = CommissionClaim.objects.filter(requester=current_emp).order_by('-created_at')

    elif is_supervisor_view and current_emp and current_emp.department:
        # 2 & 3. หัวหน้าสาขา: เห็นเฉพาะ 2% และ 2.5% ของสาขาตัวเอง
        dept_emps = Employee.objects.filter(department=current_emp.department)
        tickets_05 = CommissionTicket.objects.none()
        tickets_2 = CommissionTicket.objects.filter(ticket_type='2%', status='AVAILABLE', quotation_ref__employee__in=dept_emps).select_related('quotation_ref', 'quotation_ref__employee').order_by('-created_at')
        tickets_3 = CommissionTicket.objects.filter(ticket_type__in=['2.5%', '3%'], status='AVAILABLE', quotation_ref__employee__in=dept_emps).select_related('quotation_ref', 'quotation_ref__employee').order_by('-created_at')
        claims_qs = CommissionClaim.objects.filter(requester=current_emp).order_by('-created_at')

    else:
        # พนักงานขายทั่วไป
        tickets_05 = CommissionTicket.objects.none()
        tickets_2 = CommissionTicket.objects.none()
        tickets_3 = CommissionTicket.objects.none()
        claims_qs = CommissionClaim.objects.filter(requester=current_emp).order_by('-created_at')

    if search_query:
        claims_qs = claims_qs.filter(Q(code__icontains=search_query) | Q(requester__first_name__icontains=search_query) | Q(bank_name__icontains=search_query))

    claims_list = claims_qs[:10]
    sum_05 = sum(t.commission_amount for t in tickets_05)
    sum_2 = sum(t.commission_amount for t in tickets_2)
    sum_3 = sum(t.commission_amount for t in tickets_3)

    return render(request, 'sales/commission_board.html', {
        'tickets_05': tickets_05, 'tickets_2': tickets_2, 'tickets_3': tickets_3,
        'claims': claims_list, 'search_query': search_query,
        'is_manager_view': is_manager_view, 'is_supervisor_view': is_supervisor_view,
        'sum_05': sum_05, 'sum_2': sum_2, 'sum_3': sum_3,
    })

@login_required
def commission_history_list(request):
    if not is_sales_authorized(request.user):
        messages.error(request, "❌ บัญชีของคุณไม่มีสิทธิ์เข้าถึงหน้านี้")
        return redirect('dashboard')

    current_emp = getattr(request.user, 'employee', None)
    is_manager_view = False
    is_supervisor_view = False
    user_groups = list(request.user.groups.values_list('name', flat=True))

    # 🌟 [NEW] เช็กสิทธิ์ Manager จากสวิตช์
    if request.user.is_superuser or 'Manager_Team' in user_groups or 'Executive' in user_groups or 'Accounting_Team' in user_groups:
        is_manager_view = True
    elif current_emp:
        rank = current_emp.business_rank.lower() if current_emp.business_rank else ""
        if rank == 'supervisor':
            is_supervisor_view = True

    team_members = []
    if is_supervisor_view and current_emp and current_emp.department:
        team_members = Employee.objects.filter(department=current_emp.department).order_by('first_name')
    elif is_manager_view:
        team_members = Employee.objects.all().order_by('first_name')

    search_query = request.GET.get('q', '').strip()
    emp_search = request.GET.get('emp', '').strip()
    claim_type = request.GET.get('type', '')
    claim_status = request.GET.get('status', '')

    tz_bkk = pytz.timezone('Asia/Bangkok')
    today_bkk = timezone.now().astimezone(tz_bkk).date()

    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')

    if not start_date or start_date == 'None': start_date = (today_bkk - timedelta(days=29)).strftime('%Y-%m-%d')
    if not end_date or end_date == 'None': end_date = today_bkk.strftime('%Y-%m-%d')

    if is_manager_view:
        if request.user.is_superuser:
            claims_qs = CommissionClaim.objects.all().select_related('requester', 'requester__department').prefetch_related('tickets', 'tickets__quotation_ref', 'tickets__quotation_ref__invoice', 'allocations').order_by('-created_at')
        else:
            claims_qs = CommissionClaim.objects.filter(requester=current_emp).select_related('requester', 'requester__department').prefetch_related('tickets', 'tickets__quotation_ref', 'tickets__quotation_ref__invoice', 'allocations').order_by('-created_at')
    else:
        claims_qs = CommissionClaim.objects.filter(requester=current_emp).select_related('requester', 'requester__department').prefetch_related('tickets', 'tickets__quotation_ref', 'tickets__quotation_ref__invoice', 'allocations').order_by('-created_at')

    if search_query: claims_qs = claims_qs.filter(code__icontains=search_query)
    if emp_search: claims_qs = claims_qs.filter(Q(requester__first_name__icontains=emp_search) | Q(requester__department__name__icontains=emp_search))
    if claim_type: claims_qs = claims_qs.filter(claim_type=claim_type)
    if claim_status: claims_qs = claims_qs.filter(status=claim_status)

    try:
        s_date = parse_date(start_date)
        e_date = parse_date(end_date)
        if s_date and e_date:
            start_dt = tz_bkk.localize(datetime.datetime.combine(s_date, datetime.time.min))
            end_dt = tz_bkk.localize(datetime.datetime.combine(e_date, datetime.time.max))
            claims_qs = claims_qs.filter(created_at__gte=start_dt, created_at__lte=end_dt)
    except: pass

    paginator = Paginator(claims_qs.distinct(), 20)
    page_obj = paginator.get_page(request.GET.get('page'))

    for claim in page_obj:
        claim.paid_total = sum(a.amount for a in claim.allocations.all() if a.status == 'PAID')
        claim.remaining_balance = claim.total_amount - claim.paid_total
        claim.has_pending = any(a.status == 'PENDING' for a in claim.allocations.all())

    return render(request, 'sales/commission_history.html', {
        'page_obj': page_obj, 'search_query': search_query, 'emp_search': emp_search,
        'claim_type': claim_type, 'claim_status': claim_status, 'start_date': start_date, 'end_date': end_date,
        'is_manager_view': is_manager_view, 'is_supervisor_view': is_supervisor_view, 'team_members': team_members,
    })

@login_required
def commission_create_claim(request, claim_type):
    if request.method == 'POST':
        ticket_ids = request.POST.getlist('ticket_ids')
        bank_name = request.POST.get('bank_name')
        bank_account = request.POST.get('bank_account')
        account_name = request.POST.get('account_name')

        if not ticket_ids:
            messages.error(request, "❌ กรุณาเลือกใบคุมสิทธิ์ที่ต้องการเบิกอย่างน้อย 1 รายการ")
            return redirect('commission_board')

        tickets = CommissionTicket.objects.filter(id__in=ticket_ids, status='AVAILABLE')
        total_amount = sum(t.commission_amount for t in tickets)

        if total_amount > 0:
            claim = CommissionClaim.objects.create(
                claim_type=claim_type, requester=getattr(request.user, 'employee', None),
                total_amount=total_amount, bank_name=bank_name, bank_account=bank_account, account_name=account_name
            )
            tickets.update(status='CLAIMING', claim_ref=claim)
            messages.success(request, f"✅ สร้างใบขอเบิก {claim.code} ยอด {total_amount:,.2f} บาท สำเร็จ! (รอโอนเงินจากฝ่ายบัญชี)")
        else:
            messages.error(request, "❌ ไม่พบยอดเงินที่สามารถเบิกได้ หรือสิทธิ์ถูกเบิกไปแล้ว")
    return redirect('commission_board')

@login_required
def knockdown_commission_pay(request, claim_id):
    claim = get_object_or_404(CommissionClaim, id=claim_id)
    if request.method == 'POST' and 'transfer_slip' in request.FILES:
        claim.transfer_slip = request.FILES['transfer_slip']
        claim.status = 'PAID'
        claim.paid_at = timezone.now()
        claim.save()
        claim.tickets.update(status='PAID')
        messages.success(request, f"✅ บัญชีทำรายการโอนเงินค่าคอมมิชชันน็อคดาวน์ {claim.code} สำเร็จ!")
    return redirect('accounting_verification_hub', task_type='knockdown_commissions')

@login_required
def print_commission_claim(request, claim_id):
    claim = get_object_or_404(CommissionClaim, pk=claim_id)
    company = CompanyInfo.objects.first()
    return render(request, 'sales/print_commission_claim.html', {
        'claim': claim, 'company': company, 'tickets': claim.tickets.all(),
        'total_amount_text': get_thai_baht_text(claim.total_amount)
    })

@login_required
@transaction.atomic
def commission_allocate(request, claim_id):
    if not is_sales_authorized(request.user): return redirect('dashboard')
    claim = get_object_or_404(CommissionClaim, id=claim_id)
    current_emp = getattr(request.user, 'employee', None)

    if claim.requester != current_emp and not request.user.is_superuser:
        messages.error(request, "❌ คุณไม่มีสิทธิ์จัดสรรเงินสำหรับใบเบิกนี้")
        return redirect('commission_history_list')

    if request.method == 'POST':
        mode = request.POST.get('allocation_mode')
        dept = current_emp.department if current_emp else None
        claim.allocations.filter(status='PENDING').delete()

        if mode == 'MANUAL':
            for key, val in request.POST.items():
                if key.startswith('amount_emp_') and val.strip():
                    emp_id = key.split('_')[-1]
                    amount = Decimal(val.replace(',', ''))
                    if amount > 0:
                        CommissionAllocation.objects.create(claim=claim, employee_id=emp_id, amount=amount, method='MANUAL', status='PENDING', created_by=current_emp)
            fund_amt = request.POST.get('amount_fund', '0').strip()
            if fund_amt:
                f_amt = Decimal(fund_amt.replace(',', ''))
                if f_amt > 0: CommissionAllocation.objects.create(claim=claim, department=dept, amount=f_amt, method='MANUAL', status='PENDING', created_by=current_emp)
        elif mode == 'PERCENT_CLAIM':
            claim_total = claim.total_amount
            for key, val in request.POST.items():
                if key.startswith('pct_emp_') and val.strip():
                    emp_id = key.split('_')[-1]
                    pct = Decimal(val)
                    if pct > 0:
                        CommissionAllocation.objects.create(claim=claim, employee_id=emp_id, amount=(claim_total * (pct / Decimal('100'))).quantize(Decimal('0.00'), rounding=ROUND_DOWN), method='PERCENT_CLAIM', percentage_used=pct, status='PENDING', created_by=current_emp)
            fund_pct = request.POST.get('pct_fund', '0').strip()
            if fund_pct:
                f_pct = Decimal(fund_pct)
                if f_pct > 0: CommissionAllocation.objects.create(claim=claim, department=dept, amount=(claim_total * (f_pct / Decimal('100'))).quantize(Decimal('0.00'), rounding=ROUND_DOWN), method='PERCENT_CLAIM', percentage_used=f_pct, status='PENDING', created_by=current_emp)
        elif mode == 'PERCENT_SALES':
            for t in claim.tickets.all():
                base_amt = t.base_amount
                for key, val in request.POST.items():
                    if key.startswith(f'ticket_{t.id}_emp_') and val.strip():
                        emp_id = key.split('_')[-1]
                        pct = Decimal(val)
                        if pct > 0: CommissionAllocation.objects.create(claim=claim, ticket=t, employee_id=emp_id, amount=(base_amt * (pct / Decimal('100'))).quantize(Decimal('0.00'), rounding=ROUND_DOWN), method='PERCENT_SALES', percentage_used=pct, status='PENDING', created_by=current_emp)
                fund_pct = request.POST.get(f'ticket_{t.id}_fund', '0').strip()
                if fund_pct:
                    f_pct = Decimal(fund_pct)
                    if f_pct > 0: CommissionAllocation.objects.create(claim=claim, ticket=t, department=dept, amount=(base_amt * (f_pct / Decimal('100'))).quantize(Decimal('0.00'), rounding=ROUND_DOWN), method='PERCENT_SALES', percentage_used=f_pct, status='PENDING', created_by=current_emp)

        messages.success(request, f"✅ จัดสรรผลตอบแทนสำหรับใบเบิก {claim.code} สำเร็จ! ลูกทีมสามารถเห็นยอดเงินใน Dashboard ได้แล้ว")
    return redirect('commission_history_list')

@login_required
def commission_history_personal(request):
    if not is_sales_authorized(request.user): return redirect('dashboard')
    current_emp = getattr(request.user, 'employee', None)
    if not current_emp: return redirect('dashboard')

    is_supervisor_view = False
    user_groups = list(request.user.groups.values_list('name', flat=True))
    
    # 🌟 [NEW] เช็กสิทธิ์ว่าใครจะเห็นยอดกองทุนสาขาบ้าง
    if request.user.is_superuser or 'Manager_Team' in user_groups or 'Executive' in user_groups:
        is_supervisor_view = True
    else:
        rank = current_emp.business_rank.lower() if current_emp.business_rank else ""
        if rank == 'supervisor': is_supervisor_view = True

    tz_bkk = pytz.timezone('Asia/Bangkok')
    today_bkk = timezone.now().astimezone(tz_bkk).date()
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')

    if not start_date or start_date == 'None': start_date = (today_bkk - timedelta(days=29)).strftime('%Y-%m-%d')
    if not end_date or end_date == 'None': end_date = today_bkk.strftime('%Y-%m-%d')

    allocations = CommissionAllocation.objects.filter(employee=current_emp).select_related('claim', 'created_by', 'ticket', 'ticket__quotation_ref').prefetch_related('claim__tickets', 'claim__tickets__quotation_ref', 'claim__tickets__quotation_ref__invoice').order_by('-created_at')

    fund_allocations = CommissionAllocation.objects.none()
    if is_supervisor_view and current_emp and current_emp.department:
        fund_allocations = CommissionAllocation.objects.filter(department=current_emp.department, status='PAID')

    try:
        s_date = parse_date(start_date)
        e_date = parse_date(end_date)
        if s_date and e_date:
            start_dt = tz_bkk.localize(datetime.datetime.combine(s_date, datetime.time.min))
            end_dt = tz_bkk.localize(datetime.datetime.combine(e_date, datetime.time.max))
            allocations = allocations.filter(created_at__gte=start_dt, created_at__lte=end_dt)
            fund_allocations = fund_allocations.filter(created_at__gte=start_dt, created_at__lte=end_dt)
    except Exception:
        pass

    pending_total = allocations.filter(status='PENDING').aggregate(Sum('amount'))['amount__sum'] or 0
    paid_total = allocations.filter(status='PAID').aggregate(Sum('amount'))['amount__sum'] or 0
    branch_fund_total = fund_allocations.aggregate(Sum('amount'))['amount__sum'] or 0

    paginator = Paginator(allocations, 20)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'sales/commission_history_personal.html', {
        'page_obj': page_obj, 'pending_total': pending_total, 'paid_total': paid_total,
        'branch_fund_total': branch_fund_total, 'is_supervisor_view': is_supervisor_view,
        'start_date': start_date, 'end_date': end_date,
    })

@login_required
def supervisor_pay_allocation(request, alloc_id):
    if not is_sales_authorized(request.user): return redirect('dashboard')
    alloc = get_object_or_404(CommissionAllocation, id=alloc_id)

    current_emp = getattr(request.user, 'employee', None)
    if alloc.created_by != current_emp and not request.user.is_superuser:
        messages.error(request, "❌ คุณไม่มีสิทธิ์ยืนยันการจ่ายเงินรายการนี้")
        return redirect('commission_history_list')

    alloc.status = 'PAID'
    alloc.save()
    messages.success(request, f"✅ ยืนยันการโอนเงินค่าคอมมิชชันให้ลูกทีมเรียบร้อยแล้ว!")
    return redirect('commission_history_list')

@login_required
def supervisor_delete_allocation(request, alloc_id):
    if not is_sales_authorized(request.user): return redirect('dashboard')
    alloc = get_object_or_404(CommissionAllocation, id=alloc_id)

    current_emp = getattr(request.user, 'employee', None)
    if alloc.created_by != current_emp and not request.user.is_superuser:
        messages.error(request, "❌ คุณไม่มีสิทธิ์ลบรายการจัดสรรเงินนี้")
        return redirect('commission_history_list')

    if alloc.status != 'PENDING':
        messages.error(request, "❌ ไม่สามารถลบได้ เนื่องจากรายการนี้โอนเงินสำเร็จและถูกล็อกข้อมูลแล้ว")
        return redirect('commission_history_list')

    deleted_amount = alloc.amount
    alloc.delete()
    messages.success(request, f"🗑️ ยกเลิกและลบยอดเงินจัดสรร {deleted_amount:,.2f} บาท คืนกลับไปที่ยอดคงเหลือเรียบร้อยแล้ว!")
    return redirect('commission_history_list')