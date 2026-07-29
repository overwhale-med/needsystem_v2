import math
import json
import datetime
import openpyxl
from decimal import Decimal, ROUND_DOWN, InvalidOperation

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Q, Sum, Count, Max, F, FloatField
from django.db.models.functions import TruncDate, TruncMonth
from django.core.paginator import Paginator
from django.utils.dateparse import parse_date
from django.utils import timezone
from datetime import timedelta
from django.db import transaction

# Models
from .models import Quotation, QuotationItem, POSOrder, POSOrderItem, Invoice, UpsaleCategory, UpsaleCatalog, QuotationUpsale, InvoicePayment, CustomerLead, Appointment
from master_data.models import Customer, CompanyInfo, ShippingRate
from hr.models import Employee, SalesGroup, CompanySalesTarget, CommissionLog, FundTransaction
from .forms import QuotationForm
from manufacturing.models import ProductionOrder, Salesperson as MfgSalesperson, Branch, MfgBranch, ProductionStatus
from inventory.models import Product, InventoryDoc, StockMovement, Category
from solar_jobs.models import SolarJob

# ==========================================
# 🌟 Helper Function: แปลงวันที่ DD/MM/YYYY เป็น YYYY-MM-DD
# ==========================================
def parse_thai_date(date_str):
    if not date_str:
        return None
    try:
        # ลองแปลงแบบ YYYY-MM-DD ดูก่อน (เผื่อระบบส่งมาถูก)
        return parse_date(date_str)
    except:
        pass
    try:
        # ถ้าแปลงไม่ได้ ให้ลองแปลงแบบ DD/MM/YYYY
        day, month, year = map(int, date_str.split('/'))
        return datetime.date(year, month, day)
    except:
        return None

# ==========================================
# 🧠 ระบบคำนวณคอมมิชชัน
# ==========================================
def process_commission_logic(sale_amount, seller, sale_ref_id):
    now = timezone.now()
    sale_amount = Decimal(str(sale_amount))
    target, _ = CompanySalesTarget.objects.get_or_create(year=now.year, month=now.month)
    target.current_sales += sale_amount
    if target.current_sales >= target.target_amount:
        target.is_unlocked = True
    target.save()

    exec_group = SalesGroup.objects.filter(group_type='EXECUTIVE').first()
    if exec_group:
        exec_pool_amount = sale_amount * (exec_group.commission_rate / Decimal('100'))
        executives = Employee.objects.filter(sales_group=exec_group)
        if executives.exists():
            exact_share = exec_pool_amount / Decimal(str(executives.count()))
            share_per_head = exact_share.quantize(Decimal('0.00'), rounding=ROUND_DOWN)
            remainder = exec_pool_amount - (share_per_head * Decimal(str(executives.count())))
            for ex in executives:
                CommissionLog.objects.create(recipient=ex, source_employee=seller, level=1, amount=share_per_head, sale_ref_id=sale_ref_id)
            if remainder > 0:
                exec_group.fund_balance += remainder
                exec_group.save()
                FundTransaction.objects.create(group=exec_group, transaction_type='IN', amount=remainder, description=f"ปัดเศษเข้าสำรองบริหาร จากบิล {sale_ref_id}")

    if not seller or not seller.sales_group: return
    group = seller.sales_group

    total_group_comm = sale_amount * (group.commission_rate / Decimal('100'))
    fund_to_add = Decimal('0.00')

    if group.group_type == 'TEAM':
        exact_leader_share = total_group_comm * (group.share_leader / Decimal('100'))
        leader_share = exact_leader_share.quantize(Decimal('0.00'), rounding=ROUND_DOWN)
        fund_to_add += (exact_leader_share - leader_share)
        leader = Employee.objects.filter(sales_group=group, group_role='LEADER').first()
        if leader:
            CommissionLog.objects.create(recipient=leader, source_employee=seller, level=1, amount=leader_share, sale_ref_id=sale_ref_id)
        else:
            fund_to_add += leader_share

        exact_l1_share = total_group_comm * (group.share_level1 / Decimal('100'))
        l1_members = Employee.objects.filter(sales_group=group, group_role='LEVEL1')
        if l1_members.exists():
            exact_split = exact_l1_share / Decimal(str(l1_members.count()))
            split = exact_split.quantize(Decimal('0.00'), rounding=ROUND_DOWN)
            remainder = exact_l1_share - (split * Decimal(str(l1_members.count())))
            fund_to_add += remainder
            for m in l1_members:
                CommissionLog.objects.create(recipient=m, source_employee=seller, level=2, amount=split, sale_ref_id=sale_ref_id)
        else:
            fund_to_add += exact_l1_share

        exact_l2_share = total_group_comm * (group.share_level2 / Decimal('100'))
        l2_members = Employee.objects.filter(sales_group=group, group_role='LEVEL2')
        if l2_members.exists():
            exact_split = exact_l2_share / Decimal(str(l2_members.count()))
            split = exact_split.quantize(Decimal('0.00'), rounding=ROUND_DOWN)
            remainder = exact_l2_share - (split * Decimal(str(l2_members.count())))
            fund_to_add += remainder
            for m in l2_members:
                CommissionLog.objects.create(recipient=m, source_employee=seller, level=3, amount=split, sale_ref_id=sale_ref_id)
        else:
            fund_to_add += exact_l2_share

        exact_fixed_fund_share = total_group_comm * (group.share_fund / Decimal('100'))
        fund_to_add += exact_fixed_fund_share

    elif group.group_type == 'INDEPENDENT':
        exact_fund_share = total_group_comm * (group.share_fund / Decimal('100'))
        exact_personal_share = total_group_comm - exact_fund_share
        personal_share = exact_personal_share.quantize(Decimal('0.00'), rounding=ROUND_DOWN)
        fund_to_add = exact_fund_share + (exact_personal_share - personal_share)
        CommissionLog.objects.create(recipient=seller, source_employee=seller, level=1, amount=personal_share, sale_ref_id=sale_ref_id)

    if fund_to_add > 0:
        group.fund_balance += fund_to_add
        group.save()
        FundTransaction.objects.create(group=group, transaction_type='IN', amount=fund_to_add, description=f"รับคอมฯและปัดเศษสตางค์ จากบิล {sale_ref_id}")

def get_next_document_number():
    now = timezone.now()
    thai_year = (now.year + 543) % 100
    prefix = f"DLN-{thai_year:02d}{now.strftime('%m')}"
    last_inv = Invoice.objects.filter(code__startswith=prefix).aggregate(Max('code'))['code__max']
    last_pos = POSOrder.objects.filter(code__startswith=prefix).aggregate(Max('code'))['code__max']
    max_seq = 0
    if last_inv:
        try: max_seq = max(max_seq, int(last_inv.split('-')[-1]))
        except: pass
    if last_pos:
        try: max_seq = max(max_seq, int(last_pos.split('-')[-1]))
        except: pass
    return f"{prefix}-{max_seq + 1:03d}"

def get_target_employees(user):
    current_emp = getattr(user, 'employee', None)
    if user.is_superuser: return Employee.objects.all(), "Admin View"
    elif current_emp:
        dept_name = current_emp.department.name if current_emp.department else ""
        if 'บัญชี' in dept_name or 'Accounting' in dept_name: return Employee.objects.all(), "Accounting View"
        rank = current_emp.business_rank.lower() if current_emp.business_rank else ""
        if rank in ['manager', 'director']: return Employee.objects.all(), "Manager View"
        elif rank == 'supervisor':
            if current_emp.department: return Employee.objects.filter(department=current_emp.department), f"Team {current_emp.department.name}"
            else: return Employee.objects.filter(Q(id=current_emp.id) | Q(introducer=current_emp)), "Direct Team"
        else: return Employee.objects.filter(id=current_emp.id), "Self View"
    return Employee.objects.none(), "-"

def get_sales_queryset(model_class, user, target_employees):
    if user.is_superuser: return model_class.objects.all()
    if hasattr(user, 'employee') and user.employee:
        dept_name = user.employee.department.name if user.employee.department else ""
        rank = user.employee.business_rank.lower() if user.employee.business_rank else ""
        if 'บัญชี' in dept_name or rank in ['manager', 'director']: return model_class.objects.all()

    emp_ids = list(target_employees.values_list('id', flat=True))
    return model_class.objects.filter(employee_id__in=emp_ids)

def is_sales_authorized(user):
    if user.is_superuser: return True
    if hasattr(user, 'employee') and user.employee:
        dept = user.employee.department.name if user.employee.department else ''
        if 'ขาย' in dept or 'Sales' in dept: return True
    return False

# ==========================================
# หน้า Sales Hub และ Dashboards
# ==========================================
@login_required
def sales_dashboard(request):
    if not is_sales_authorized(request.user): return redirect('dashboard')

    target_employees, scope_title = get_target_employees(request.user)
    today = timezone.now().date()

    # 🌟 [NEW] ระบบดึงข้อมูลสาขา เพื่อใช้เป็น Dropdown ตัวกรอง
    from hr.models import Department
    is_manager = False
    is_supervisor = False
    current_emp = getattr(request.user, 'employee', None)

    if request.user.is_superuser:
        is_manager = True
    elif current_emp:
        rank = current_emp.business_rank.lower() if current_emp.business_rank else ""
        if rank in ['manager', 'director'] or 'manager' in getattr(current_emp.position, 'title', '').lower() or 'บัญชี' in getattr(current_emp.department, 'name', ''):
            is_manager = True
        elif rank == 'supervisor':
            is_supervisor = True

    # 🌟 โหลดรายชื่อสาขาตามสิทธิ์ (กรองเฉพาะ "ทีม" และ "สาขา")
    if is_manager:
        departments = list(Department.objects.filter(
            Q(name__icontains='ทีม') | Q(name__icontains='สาขา')
        ).order_by('name'))
    elif is_supervisor and current_emp.department:
        departments = list(Department.objects.filter(id=current_emp.department.id))
    else:
        departments = []

    # ลบคำว่า "แผนก" ทิ้งเพื่อความสะอาดตา
    for d in departments:
        d.name = d.name.replace('แผนก', '').strip()

    return render(request, 'sales/dashboard.html', {
        'scope_title': scope_title,
        'start_date': today.strftime('%Y-%m-%d'),
        'end_date': today.strftime('%Y-%m-%d'),
        'departments': departments,
        'is_manager': is_manager,
        'is_supervisor': is_supervisor
    })

@login_required
def sales_hub(request):
    if not is_sales_authorized(request.user):
        messages.error(request, "❌ บัญชีของคุณไม่มีสิทธิ์เปิดบิลขาย")
        return redirect('dashboard')

@login_required
def api_dashboard_data(request):
    if not is_sales_authorized(request.user): return JsonResponse({'error': 'Unauthorized'}, status=403)

    target_employees, scope_title = get_target_employees(request.user)
    emp = getattr(request.user, 'employee', None)
    today = timezone.now().date()

    start_date_str = request.GET.get('start_date')
    end_date_str = request.GET.get('end_date')

    start_date = parse_date(start_date_str) if start_date_str else today
    end_date = parse_date(end_date_str) if end_date_str else today
    end_date_inclusive = end_date + timedelta(days=1)

    branch_filter = request.GET.get('branch', '')
    user_rank = emp.business_rank.lower() if (emp and emp.business_rank) else "member"

    if branch_filter and (user_rank in ['manager', 'director', 'supervisor'] or request.user.is_superuser):
        target_employees = target_employees.filter(department_id=branch_filter)

    pos_qs_all = get_sales_queryset(POSOrder, request.user, target_employees).filter(created_at__gte=start_date, created_at__lt=end_date_inclusive)
    inv_qs_all = get_sales_queryset(Invoice, request.user, target_employees).filter(date__gte=start_date, date__lte=end_date)

    total_sales = float((pos_qs_all.filter(status='PAID').aggregate(Sum('total_amount'))['total_amount__sum'] or 0) +
                        (inv_qs_all.filter(status='PAID').aggregate(Sum('grand_total'))['grand_total__sum'] or 0))

    today_start = datetime.datetime.combine(today, datetime.time.min)
    tomorrow_start = today_start + timedelta(days=1)

    pos_today_count = get_sales_queryset(POSOrder, request.user, target_employees).filter(created_at__gte=today_start, created_at__lt=tomorrow_start).count()
    inv_today_count = get_sales_queryset(Invoice, request.user, target_employees).filter(date=today).count()
    total_orders_today = pos_today_count + inv_today_count

    qt_all_qs = get_sales_queryset(Quotation, request.user, target_employees)
    pending_approval = qt_all_qs.filter(status='DRAFT').count()
    pending_closing = qt_all_qs.filter(status='APPROVED', is_deposit_paid=False).count()
    in_production = qt_all_qs.filter(status='APPROVED', is_deposit_paid=True).count()

    chart_labels, chart_data, chart_title, chart_type = [], [], "", "bar"

    pos_raw = list(pos_qs_all.filter(status='PAID').values('total_amount', 'employee__department__name', 'employee__first_name'))
    inv_raw = list(inv_qs_all.filter(status='PAID').values('grand_total', 'employee__department__name', 'employee__first_name'))

    # 🌟 บังคับกราฟให้เป็นเปรียบเทียบทีม/สาขา หรือ พนักงานเสมอ (ผลรวมจะตรงกับบัตร 100%) 🌟
    if user_rank in ['manager', 'director'] or request.user.is_superuser:
        chart_title = "ยอดขายเปรียบเทียบรายทีม/สาขา"
        team_dict = {}
        for p in pos_raw:
            t = p['employee__department__name'] or 'ไม่ระบุสาขา'
            team_dict[t] = team_dict.get(t, 0) + float(p['total_amount'] or 0)
        for i in inv_raw:
            t = i['employee__department__name'] or 'ไม่ระบุสาขา'
            team_dict[t] = team_dict.get(t, 0) + float(i['grand_total'] or 0)

        sorted_data = sorted(team_dict.items(), key=lambda x: x[1], reverse=True)
        chart_labels, chart_data = [x[0] for x in sorted_data], [x[1] for x in sorted_data]

    elif user_rank == 'supervisor':
        chart_title = f"ยอดขายเปรียบเทียบพนักงานในทีม"
        mem_dict = {}
        for p in pos_raw:
            m = p['employee__first_name'] or 'ไม่ระบุชื่อ'
            mem_dict[m] = mem_dict.get(m, 0) + float(p['total_amount'] or 0)
        for i in inv_raw:
            m = i['employee__first_name'] or 'ไม่ระบุชื่อ'
            mem_dict[m] = mem_dict.get(m, 0) + float(i['grand_total'] or 0)

        sorted_data = sorted(mem_dict.items(), key=lambda x: x[1], reverse=True)
        chart_labels, chart_data = [x[0] for x in sorted_data], [x[1] for x in sorted_data]

    else:
        chart_title = "ยอดขายส่วนตัว"
        chart_labels = [emp.first_name if emp else 'พนักงาน']
        chart_data = [total_sales]

    recent_pos = list(get_sales_queryset(POSOrder, request.user, target_employees)
                      .filter(created_at__gte=start_date, created_at__lt=end_date_inclusive)
                      .select_related('employee', 'employee__department')
                      .order_by('-created_at')[:10])

    recent_inv = list(get_sales_queryset(Invoice, request.user, target_employees)
                      .filter(date__gte=start_date, date__lte=end_date)
                      .select_related('employee', 'employee__department', 'quotation_ref')
                      .prefetch_related('quotation_ref__production_orders')
                      .order_by('-created_at')[:10])

    combined = sorted(recent_pos + recent_inv, key=lambda x: x.created_at, reverse=True)[:10]
    recent_sales_data = []

    for item in combined:
        is_pos = isinstance(item, POSOrder)
        qt, job = "-", "-"

        if not is_pos and getattr(item, 'quotation_ref', None):
            qt = item.quotation_ref.code
            jobs = item.quotation_ref.production_orders.all()
            if jobs.exists(): job = ", ".join([j.code for j in jobs])

        recent_sales_data.append({
            'time': item.created_at.strftime('%H:%M') if item.created_at.date() == today else item.created_at.strftime('%d/%m/%Y'),
            'code': item.code, 'is_pos': is_pos, 'qt_code': qt, 'job_code': job,
            'employee_name': item.employee.first_name if item.employee else '-',
            'employee_branch': item.employee.department.name if item.employee and item.employee.department else '-',
            'employee_photo': item.employee.photo.url if item.employee and getattr(item.employee, 'photo', None) else None,
            'employee_initial': item.employee.first_name[0] if item.employee and item.employee.first_name else '-',
            'amount': float(item.total_amount) if is_pos else float(item.grand_total)
        })

    response_data = {
        'total_sales': total_sales, 'total_orders_today': total_orders_today,
        'pending_approval': pending_approval, 'pending_closing': pending_closing,
        'in_production': in_production, 'chart_labels': chart_labels,
        'chart_data': chart_data, 'chart_title': chart_title,
        'chart_type': chart_type, 'scope_title': scope_title,
        'recent_sales': recent_sales_data
    }

    return JsonResponse(response_data)

@login_required
def sales_hub(request):
    if not is_sales_authorized(request.user):
        messages.error(request, "❌ บัญชีของคุณไม่มีสิทธิ์เปิดบิลขาย")
        return redirect('dashboard')

    target_employees, _ = get_target_employees(request.user)
    qt_qs = get_sales_queryset(Quotation, request.user, target_employees)
    inv_qs = get_sales_queryset(Invoice, request.user, target_employees)
    pos_qs = get_sales_queryset(POSOrder, request.user, target_employees)

    ready_quotes = qt_qs.filter(status='APPROVED').order_by('-created_at')
    today = timezone.now().date()
    today_invoices = inv_qs.filter(date=today).order_by('-created_at')
    today_pos = pos_qs.filter(created_at__date=today).order_by('-created_at')

    return render(request, 'sales/sales_hub.html', {
        'ready_quotes': ready_quotes,
        'today_invoices': today_invoices,
        'today_pos': today_pos
    })

@login_required
def record_deposit(request, qt_id):
    qt = get_object_or_404(Quotation, pk=qt_id)
    if request.method == 'POST':
        amount_str = request.POST.get('deposit_amount', '0').replace(',', '')
        try: amount = Decimal(amount_str)
        except: amount = Decimal(0)

        method = request.POST.get('deposit_method', 'TRANSFER')
        date_str = request.POST.get('deposit_date')
        next_url = request.POST.get('next')

        if amount > 0:
            qt.deposit_amount = amount
            qt.deposit_method = method
            if date_str: qt.deposit_date = parse_thai_date(date_str) 
            else: qt.deposit_date = timezone.now().date()
            qt.is_deposit_paid = True

            if 'deposit_slip' in request.FILES:
                qt.deposit_slip = request.FILES['deposit_slip']
            qt.save()
            messages.success(request, f"💰 บันทึกรับมัดจำ {amount:,.2f} บาท สำหรับใบเสนอราคา {qt.code} เรียบร้อยแล้ว")
        else:
            messages.error(request, "❌ จำนวนเงินมัดจำต้องมากกว่า 0")

        if next_url: return redirect(next_url)

    return redirect('quotation_edit', qt_id=qt.id)

def get_auto_delivery_date(qt):
    first_item = qt.items.filter(product__isnull=False).first()
    if not first_item: return timezone.now().date()

    company_info = CompanyInfo.objects.first()
    max_quota = company_info.weekly_job_quota if company_info and company_info.weekly_job_quota else 25

    deposit_date = qt.deposit_date if qt.deposit_date else timezone.now().date()
    current_check_date = deposit_date
    weeks_pushed = 0

    while True:
        iso_year, iso_week, _ = current_check_date.isocalendar()
        check_cohort = f"{iso_year}-W{iso_week:02d}"

        total_qty_in_week = ProductionOrder.objects.filter(cohort_week=check_cohort, is_closed=False).aggregate(Sum('quantity'))['quantity__sum'] or 0

        if total_qty_in_week + first_item.quantity <= max_quota:
            break

        weeks_pushed += 1
        current_check_date += datetime.timedelta(days=7)

    base_lead_time = 14 + (weeks_pushed * 7)
    delivery_start_date = deposit_date + datetime.timedelta(days=base_lead_time)
    days_to_monday = delivery_start_date.weekday()
    monday_of_delivery_week = delivery_start_date - datetime.timedelta(days=days_to_monday)

    return monday_of_delivery_week + datetime.timedelta(days=4)

@login_required
def create_job_order(request, qt_id):
    qt = get_object_or_404(Quotation, pk=qt_id)

    if qt.production_orders.exists():
        messages.warning(request, f"⚠️ ใบเสนอราคา {qt.code} ถูกส่งสั่งผลิตไปแล้ว!")
        return redirect('quotation_list')

    if qt.is_deposit_paid and not qt.is_deposit_verified:
        messages.error(request, f"❌ ไม่สามารถส่งสั่งผลิตได้ บัญชียังไม่ได้ตรวจสอบสลิปเงินมัดจำของ {qt.code}")
        return redirect('quotation_list')

    first_item = qt.items.filter(product__isnull=False).first()
    if not first_item:
        messages.error(request, "❌ ไม่พบข้อมูลสินค้า (FG) ในใบเสนอราคา ไม่สามารถสร้างใบสั่งผลิตได้")
        return redirect('quotation_list')

    company_info = CompanyInfo.objects.first()
    max_quota = company_info.weekly_job_quota if company_info and company_info.weekly_job_quota else 25

    deposit_date = qt.deposit_date if qt.deposit_date else timezone.now().date()
    current_check_date = deposit_date
    weeks_pushed = 0
    assigned_cohort = ""

    while True:
        iso_year, iso_week, _ = current_check_date.isocalendar()
        check_cohort = f"{iso_year}-W{iso_week:02d}"

        total_qty_in_week = ProductionOrder.objects.filter(cohort_week=check_cohort, is_closed=False).aggregate(Sum('quantity'))['quantity__sum'] or 0

        if total_qty_in_week + first_item.quantity <= max_quota:
            assigned_cohort = check_cohort
            break

        weeks_pushed += 1
        current_check_date += datetime.timedelta(days=7)

    base_lead_time = 14 + (weeks_pushed * 7)
    start_date = deposit_date + datetime.timedelta(days=(weeks_pushed * 7))
    delivery_start_date = deposit_date + datetime.timedelta(days=base_lead_time)

    days_to_monday = delivery_start_date.weekday()
    monday_of_delivery_week = delivery_start_date - datetime.timedelta(days=days_to_monday)

    total_qty = int(first_item.quantity)
    daily_qty = math.ceil(total_qty / 5.0)

    delivery_plan_note = f"\n\n🚚 แผนการจัดส่ง (เฉลี่ยวันละ {daily_qty} หลัง):\n"
    remaining_qty = total_qty
    for i in range(5):
        current_day = monday_of_delivery_week + datetime.timedelta(days=i)
        qty_today = min(daily_qty, remaining_qty)
        if qty_today > 0:
            delivery_plan_note += f"- {current_day.strftime('%d/%m/%Y')} ({['จันทร์', 'อังคาร', 'พุธ', 'พฤหัสฯ', 'ศุกร์'][i]}): ส่ง {qty_today} หลัง\n"
        remaining_qty -= qty_today

    final_delivery_date = monday_of_delivery_week + datetime.timedelta(days=4)

    target_date_str = request.POST.get('target_date')
    
    requested_date_obj = parse_thai_date(target_date_str) if target_date_str else None

    if requested_date_obj and requested_date_obj != final_delivery_date:
        approval_status = 'PENDING'
        req_date = requested_date_obj
        deadline = requested_date_obj 
    else:
        approval_status = 'NOT_REQUIRED'
        req_date = None
        deadline = final_delivery_date

    sales_obj = None
    if qt.employee:
        emp_name = f"{qt.employee.first_name} {qt.employee.last_name}".strip()
        branch_name = qt.employee.department.name if qt.employee.department else "สำนักงานใหญ่"
        sales_branch_obj, _ = Branch.objects.get_or_create(name=branch_name)
        sales_obj, _ = MfgSalesperson.objects.get_or_create(name=emp_name, branch=sales_branch_obj)

    is_onsite_val = request.POST.get('is_onsite') == 'on'

    job = ProductionOrder.objects.create(
        product=first_item.product,
        quantity=total_qty,
        quotation_ref=qt,
        customer_name=qt.customer_name,
        note=f"อ้างอิงใบเสนอราคา: {qt.code}\n{qt.note}{delivery_plan_note}",
        salesperson=sales_obj,
        branch=None,
        start_date=start_date,
        delivery_date=deadline,
        deadline_date=deadline,
        auto_calculated_date=final_delivery_date,
        requested_date=req_date,
        date_approval_status=approval_status,
        cohort_week=assigned_cohort,
        is_onsite=is_onsite_val
    )

    if first_item.product and first_item.product.standard_blueprint:
        job.blueprint_file = first_item.product.standard_blueprint
        job.save()

    if first_item.product:
        p_name = first_item.product.name.lower()
        c_name = first_item.product.category.name.lower() if hasattr(first_item.product, 'category') and first_item.product.category else ""

        if 'โซล่า' in p_name or 'solar' in p_name or 'โซล่า' in c_name or 'solar' in c_name:
            try:
                SolarJob.objects.create(
                    customer=qt.customer,
                    salesperson=qt.employee,
                    package_sold=first_item.product,
                    status='DRAFT',
                    note=f"📌 สร้างอัตโนมัติจากใบเสนอราคา {qt.code}\nรายละเอียดเพิ่มเติม: {qt.note}"
                )
            except Exception as e:
                print(f"เกิดข้อผิดพลาดในการสร้าง Solar Job: {e}")

    if approval_status == 'PENDING':
        messages.warning(request, f"🏭 ส่งสั่งผลิตสำเร็จ! (ระบบตั้งสถานะ 'รออนุมัติวัน' เนื่องจากขอเปลี่ยนวันจัดส่งเป็น {req_date.strftime('%d/%m/%Y')})")
    elif weeks_pushed > 0:
        messages.warning(request, f"⚠️ คิวผลิตสัปดาห์แรกล้น! ระบบปัดคิวงาน {job.code} ไปสัปดาห์ถัดไป (กำหนดส่ง: {final_delivery_date.strftime('%d/%m/%Y')})")
    else:
        onsite_txt = " 👷‍♂️(ประกอบหน้างาน)" if is_onsite_val else ""
        messages.success(request, f"🏭 ส่งข้อมูลเข้ากองกลางผลิตสำเร็จ (Job Order: {job.code}){onsite_txt}! (กำหนดส่ง: {deadline.strftime('%d/%m/%Y')})")

    return redirect('quotation_list')


# ==========================================
# 🌟 [NEW] หน้าระบบ Timeline และ Dashboards สำหรับงานขาย 🌟
# ==========================================
@login_required
def sales_timeline(request):
    if not is_sales_authorized(request.user):
        messages.error(request, "❌ บัญชีของคุณไม่มีสิทธิ์เข้าถึงหน้า Timeline")
        return redirect('dashboard')

    today = timezone.now().date()
    company_info = CompanyInfo.objects.first()
    max_quota = company_info.weekly_job_quota if company_info and company_info.weekly_job_quota else 25

    deposit_date_str = request.GET.get('deposit_date')
    if deposit_date_str:
        try: calc_deposit_date = parse_thai_date(deposit_date_str) or today
        except: calc_deposit_date = today
    else:
        calc_deposit_date = today

    current_check_date = calc_deposit_date
    weeks_pushed = 0
    while True:
        iso_year, iso_week, _ = current_check_date.isocalendar()
        check_cohort = f"{iso_year}-W{iso_week:02d}"

        total_qty_in_week = ProductionOrder.objects.filter(cohort_week=check_cohort, is_closed=False).aggregate(Sum('quantity'))['quantity__sum'] or 0

        if total_qty_in_week < max_quota:
            break

        weeks_pushed += 1
        current_check_date += datetime.timedelta(days=7)

    smart_eta_date = calc_deposit_date + datetime.timedelta(days=22 + (weeks_pushed * 7))

    def format_week_range(d):
        iso_y, iso_w, _ = d.isocalendar()
        monday = datetime.date.fromisocalendar(iso_y, iso_w, 1)
        sunday = monday + datetime.timedelta(days=6)
        y_str = str(sunday.year + 543)[-2:]
        if monday.month == sunday.month:
            return f"จ.{monday.day}-อา.{sunday.day}/{monday.month}/{y_str}"
        else:
            return f"จ.{monday.day}/{monday.month}-อา.{sunday.day}/{sunday.month}/{y_str}"

    chart_labels = []
    chart_labels_display = []
    chart_week_starts = []
    chart_week_ends = []

    chart1_ordered = []
    chart1_pending = []
    chart1_delivered = []

    start_date = today - datetime.timedelta(weeks=4)
    for i in range(8):
        w_date = start_date + datetime.timedelta(weeks=i)
        iso_year, iso_week, _ = w_date.isocalendar()
        cohort = f"{iso_year}-W{iso_week:02d}"

        monday = datetime.date.fromisocalendar(iso_year, iso_week, 1)
        sunday = monday + datetime.timedelta(days=6)

        chart_labels.append(cohort)
        chart_labels_display.append(format_week_range(w_date))
        chart_week_starts.append(monday.strftime('%Y-%m-%d'))
        chart_week_ends.append(sunday.strftime('%Y-%m-%d'))

        ordered = ProductionOrder.objects.filter(cohort_week=cohort).exclude(status='CANCELLED').aggregate(Sum('quantity'))['quantity__sum'] or 0
        pending = ProductionOrder.objects.filter(cohort_week=cohort, status='COMPLETED', is_closed=False).aggregate(Sum('quantity'))['quantity__sum'] or 0
        deli = ProductionOrder.objects.filter(cohort_week=cohort, is_closed=True).aggregate(Sum('quantity'))['quantity__sum'] or 0

        chart1_ordered.append(int(ordered))
        chart1_pending.append(int(pending))
        chart1_delivered.append(int(deli))

    filter_date_str = request.GET.get('filter_date')
    if filter_date_str:
        try: filter_date = parse_thai_date(filter_date_str) or today
        except: filter_date = today
    else:
        filter_date = today

    f_iso_year, f_iso_week, _ = filter_date.isocalendar()
    target_cohort = f"{f_iso_year}-W{f_iso_week:02d}"
    filter_week_display = format_week_range(filter_date)

    branches = MfgBranch.objects.all().order_by('id')
    chart2_labels = []
    chart2_data = []
    chart2_bg_colors = ['#0d6efd', '#ffc107', '#198754', '#dc3545', '#6f42c1', '#0dcaf0', '#fd7e14']

    for b in branches:
        chart2_labels.append(b.name)
        qty = ProductionOrder.objects.filter(cohort_week=target_cohort, branch=b).aggregate(Sum('quantity'))['quantity__sum'] or 0
        chart2_data.append(int(qty))

    return render(request, 'sales/sales_timeline.html', {
        'today': today,
        'calc_deposit_date': calc_deposit_date,
        'smart_eta_date': smart_eta_date,
        'filter_date': filter_date,
        'filter_week_display': filter_week_display,
        'chart_labels_display_json': json.dumps(chart_labels_display),
        'chart_week_starts_json': json.dumps(chart_week_starts),
        'chart_week_ends_json': json.dumps(chart_week_ends),
        'chart1_ordered_json': json.dumps(chart1_ordered),
        'chart1_pending_json': json.dumps(chart1_pending),
        'chart1_delivered_json': json.dumps(chart1_delivered),
        'chart2_labels_json': json.dumps(chart2_labels),
        'chart2_data_json': json.dumps(chart2_data),
        'chart2_colors_json': json.dumps(chart2_bg_colors[:len(branches)]),
    })

@login_required
def convert_quote_to_invoice(request, qt_id):
    qt = get_object_or_404(Quotation, pk=qt_id)
    new_code = get_next_document_number()

    balance = qt.grand_total - qt.deposit_amount
    status = 'PAID' if balance <= 0 else 'UNPAID'

    invoice = Invoice.objects.create(
        code=new_code,
        quotation_ref=qt,
        date=timezone.now().date(),
        customer=qt.customer,
        employee=request.user.employee if hasattr(request.user, 'employee') else None,
        grand_total=qt.grand_total,
        deposit_amount=qt.deposit_amount,
        balance_amount=balance,
        status=status
    )
    qt.status = 'CONVERTED'
    qt.save()

    for job in qt.production_orders.all():
        if not job.is_closed:
            job.is_closed = True
            job.save()

    messages.success(request, f"✅ เปิดใบขายสินค้า {new_code} เรียบร้อย (ยอดคงค้างชำระ: {balance:,.2f} บาท) และอัปเดตปิดจ๊อบให้โรงงานแล้ว!")
    return redirect('invoice_list')

@login_required
def pos_home(request):
    if not is_sales_authorized(request.user):
        messages.error(request, "❌ บัญชีของคุณไม่มีสิทธิ์ใช้งานระบบ POS")
        return redirect('dashboard')
    products = Product.objects.filter(is_active=True, stock_qty__gt=0, product_type='FG')
    categories = Category.objects.all()
    return render(request, 'sales/pos_home.html', {'products': products, 'categories': categories})

@csrf_exempt
@login_required
def pos_checkout(request):
    if request.method == 'POST':
        try:
            payment_method = request.POST.get('payment_method', 'CASH')
            total_amount = Decimal(request.POST.get('total_amount', 0))
            received_amount = Decimal(request.POST.get('received_amount', 0))

            cust_id = request.POST.get('customer_id')
            cust_name = request.POST.get('customer_name', '')
            cust_addr = request.POST.get('customer_address', '')
            cust_phone = request.POST.get('customer_phone', '')
            cust_tax = request.POST.get('customer_tax_id', '')

            cart_json = request.POST.get('cart', '[]')
            cart = json.loads(cart_json)

            order_code = get_next_document_number()
            current_emp = getattr(request.user, 'employee', None)

            customer_obj = None
            if cust_id:
                 try: customer_obj = Customer.objects.get(id=cust_id)
                 except: pass

            order = POSOrder.objects.create(
                code=order_code,
                employee=current_emp,
                total_amount=total_amount,
                received_amount=received_amount,
                change_amount=received_amount - total_amount,
                payment_method=payment_method,
                status='PENDING',
                customer=customer_obj,
                customer_name=cust_name,
                customer_address=cust_addr,
                customer_phone=cust_phone,
                customer_tax_id=cust_tax
            )

            if payment_method == 'TRANSFER':
                if 'transfer_slip' in request.FILES:
                    order.transfer_slip = request.FILES['transfer_slip']
            elif payment_method == 'CHECK':
                order.check_number = request.POST.get('check_number', '')
                order.check_bank = request.POST.get('check_bank', '')
                if 'check_slip' in request.FILES:
                    order.check_slip = request.FILES['check_slip']

            order.save()

            for item in cart:
                product = Product.objects.get(id=item['id'])
                POSOrderItem.objects.create(
                    order=order, product=product, product_name=product.name,
                    quantity=item['qty'], price=item['price'],
                    total_price=float(item['qty']) * float(item['price'])
                )
                product.stock_qty -= int(item['qty'])
                product.save()

            if current_emp: process_commission_logic(total_amount, current_emp, order_code)

            return JsonResponse({'success': True, 'order_code': order_code})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    return JsonResponse({'success': False, 'error': 'Invalid Request'})

@login_required
def pos_print_slip(request, order_code):
    order = get_object_or_404(POSOrder, code=order_code)
    company = CompanyInfo.objects.first()

    items = list(order.items.all())
    item_total = Decimal('0.00')
    for item in items:
        item.item_name = item.product_name
        item.unit_price = item.price
        item.amount = item.total_price
        item_total += Decimal(str(item.amount))

    payment_note = "ชำระโดย: เงินสด (Cash)"
    if order.payment_method == 'TRANSFER':
        payment_note = "ชำระโดย: โอนเงิน (Bank Transfer)"
    elif order.payment_method == 'CHECK':
        payment_note = f"ชำระโดย: เช็คธนาคาร {order.check_bank} #{order.check_number}"

    grand_total = order.total_amount
    subtotal = grand_total / Decimal('1.07')
    tax_amount = grand_total - subtotal

    context = {
        'inv': order, 'company': company, 'items': items,
        'item_total': item_total, 'subtotal': subtotal, 'tax_amount': tax_amount,
        'discount': Decimal('0.00'), 'shipping_cost': Decimal('0.00'),
        'note': payment_note, 'is_pos': True
    }
    return render(request, 'sales/invoice_print.html', context)

@login_required
def quotation_list(request):
    if not is_sales_authorized(request.user):
        messages.error(request, "❌ บัญชีของคุณไม่มีสิทธิ์เข้าถึงหน้ารายการใบเสนอราคา")
        return redirect('dashboard')

    target_employees, _ = get_target_employees(request.user)
    queryset = get_sales_queryset(Quotation, request.user, target_employees).order_by('-created_at')

    # 🌟 [NEW] ระบบจำกัดสิทธิ์และดึงข้อมูลสาขา
    from hr.models import Department
    is_manager = False
    is_supervisor = False
    current_emp = getattr(request.user, 'employee', None)

    if request.user.is_superuser:
        is_manager = True
    elif current_emp:
        rank = current_emp.business_rank.lower() if current_emp.business_rank else ""
        if rank in ['manager', 'director'] or 'manager' in getattr(current_emp.position, 'title', '').lower() or 'บัญชี' in getattr(current_emp.department, 'name', ''):
            is_manager = True
        elif rank == 'supervisor':
            is_supervisor = True

    # 🌟 โหลดรายชื่อสาขาตามสิทธิ์ (กรองเฉพาะ "ทีม" และ "สาขา")
    if is_manager:
        departments = list(Department.objects.filter(
            Q(name__icontains='ทีม') |
            Q(name__icontains='สาขา')
        ).order_by('name'))
    elif is_supervisor and current_emp.department:
        departments = list(Department.objects.filter(id=current_emp.department.id))
    else:
        departments = []

    # 🌟 ลบคำว่า "แผนก" ทิ้งเพื่อความสะอาดตา
    for d in departments:
        d.name = d.name.replace('แผนก', '').strip()

    search_query = request.GET.get('q', '')
    status_filter = request.GET.get('status')
    prod_status_filter = request.GET.get('prod_status')
    branch_filter = request.GET.get('branch', '') # 🌟 รับค่าตัวกรองสาขา

    # 🌟 กรองข้อมูลตาม "สาขา"
    if branch_filter and (is_manager or is_supervisor):
        queryset = queryset.filter(employee__department_id=branch_filter)

    if status_filter:
        if status_filter == 'PENDING_PRODUCTION':
             queryset = queryset.filter(is_deposit_paid=True, production_orders__isnull=True).distinct()
        elif status_filter == 'PENDING_CLOSING':
            queryset = queryset.filter(status='APPROVED', is_deposit_paid=False).distinct()
        elif status_filter == 'IN_PRODUCTION':
            queryset = queryset.filter(status='APPROVED', is_deposit_paid=True).distinct()
        else:
            queryset = queryset.filter(status=status_filter).distinct()

    total_departments_count = ProductionStatus.objects.count()

    if prod_status_filter:
        if prod_status_filter == 'CLOSED':
            valid_jobs = ProductionOrder.objects.filter(is_closed=True)
        else:
            valid_jobs = ProductionOrder.objects.filter(is_closed=False)
            if prod_status_filter == 'IN_PROGRESS_5':
                 valid_jobs = valid_jobs.annotate(dept_count=Count('completed_departments')).filter(status='IN_PROGRESS', dept_count__lt=total_departments_count)
            elif prod_status_filter == 'IN_PROGRESS_6':
                 valid_jobs = valid_jobs.annotate(dept_count=Count('completed_departments')).filter(status='IN_PROGRESS', dept_count=total_departments_count)
            else:
                  valid_jobs = valid_jobs.filter(status=prod_status_filter)
        valid_job_ids = list(valid_jobs.values_list('id', flat=True))
        queryset = queryset.filter(production_orders__in=valid_job_ids).distinct()

    if search_query:
        queryset = queryset.filter(Q(code__icontains=search_query) | Q(customer_name__icontains=search_query)).distinct()

    # 🌟 กรองวันที่ (ตั้งค่าเริ่มต้นเป็น "ช่วง 30 วันก่อนหน้า") 🌟
    date_start = request.GET.get('start_date')
    date_end = request.GET.get('end_date')

    if not date_start or date_start == 'None':
        date_start = (timezone.now().date() - datetime.timedelta(days=29)).strftime('%Y-%m-%d')
    if not date_end or date_end == 'None':
        date_end = timezone.now().date().strftime('%Y-%m-%d')

    # 🌟 [NEW] ถ้าเลือก 'สถานะเอกสาร' หรือ 'สถานะผลิต' ให้ข้ามการกรองวันที่ (ดึงข้อมูลมาทั้งหมด) 🌟
    if not status_filter and not prod_status_filter:
        queryset = queryset.filter(date__gte=date_start, date__lte=date_end).distinct()

    paginator = Paginator(queryset, 10)
    page_obj = paginator.get_page(request.GET.get('page'))

    for qt in page_obj:
        if qt.status == 'APPROVED' and qt.is_deposit_paid and qt.is_deposit_verified and not qt.production_orders.exists():
            qt.auto_delivery_date = get_auto_delivery_date(qt)

    return render(request, 'sales/quotation_list.html', {
        'page_obj': page_obj, 'search_query': search_query, 'is_manager': is_manager,
        'is_supervisor': is_supervisor, 'departments': departments, 'branch_filter': branch_filter,
        'status_filter': status_filter, 'prod_status_filter': prod_status_filter,
        'date_start': date_start, 'date_end': date_end, 'total_departments_count': total_departments_count
    })

@login_required
def quotation_create(request):
    if not is_sales_authorized(request.user):
        messages.error(request, "❌ บัญชีของคุณไม่มีสิทธิ์สร้างใบเสนอราคา")
        return redirect('dashboard')

    if request.method == 'POST':
        form = QuotationForm(request.POST)
        if form.is_valid():
            qt = form.save(commit=False)
            qt.created_by = request.user
            if hasattr(request.user, 'employee'): qt.employee = request.user.employee
            cust_id = request.POST.get('customer_id')
            if cust_id:
                try: qt.customer = Customer.objects.get(pk=cust_id)
                except Customer.DoesNotExist: pass
            now = datetime.datetime.now()
            thai_year = (now.year + 543) % 100
            prefix = f"QT-{thai_year:02d}{now.strftime('%m')}"
            last = Quotation.objects.filter(code__startswith=prefix).order_by('code').last()
            seq = int(last.code.split('-')[-1]) + 1 if last else 1
            qt.code = f"{prefix}-{seq:03d}"

            if not qt.payment_terms: qt.payment_terms = "-ชำระเงินมัดจำ 50% ของยอดรวมเพื่อยืนยันการสั่งซื้อ ส่วนที่เหลือชำระก่อนการจัดส่ง"
            if not qt.note: qt.note = "-ไม่มี-"

            qt.save()
            messages.success(request, f"ร่างใบเสนอราคา {qt.code} เรียบร้อย กรุณาเพิ่มรายการสินค้า")
            return redirect('quotation_edit', qt_id=qt.id)
    else:
        form = QuotationForm(initial={'date': datetime.date.today(), 'valid_until': datetime.date.today() + datetime.timedelta(days=15)})
    return render(request, 'sales/quotation_form.html', {'form': form})


@login_required
def quotation_edit(request, qt_id):

    if not is_sales_authorized(request.user):
        messages.error(request, "❌ บัญชีของคุณไม่มีสิทธิ์แก้ไขใบเสนอราคา")
        return redirect('dashboard')

    qt = get_object_or_404(Quotation, pk=qt_id)

    main_categories = Category.objects.all()
    products = Product.objects.filter(is_active=True, product_type='FG').exclude(code__contains='-JOB')

    products_list = []
    for p in products:
        products_list.append({
            'id': p.id, 'name': p.name, 'code': p.code, 'sell_price': float(p.sell_price), 'category_id': getattr(p, 'category_id', None)
        })

    upsale_categories = UpsaleCategory.objects.filter(is_active=True)
    upsale_catalogs = UpsaleCatalog.objects.filter(is_active=True)

    upsales_list = []
    for u in upsale_catalogs:
        upsales_list.append({
            'id': u.id, 'name': u.name, 'default_price': float(u.default_price), 'category_id': u.category_id
        })

    main_item_total = sum(i.quantity * i.unit_price for i in qt.items.all())
    upsale_total = sum(u.total_price for u in qt.upsales.all())
    item_total = main_item_total + upsale_total

    balance_due = qt.grand_total - qt.deposit_amount

    regions_data = {
        'ภาคเหนือ': ['เชียงราย', 'เชียงใหม่', 'น่าน', 'พะเยา', 'แพร่', 'แม่ฮ่องสอน', 'ลำปาง', 'ลำพูน', 'อุตรดิตถ์'],
        'ภาคกลาง': ['กรุงเทพมหานคร', 'กำแพงเพชร', 'ชัยนาท', 'นครนายก', 'นครปฐม', 'นครสวรรค์', 'นนทบุรี', 'ปทุมธานี', 'พระนครศรีอยุธยา', 'พิจิตร', 'พิษณุโลก', 'เพชรบูรณ์', 'ลพบุรี', 'สมุทรปราการ', 'สมุทรสงคราม', 'สมุทรสาคร', 'สระบุรี', 'สิงห์บุรี', 'สุโขทัย', 'สุพรรณบุรี', 'อ่างทอง', 'อุทัยธานี'],
        'ภาคอีสาน': ['กาฬสินธุ์', 'ขอนแก่น', 'ชัยภูมิ', 'นครพนม', 'นครราชสีมา', 'บึงกาฬ', 'บุรีรัมย์', 'มหาสารคาม', 'มุกดาหาร', 'ยโสธร', 'ร้อยเอ็ด', 'เลย', 'ศรีสะเกษ', 'สกลนคร', 'สุรินทร์', 'หนองคาย', 'หนองบัวลำภู', 'อำนาจเจริญ', 'อุดรธานี', 'อุบลราชธานี'],
        'ภาคตะวันออก': ['จันทบุรี', 'ฉะเชิงเทรา', 'ชลบุรี', 'ตราด', 'ปราจีนบุรี', 'ระยอง', 'สระแก้ว'],
        'ภาคตะวันตก': ['กาญจนบุรี', 'ตาก', 'ประจวบคีรีขันธ์', 'เพชรบุรี', 'ราชบุรี'],
        'ภาคใต้': ['กระบี่', 'ชุมพร', 'ตรัง', 'นครศรีธรรมราช', 'พังงา', 'พัทลุง', 'ภูเก็ต', 'ระนอง', 'สงขลา', 'สตูล', 'สุราษฎร์ธานี']
    }

    shipping_rates = list(ShippingRate.objects.all().values('origin_branch', 'destination_province', 'price'))
    shipping_rates_json = json.dumps([
        {'origin': r['origin_branch'], 'province': r['destination_province'], 'price': float(r['price'])} for r in shipping_rates
    ])

    if request.method == 'POST':
        if qt.status != 'DRAFT':
            messages.error(request, "❌ ไม่สามารถแก้ไขได้ เนื่องจากเอกสารนี้ถูกอนุมัติหรือล็อกไปแล้ว")
            return redirect('quotation_edit', qt_id=qt.id)

        if 'add_item' in request.POST:
            item_name = request.POST.get('item_name')
            qty = int(request.POST.get('quantity', 1))
            price = Decimal(request.POST.get('price', '0').replace(',', ''))
            product_id = request.POST.get('product_id')

            product_obj = None
            if product_id:
                try: product_obj = Product.objects.get(id=product_id)
                except Product.DoesNotExist: pass

            if item_name:
                QuotationItem.objects.create(quotation=qt, product=product_obj, item_name=item_name, quantity=qty, unit_price=price)
                calculate_totals(qt)
            return redirect('quotation_edit', qt_id=qt.id)

        elif 'add_upsale' in request.POST:
            desc = request.POST.get('upsale_desc')
            qty = Decimal(request.POST.get('upsale_qty', '1'))
            price = Decimal(request.POST.get('upsale_price', '0').replace(',', ''))
            if desc:
                QuotationUpsale.objects.create(quotation=qt, description=desc, quantity=qty, unit_price=price)
                calculate_totals(qt)
            return redirect('quotation_edit', qt_id=qt.id)

        elif 'delete_upsale' in request.POST:
            upsale_id = request.POST.get('upsale_id')
            try:
                 QuotationUpsale.objects.filter(id=upsale_id).delete()
                 calculate_totals(qt)
            except: pass
            return redirect('quotation_edit', qt_id=qt.id)

        elif 'update_info' in request.POST or 'finish_quote' in request.POST:
            qt.payment_terms = request.POST.get('payment_terms', '')
            qt.note = request.POST.get('note', '')
            qt.discount = Decimal(request.POST.get('discount', '0') or 0)

            qt.shipping_origin = request.POST.get('shipping_origin', '')
            qt.shipping_province = request.POST.get('shipping_province', '')
            qt.shipping_is_island = request.POST.get('shipping_is_island') == 'on'
            qt.shipping_is_oversize = request.POST.get('shipping_is_oversize') == 'on'
            qt.shipping_cost = Decimal(request.POST.get('shipping_cost', '0') or 0)

            calculate_totals(qt)

            if 'finish_quote' in request.POST:
                messages.success(request, f"✅ สร้างใบเสนอราคา {qt.code} เสร็จสมบูรณ์แล้ว! (รอผู้จัดการอนุมัติ)")
                return redirect('quotation_list')
            else:
                messages.success(request, "อัปเดตยอดเงินและหมายเหตุเรียบร้อย")
                return redirect('quotation_edit', qt_id=qt.id)

    return render(request, 'sales/quotation_edit.html', {
        'qt': qt, 'main_categories': main_categories, 'upsale_categories': upsale_categories,
        'products_json': json.dumps(products_list), 'upsales_json': json.dumps(upsales_list),
        'item_total': item_total, 'balance_due': balance_due,
        'regions_json': json.dumps(regions_data), 'shipping_rates_json': shipping_rates_json
    })

def calculate_totals(qt):
    item_sum = sum(item.quantity * item.unit_price for item in qt.items.all())
    upsale_sum = sum(u.quantity * u.unit_price for u in qt.upsales.all())
    total_goods = item_sum + upsale_sum

    shipping = qt.shipping_cost if qt.shipping_cost else Decimal(0)
    discount = qt.discount if qt.discount else Decimal(0)

    grand_total = (total_goods + shipping) - discount
    if grand_total < 0: grand_total = 0

    qt.subtotal = grand_total / Decimal('1.07')
    qt.tax_amount = grand_total - qt.subtotal
    qt.grand_total = grand_total
    qt.save()

@login_required
def delete_item(request, item_id):
    item = get_object_or_404(QuotationItem, pk=item_id)
    qt = item.quotation

    if qt.status != 'DRAFT':
        messages.error(request, "❌ ไม่สามารถลบรายการได้ เนื่องจากเอกสารนี้ถูกอนุมัติหรือล็อกไปแล้ว")
        return redirect('quotation_edit', qt_id=qt.id)

    item.delete()
    calculate_totals(qt)
    return redirect('quotation_edit', qt_id=qt.id)

@login_required
def quotation_clone(request, qt_id):
    old_qt = get_object_or_404(Quotation, pk=qt_id)
    now = datetime.datetime.now()
    thai_year = (now.year + 543) % 100
    prefix = f"QT-{thai_year:02d}{now.strftime('%m')}"
    last = Quotation.objects.filter(code__startswith=prefix).order_by('code').last()
    seq = int(last.code.split('-')[-1]) + 1 if last else 1
    new_code = f"{prefix}-{seq:03d}"

    new_qt = Quotation.objects.create(
        code=new_code,
        date=timezone.now().date(),
        valid_until=timezone.now().date() + datetime.timedelta(days=15),
        customer=old_qt.customer,
        customer_name=old_qt.customer_name,
        customer_address=old_qt.customer_address,
        customer_tax_id=old_qt.customer_tax_id,
        customer_phone=old_qt.customer_phone,
        employee=request.user.employee if hasattr(request.user, 'employee') else None,
        subtotal=old_qt.subtotal,
        discount=old_qt.discount,
        shipping_cost=old_qt.shipping_cost,
        tax_amount=old_qt.tax_amount,
        grand_total=old_qt.grand_total,
        status='DRAFT',
        payment_terms=old_qt.payment_terms if old_qt.payment_terms else "-ชำระเงินมัดจำ 50% ของยอดรวมเพื่อยืนยันการสั่งซื้อ ส่วนที่เหลือชำระก่อนการจัดส่ง",
        note=old_qt.note if old_qt.note else "-ไม่มี-",
    )

    for item in old_qt.items.all():
        QuotationItem.objects.create(
            quotation=new_qt, product=item.product, item_name=item.item_name,
            description=item.description, quantity=item.quantity, unit_price=item.unit_price, amount=item.amount
        )

    for upsale in old_qt.upsales.all():
        QuotationUpsale.objects.create(
            quotation=new_qt, description=upsale.description,
            quantity=upsale.quantity, unit_price=upsale.unit_price, total_price=upsale.total_price
        )

    messages.success(request, f"📋 คัดลอกเอกสารสำเร็จ! (คุณกำลังอยู่ในเอกสารใหม่ อ้างอิงข้อมูลจากใบเดิม {old_qt.code})")
    return redirect('quotation_edit', qt_id=new_qt.id)

@login_required
def quotation_approve(request, qt_id):
    qt = get_object_or_404(Quotation, pk=qt_id)
    current_emp = getattr(request.user, 'employee', None)
    qt.status = 'APPROVED'
    qt.approved_by = current_emp
    qt.approved_at = timezone.now()
    qt.save()
    messages.success(request, f"✅ อนุมัติใบเสนอราคา {qt.code} เรียบร้อยแล้ว")
    return redirect('quotation_list')

@login_required
def quotation_cancel(request, qt_id):
    qt = get_object_or_404(Quotation, pk=qt_id)
    current_emp = getattr(request.user, 'employee', None)
    is_manager = request.user.is_superuser or request.user.groups.filter(name__icontains='Manager').exists()
    is_owner = (qt.employee == current_emp) if current_emp else False

    if is_manager or is_owner:
        # 🌟 ด่านตรวจที่ 2: ห้ามยกเลิกถ้าสั่งผลิตแล้ว 🌟
        if qt.production_orders.exists():
            messages.error(request, "❌ ไม่อนุญาตให้ยกเลิก เนื่องจากเอกสารนี้ถูกส่งเข้ากระบวนการผลิตเรียบร้อยแล้ว")
        
        # 🌟 ด่านตรวจที่ 1: ห้ามยกเลิกถ้าจ่ายมัดจำแล้ว 🌟
        elif qt.is_deposit_paid:
            messages.error(request, "❌ ไม่สามารถยกเลิกได้ เนื่องจากมีการรับมัดจำแล้ว กรุณาทำเรื่องคืนเงินมัดจำก่อน")
            
        # 🌟 ผ่านด่านตรวจ จึงจะยอมให้ยกเลิก 🌟
        elif qt.status in ['DRAFT', 'APPROVED']:
            qt.status = 'CANCELLED'
            qt.save()
            messages.warning(request, f"⚠️ ยกเลิกใบเสนอราคา {qt.code} เรียบร้อยแล้ว (เอกสารนี้ถือเป็นโมฆะ)")
        else:
            messages.error(request, "❌ ไม่สามารถยกเลิกได้ เนื่องจากเอกสารถูกนำไปเปิดบิลแล้ว หรือสถานะไม่ถูกต้อง")
    else:
        messages.error(request, "❌ คุณไม่มีสิทธิ์ยกเลิกใบเสนอราคานี้")

    return redirect('quotation_list')

@login_required
def quotation_print(request, qt_id):
    qt = get_object_or_404(Quotation, pk=qt_id)
    company = CompanyInfo.objects.first()
    main_total = sum(item.quantity * item.unit_price for item in qt.items.all())
    upsale_total = sum(u.quantity * u.unit_price for u in qt.upsales.all())
    item_total = main_total + upsale_total
    return render(request, 'sales/quotation_print.html', {'qt': qt, 'company': company, 'item_total': item_total})

# ==========================================
# 🌟 [NEW] ฟังก์ชันแปลงตัวเลขเป็นภาษาไทย และพิมพ์สัญญามัดจำ 🌟
# ==========================================
def get_thai_baht_text(number):
    if number == 0: return "ศูนย์บาทถ้วน"
    import math
    number = round(float(number), 2)
    baht = math.floor(number)
    satang = int(round((number - baht) * 100))

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
            if val == 0:
                continue
            if pos == 0 and val == 1 and length > 1:
                res += "เอ็ด"
            elif pos == 1 and val == 1:
                res += "สิบ"
            elif pos == 1 and val == 2:
                res += "ยี่สิบ"
            else:
                res += numbers[val] + positions[pos]
        return res

    res = ""
    if baht > 0:
        res += read_num(baht) + "บาท"
    if satang > 0:
        res += read_num(satang) + "สตางค์"
    else:
        res += "ถ้วน"
    return res

@login_required
def print_deposit_contract(request, qt_id):
    qt = get_object_or_404(Quotation, pk=qt_id)
    company = CompanyInfo.objects.first()

    grand_total = qt.grand_total if qt.grand_total else Decimal('0.00')
    deposit_amount = qt.deposit_amount if qt.deposit_amount else Decimal('0.00')
    balance_due = grand_total - deposit_amount

    grand_total_text = get_thai_baht_text(grand_total)
    deposit_amount_text = get_thai_baht_text(deposit_amount)
    balance_due_text = get_thai_baht_text(balance_due)

    # 🌟 [NEW] ดึงวันที่จัดส่งจากใบสั่งผลิตที่เชื่อมโยงอยู่ (ถ้ามี)
    job = qt.production_orders.first()
    delivery_date = job.delivery_date if job else None

    return render(request, 'sales/print_deposit_contract.html', {
        'qt': qt,
        'company': company,
        'grand_total_text': grand_total_text,
        'deposit_amount_text': deposit_amount_text,
        'balance_due': balance_due,
        'balance_due_text': balance_due_text,
        'delivery_date': delivery_date, # 🌟 ส่งวันที่ไปให้หน้ากระดาษ
    })

@login_required
def export_sales_excel(request):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sales Report"
    ws.append(["วันที่", "เลขที่เอกสาร", "ประเภท", "ยอดขาย"])
    for p in POSOrder.objects.all():
        ws.append([p.created_at.strftime('%d/%m/%Y'), p.code, "POS", p.total_amount])
    for i in Invoice.objects.all():
        ws.append([i.date.strftime('%d/%m/%Y'), i.code, "Invoice", i.grand_total])
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename="Sales_Report.xlsx"'
    wb.save(response)
    return response

@login_required
def api_search_customer(request):
    query = request.GET.get('q', '').strip()
    if not query: return JsonResponse({'results': []})
    customers = Customer.objects.filter(Q(name__icontains=query) | Q(code__icontains=query) | Q(phone__icontains=query))[:10]
    results = []
    for c in customers:
        addr_parts = [c.address, f"ต.{c.sub_district}" if c.sub_district else "", f"อ.{c.district}" if c.district else "", f"จ.{c.province}" if c.province else "", c.zip_code]
        full_address = " ".join(filter(None, addr_parts))
        results.append({'id': c.id, 'name': c.name, 'code': c.code, 'address': full_address, 'tax_id': c.tax_id, 'phone': c.phone})
    return JsonResponse({'results': results})

@csrf_exempt
@login_required
def api_create_customer(request):
    if request.method == 'POST':
        try:
            name = request.POST.get('name')
            code = request.POST.get('code')
            phone = request.POST.get('phone')
            tax_id = request.POST.get('tax_id')
            address = request.POST.get('address')

            if not code:
                count = Customer.objects.count() + 1
                code = f"C{count:04d}"

            customer = Customer.objects.create(name=name, code=code, phone=phone, tax_id=tax_id, address=address)
            return JsonResponse({'success': True, 'customer': {'id': customer.id, 'name': customer.name, 'address': customer.address, 'tax_id': customer.tax_id, 'phone': customer.phone}})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    return JsonResponse({'success': False, 'error': 'Invalid Method'})

@login_required
def invoice_list(request):
    if not is_sales_authorized(request.user):
        messages.error(request, "❌ บัญชีของคุณไม่มีสิทธิ์เข้าถึงหน้ารายการใบเสร็จ")
        return redirect('dashboard')

    target_employees, _ = get_target_employees(request.user)
    qs_invoice = get_sales_queryset(Invoice, request.user, target_employees).prefetch_related('payment_history', 'quotation_ref__production_orders')
    qs_pos = get_sales_queryset(POSOrder, request.user, target_employees)

    # 🌟 [NEW] ระบบดึงข้อมูลสาขา เพื่อใช้เป็นตัวกรอง
    from hr.models import Department

    # 🌟 เช็คสิทธิ์และระดับ (Rank) ของพนักงาน
    is_manager = request.user.is_superuser
    is_supervisor = False
    current_emp = getattr(request.user, 'employee', None)

    if current_emp:
        rank = current_emp.business_rank.lower() if current_emp.business_rank else ""
        if rank in ['manager', 'director'] or 'บัญชี' in current_emp.department.name:
            is_manager = True
        elif rank == 'supervisor':
            is_supervisor = True

    # 🌟 โหลดรายชื่อสาขาตามสิทธิ์ (กรองเฉพาะ "ทีม" และ "สาขา" เท่านั้น)
    if is_manager:
        departments = list(Department.objects.filter(
            Q(name__icontains='ทีม') |
            Q(name__icontains='สาขา')
        ).order_by('name'))
    elif is_supervisor and current_emp.department:
        departments = list(Department.objects.filter(id=current_emp.department.id))
    else:
        departments = [] # พนักงานทั่วไป ไม่ต้องเห็นสาขา

    # 🌟 ลบคำว่า "แผนก" ออกจากชื่อ เพื่อความสะอาดตาบนหน้าเว็บ
    for d in departments:
        d.name = d.name.replace('แผนก', '').strip()

    # 🌟 รับค่าการค้นหาจากฟอร์ม
    search_query = request.GET.get('q', '')
    status_filter = request.GET.get('status', '')
    branch_filter = request.GET.get('branch', '') # 🌟 รับค่าสาขา

    # 🌟 กรองข้อมูลตาม "สาขา"
    if branch_filter and (is_manager or is_supervisor):
        qs_invoice = qs_invoice.filter(employee__department_id=branch_filter)
        qs_pos = qs_pos.filter(employee__department_id=branch_filter)

    # กรองข้อมูลอื่นๆ
    if search_query:
        qs_invoice = qs_invoice.filter(Q(code__icontains=search_query) | Q(customer__name__icontains=search_query))
        qs_pos = qs_pos.filter(code__icontains=search_query)

    if status_filter:
        if status_filter == 'PENDING':
            qs_invoice = qs_invoice.filter(Q(status='PENDING') | Q(status='UNPAID'))
            qs_pos = qs_pos.filter(Q(status='PENDING') | Q(status='UNPAID'))
        else:
            qs_invoice = qs_invoice.filter(status=status_filter)
            qs_pos = qs_pos.filter(status=status_filter)

    # 🌟 กรองวันที่
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')

    # ถ้าไม่มีการเลือกวันที่มา (โหลดหน้าแรก) ให้บังคับดึงข้อมูลของ "วันนี้"
    if not start_date or start_date == 'None':
        start_date = timezone.now().date().strftime('%Y-%m-%d')
    if not end_date or end_date == 'None':
        end_date = timezone.now().date().strftime('%Y-%m-%d')

    qs_invoice = qs_invoice.filter(date__gte=start_date, date__lte=end_date)
    qs_pos = qs_pos.filter(created_at__date__gte=start_date, created_at__date__lte=end_date)

    combined_list = sorted(list(qs_invoice) + list(qs_pos), key=lambda x: x.created_at, reverse=True)
    paginator = Paginator(combined_list, 15)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'sales/invoice_list.html', {
        'page_obj': page_obj, 'search_query': search_query,
        'start_date': start_date, 'end_date': end_date, 'status_filter': status_filter,
        'departments': departments, 'branch_filter': branch_filter,
        'is_manager': is_manager, 'is_supervisor': is_supervisor
    })

@login_required
def confirm_payment(request, doc_type, doc_id):
    if doc_type == 'pos':
        obj = get_object_or_404(POSOrder, id=doc_id)
        if obj.status != 'PAID':
            obj.status = 'PAID'
            obj.save()
            sale_amt = getattr(obj, 'total_amount', getattr(obj, 'grand_total', 0))
            if obj.employee:
                process_commission_logic(sale_amt, obj.employee, obj.code)
        messages.success(request, f"✅ ยืนยันรับชำระเงินเอกสาร {obj.code} ปิดการขายเรียบร้อยแล้ว!")
    else:
        obj = get_object_or_404(Invoice, id=doc_id)
        if obj.status == 'PENDING':
            pending_payments = obj.payment_history.filter(status='PENDING')
            pending_payments.update(status='VERIFIED')

            if obj.balance_amount <= 0:
                obj.status = 'PAID'
                obj.save()
                sale_amt = getattr(obj, 'total_amount', getattr(obj, 'grand_total', 0))
                if obj.employee:
                    process_commission_logic(sale_amt, obj.employee, obj.code)
                messages.success(request, f"✅ ยืนยันรับชำระเงินครบ 100% เอกสาร {obj.code} ปิดการขายเรียบร้อยแล้ว!")
            else:
                obj.status = 'UNPAID'
                obj.save()
                messages.success(request, f"✅ ยืนยันการแบ่งชำระเงินเอกสาร {obj.code} เรียบร้อยแล้ว! (ยอดคงค้าง: {obj.balance_amount:,.2f} บาท)")
    return redirect('invoice_list')

@login_required
def record_invoice_payment(request, inv_id):
    inv = get_object_or_404(Invoice, pk=inv_id)
    if request.method == 'POST':
        method = request.POST.get('payment_method', 'TRANSFER')
        date_str = request.POST.get('payment_date')
        amount_str = request.POST.get('received_amount', '0').replace(',', '')

        try:
            amount = Decimal(amount_str)
        except:
            amount = Decimal('0.00')

        if amount > 0:
            payment = InvoicePayment(
                invoice=inv,
                amount=amount,
                payment_method=method,
                payment_date=parse_thai_date(date_str) if date_str else timezone.now().date()
            )
            if method == 'TRANSFER' and 'transfer_slip' in request.FILES:
                payment.transfer_slip = request.FILES['transfer_slip']
            elif method == 'CHECK':
                payment.check_number = request.POST.get('check_number', '')
                payment.check_bank = request.POST.get('check_bank', '')
                if 'check_slip' in request.FILES:
                    payment.check_slip = request.FILES['check_slip']
            payment.save()

            inv.balance_amount -= amount
            if inv.balance_amount < 0:
                inv.balance_amount = Decimal('0.00')

            inv.status = 'PENDING'
            inv.save()
            messages.success(request, f"💰 บันทึกรับชำระเงิน {amount:,.2f} บาท สำหรับเอกสาร {inv.code} สำเร็จ! (รอตรวจสอบยอดจากฝ่ายบัญชี)")

    return redirect('invoice_list')

@login_required
def delete_invoice_payment(request, pay_id):
    # ป้องกันไม่ให้แผนกอื่นมาลบ
    if not is_sales_authorized(request.user):
        messages.error(request, "❌ บัญชีของคุณไม่มีสิทธิ์ดำเนินการนี้")
        return redirect('invoice_list')

    payment = get_object_or_404(InvoicePayment, pk=pay_id)
    inv = payment.invoice

    # ดักไว้เผื่อมีคนพยายามลบรายการที่บัญชียืนยัน (VERIFIED) ไปแล้ว
    if payment.status == 'VERIFIED':
        messages.error(request, "❌ ไม่สามารถลบได้ เนื่องจากฝ่ายบัญชีได้ทำการตรวจสอบและรับเงินเข้าระบบไปแล้ว")
        return redirect('invoice_list')

    # ดึงยอดเงินที่กำลังจะลบ
    amount_to_return = payment.amount

    # ลบข้อมูลในฐานข้อมูล
    payment.delete()

    # คืนยอดค้างชำระให้บิลนั้นๆ
    inv.balance_amount += amount_to_return

    # ถ้ายอดค้างชำระกลับมาเท่ากับยอดเต็ม ให้ปรับสถานะเป็นยังไม่ชำระ
    if inv.balance_amount >= inv.grand_total:
        inv.status = 'UNPAID'
    else:
        # ถ้ายอดค้างยังน้อยกว่ายอดเต็ม แปลว่ายังมีรายการจ่ายอื่นค้างอยู่ ให้สถานะยังคงรอตรวจ
        inv.status = 'PENDING'

    inv.save()

    messages.success(request, f"🗑️ ลบรายการรับชำระ {amount_to_return:,.2f} บาท สำเร็จ! (ระบบคืนยอดค้างชำระให้บิล {inv.code} แล้ว)")
    return redirect('invoice_list')

@login_required
def invoice_print(request, inv_id):
    inv = get_object_or_404(Invoice, pk=inv_id)
    company = CompanyInfo.objects.first()

    items = []
    item_total = Decimal('0.00')
    subtotal = Decimal('0.00')
    tax_amount = Decimal('0.00')
    discount = Decimal('0.00')
    shipping_cost = Decimal('0.00')

    note = "-ไม่มี-"
    if inv.status == 'PAID':
        p_date = inv.payment_date.strftime('%d/%m/%Y') if inv.payment_date else '-'
        if inv.payment_method == 'TRANSFER':
            note = f"ชำระโดย: โอนเงินเข้าบัญชี (วันที่ {p_date})"
        elif inv.payment_method == 'CHECK':
            note = f"ชำระโดย: เช็คธนาคาร {inv.check_bank} เลขที่ {inv.check_number} (วันที่ {p_date})"
        elif inv.payment_method == 'CASH':
            note = f"ชำระโดย: เงินสด (วันที่ {p_date})"
        else:
            note = "ชำระเงินเรียบร้อยแล้ว"
    else:
        if inv.quotation_ref:
            if inv.quotation_ref.payment_terms and inv.quotation_ref.payment_terms != "-ไม่มี-":
                note = f"เงื่อนไขการชำระเงิน:\n{inv.quotation_ref.payment_terms}"
            elif inv.quotation_ref.note:
                note = inv.quotation_ref.note

    if inv.quotation_ref:
        qt = inv.quotation_ref
        items = list(qt.items.all())
        for item in items:
            item.amount = item.quantity * item.unit_price
            item_total += Decimal(str(item.amount))

        for u in qt.upsales.all():
            items.append(u)
            item_total += Decimal(str(u.total_price))

        subtotal = qt.subtotal
        tax_amount = qt.tax_amount
        discount = qt.discount
        shipping_cost = qt.shipping_cost

    if not getattr(inv, 'customer_name', None) and inv.quotation_ref:
            inv.customer_name = qt.customer_name
            inv.customer_address = qt.customer_address
            inv.customer_tax_id = qt.customer_tax_id
            inv.customer_phone = qt.customer_phone

    if not hasattr(inv, 'total_amount'):
        inv.total_amount = inv.grand_total

    if not hasattr(inv, 'deposit_amount'):
        inv.deposit_amount = Decimal('0.00')
        inv.balance_amount = inv.grand_total

    context = {
        'inv': inv, 'company': company, 'items': items,
        'item_total': item_total, 'subtotal': subtotal, 'tax_amount': tax_amount,
        'discount': discount, 'shipping_cost': shipping_cost, 'note': note,
    }
    return render(request, 'sales/invoice_print.html', context)

@login_required
def deposit_list(request):
    target_employees, _ = get_target_employees(request.user)
    qs = get_sales_queryset(Quotation, request.user, target_employees).filter(is_deposit_paid=True)

    search_query = request.GET.get('q', '')
    if search_query:
        qs = qs.filter(Q(code__icontains=search_query) | Q(customer_name__icontains=search_query))

    status_filter = request.GET.get('status')
    if status_filter == 'VERIFIED':
        qs = qs.filter(is_deposit_verified=True)
    elif status_filter == 'PENDING':
        qs = qs.filter(is_deposit_verified=False)

    qs = qs.order_by('-deposit_date', '-created_at')
    paginator = Paginator(qs, 15)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'sales/deposit_list.html', {
        'page_obj': page_obj, 'search_query': search_query, 'status_filter': status_filter
    })

@login_required
def verify_deposit(request, qt_id):
    qt = get_object_or_404(Quotation, pk=qt_id)
    qt.is_deposit_verified = True
    qt.save()
    messages.success(request, f"✅ บัญชียืนยันตรวจสอบยอดมัดจำของ {qt.code} เรียบร้อยแล้ว!")
    return redirect('deposit_list')

@login_required
def deposit_print(request, qt_id):
    qt = get_object_or_404(Quotation, pk=qt_id)
    company = CompanyInfo.objects.first()

    main_total = sum(item.quantity * item.unit_price for item in qt.items.all())
    upsale_total = sum(u.quantity * u.unit_price for u in qt.upsales.all())
    item_total = main_total + upsale_total

    balance_due = qt.grand_total - qt.deposit_amount
    return render(request, 'sales/deposit_print.html', {
        'qt': qt, 'company': company, 'item_total': item_total, 'balance_due': balance_due
    })

# ==========================================
# 🌟 [NEW] ระบบ CRM ติดตามลูกค้ามุ่งหวัง (Leads) 🌟
# ==========================================
@login_required
def crm_board(request):
    if not is_sales_authorized(request.user):
        messages.error(request, "❌ บัญชีของคุณไม่มีสิทธิ์เข้าถึงระบบ CRM")
        return redirect('dashboard')

    target_employees, scope_title = get_target_employees(request.user)

    leads = get_sales_queryset(CustomerLead, request.user, target_employees)\
        .select_related('employee', 'employee__department')\
        .order_by('-created_at')

    # 🌟 [FIXED] กรองรายชื่อให้โชว์เฉพาะพนักงานแผนก "ขาย" หรือ "Sales" เท่านั้น 🌟
    all_emps_in_scope = target_employees.filter(
        Q(department__name__icontains='ขาย') |
        Q(department__name__icontains='Sales') |
        Q(department__name__icontains='Marketing')
    ).order_by('first_name')

    # ระบบค้นหาและกรองข้อมูล
    search_q = request.GET.get('q', '')
    status_f = request.GET.get('status', '')
    channel_f = request.GET.get('channel', '')
    start_date = request.GET.get('start_date', '')
    end_date = request.GET.get('end_date', '')
    emp_f = request.GET.get('employee', '')

    if search_q:
        leads = leads.filter(Q(code__icontains=search_q) | Q(customer_name__icontains=search_q) | Q(phone__icontains=search_q))
    if status_f:
        leads = leads.filter(status=status_f)
    if channel_f:
        leads = leads.filter(channel=channel_f)
    if start_date:
        leads = leads.filter(date__date__gte=start_date)
    if end_date:
        leads = leads.filter(date__date__lte=end_date)
    if emp_f:
        leads = leads.filter(employee_id=emp_f)

    paginator = Paginator(leads, 20)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'sales/crm_board.html', {
        'leads': page_obj,
        'search_q': search_q,
        'status_f': status_f,
        'channel_f': channel_f,
        'start_date': start_date,
        'end_date': end_date,
        'emp_f': emp_f,
        'scope_title': scope_title,
        'status_choices': CustomerLead.STATUS_CHOICES,
        'channel_choices': CustomerLead.CHANNEL_CHOICES,
        'employees': all_emps_in_scope # ส่งรายชื่อเฉพาะเซลส์ไปทำ Dropdown
    })

@login_required
def crm_lead_create(request):
    if request.method == 'POST':
        name = request.POST.get('customer_name')
        phone = request.POST.get('phone', '')
        channel = request.POST.get('channel', 'LINE')
        requirements = request.POST.get('requirements', '')

        # รันรหัสลูกค้ามุ่งหวัง (Auto ID)
        now = datetime.datetime.now()
        thai_year = (now.year + 543) % 100
        prefix = f"LD-{thai_year:02d}{now.strftime('%m')}"
        last = CustomerLead.objects.filter(code__startswith=prefix).order_by('code').last()
        seq = int(last.code.split('-')[-1]) + 1 if last else 1
        new_code = f"{prefix}-{seq:04d}"

        current_emp = getattr(request.user, 'employee', None)

        CustomerLead.objects.create(
            code=new_code,
            customer_name=name,
            phone=phone,
            channel=channel,
            requirements=requirements,
            employee=current_emp
        )
        messages.success(request, f"✅ สร้างข้อมูลลูกค้ามุ่งหวัง {new_code} เรียบร้อยแล้ว!")
    return redirect('crm_board')

@login_required
def crm_lead_update(request, lead_id):
    lead = get_object_or_404(CustomerLead, pk=lead_id)
    if request.method == 'POST':
        lead.customer_name = request.POST.get('customer_name', lead.customer_name)
        lead.phone = request.POST.get('phone', lead.phone)
        lead.channel = request.POST.get('channel', lead.channel)
        lead.requirements = request.POST.get('requirements', lead.requirements)
        lead.status = request.POST.get('status', lead.status)
        lead.date = timezone.now() # อัปเดตเวลาล่าสุดทุกครั้งที่มีการเคลื่อนไหว
        lead.save()
        messages.success(request, f"✅ อัปเดตสถานะข้อมูลลูกค้า {lead.code} เรียบร้อยแล้ว!")
    return redirect('crm_board')

# ==========================================
# 🌟 [NEW] ระบบจัดการนัดหมาย (Appointments) 🌟
# ==========================================
@login_required
def appointment_board(request):
    if not is_sales_authorized(request.user):
        messages.error(request, "❌ บัญชีของคุณไม่มีสิทธิ์เข้าถึงระบบนัดหมาย")
        return redirect('dashboard')

    target_employees, _ = get_target_employees(request.user)

    # โหลดข้อมูลนัดหมายทั้งหมดมาโชว์ในตาราง (พ่วงข้อมูลพนักงานมาด้วย)
    appointments = get_sales_queryset(Appointment, request.user, target_employees)\
        .select_related('employee', 'employee__department', 'lead')\
        .order_by('-appointment_date')

    # ระบบตัวกรองและค้นหาในตาราง
    search_q = request.GET.get('q', '')
    type_f = request.GET.get('type', '')
    status_f = request.GET.get('status', '')
    start_date = request.GET.get('start_date', '')
    end_date = request.GET.get('end_date', '')

    if search_q:
        appointments = appointments.filter(
            Q(lead__customer_name__icontains=search_q) |
            Q(lead__code__icontains=search_q) |
            Q(details__icontains=search_q) |
            Q(employee__first_name__icontains=search_q)
        )
    if type_f:
        appointments = appointments.filter(appointment_type=type_f)
    if status_f:
        appointments = appointments.filter(status=status_f)
    if start_date:
        appointments = appointments.filter(appointment_date__date__gte=start_date)
    if end_date:
        appointments = appointments.filter(appointment_date__date__lte=end_date)

    paginator = Paginator(appointments, 20)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'sales/appointment_board.html', {
        'appointments': page_obj,
        'search_q': search_q,
        'type_f': type_f,
        'status_f': status_f,
        'start_date': start_date,
        'end_date': end_date,
        'type_choices': Appointment.TYPE_CHOICES,
        'status_choices': Appointment.STATUS_CHOICES,
    })

@login_required
def appointment_create_modal(request):
    if request.method == 'POST':
        lead_id = request.POST.get('lead_id')
        lead_to_book = get_object_or_404(CustomerLead, pk=lead_id)
        apt_date_str = request.POST.get('appointment_date')
        apt_type = request.POST.get('appointment_type')
        details = request.POST.get('details')

        if apt_date_str:
            Appointment.objects.create(
                lead=lead_to_book,
                appointment_date=apt_date_str,
                appointment_type=apt_type,
                details=details,
                employee=getattr(request.user, 'employee', None)
            )
            messages.success(request, f"📅 สร้างรายการนัดหมายสำหรับ {lead_to_book.customer_name} เรียบร้อยแล้ว!")
    return redirect('crm_board')

@login_required
def appointment_update(request, apt_id):
    apt = get_object_or_404(Appointment, pk=apt_id)
    if request.method == 'POST':
        apt.status = request.POST.get('status', apt.status)
        apt.details = request.POST.get('details', apt.details)
        apt_date_str = request.POST.get('appointment_date')
        if apt_date_str:
            apt.appointment_date = apt_date_str
        apt.save()
        messages.success(request, "✅ อัปเดตข้อมูลการนัดหมายเรียบร้อยแล้ว!")
    return redirect('appointment_board_global')