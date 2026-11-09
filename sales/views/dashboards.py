import json
import datetime
import pytz
from decimal import Decimal
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.db.models import Sum, Q
from django.utils import timezone
from django.utils.dateparse import parse_date
from datetime import timedelta

# Models
from sales.models import Quotation, POSOrder, Invoice, CommissionAllocation
from hr.models import Department, Employee
from manufacturing.models import ProductionOrder, MfgBranch, BlueprintClaim
from master_data.models import CompanyInfo

# Services
from sales.services import is_sales_authorized, get_target_employees, get_sales_queryset, parse_thai_date

@login_required
def sales_dashboard(request):
    if not is_sales_authorized(request.user): return redirect('dashboard')

    target_employees, scope_title = get_target_employees(request.user)
    tz_bkk = pytz.timezone('Asia/Bangkok')
    today_bkk = timezone.now().astimezone(tz_bkk).date()

    is_manager = False
    is_supervisor = False
    current_emp = getattr(request.user, 'employee', None)
    user_groups = list(request.user.groups.values_list('name', flat=True))

    # 🌟 [NEW] เช็กสิทธิ์ Manager และ Supervisor จากสวิตช์คีย์การ์ด (Groups) อย่างแม่นยำ
    if request.user.is_superuser or 'Manager_Team' in user_groups or 'Executive' in user_groups or 'Accounting_Team' in user_groups:
        is_manager = True
    elif 'Supervisor_Team' in user_groups:
        is_supervisor = True

    team_members = []
    if is_manager:
        departments = list(Department.objects.filter(name__icontains='สาขา').order_by('name'))
        for d in departments: d.name = d.name.replace('แผนก', '').strip()
    elif is_supervisor and current_emp and current_emp.department:
        departments = []
        team_members = list(Employee.objects.filter(department=current_emp.department).order_by('first_name'))
    else:
        departments = []

    if is_manager:
        template_name = 'dashboards/knockdown/manager.html'
    elif is_supervisor:
        template_name = 'dashboards/knockdown/supervisor.html'
    else:
        template_name = 'dashboards/knockdown/sales.html'

    return render(request, template_name, {
        'scope_title': scope_title, 'start_date': today_bkk.strftime('%Y-%m-%d'),
        'end_date': today_bkk.strftime('%Y-%m-%d'), 'departments': departments,
        'team_members': team_members, 'is_manager': is_manager, 'is_supervisor': is_supervisor
    })

@login_required
def api_dashboard_data(request):
    if not is_sales_authorized(request.user): return JsonResponse({'error': 'Unauthorized'}, status=403)

    target_employees, scope_title = get_target_employees(request.user)
    emp = getattr(request.user, 'employee', None)

    tz_bkk = pytz.timezone('Asia/Bangkok')
    today_bkk = timezone.now().astimezone(tz_bkk).date()

    start_date_str = request.GET.get('start_date')
    end_date_str = request.GET.get('end_date')

    start_date = parse_date(start_date_str) if start_date_str else today_bkk
    end_date = parse_date(end_date_str) if end_date_str else today_bkk
    end_date_inclusive = end_date + timedelta(days=1)

    branch_filter = request.GET.get('branch', '')
    emp_filter = request.GET.get('employee', '')

    # 🌟 [NEW] อ่านสวิตช์ Manager และ Supervisor จาก Groups เพื่อวาดกราฟ
    user_groups = list(request.user.groups.values_list('name', flat=True))
    is_manager_role = request.user.is_superuser or 'Manager_Team' in user_groups or 'Executive' in user_groups or 'Accounting_Team' in user_groups
    is_supervisor_role = 'Supervisor_Team' in user_groups

    if branch_filter and is_manager_role:
        if branch_filter != 'sum_only':
            target_employees = target_employees.filter(department_id=branch_filter)
    elif emp_filter and is_supervisor_role and not is_manager_role:
        if emp_filter not in ['sum_only', 'compare_all']:
            target_employees = target_employees.filter(id=emp_filter)

    pos_qs_all = get_sales_queryset(POSOrder, request.user, target_employees).filter(created_at__gte=start_date, created_at__lt=end_date_inclusive)
    inv_qs_all = get_sales_queryset(Invoice, request.user, target_employees).filter(date__gte=start_date, date__lte=end_date)

    total_sales = float((pos_qs_all.filter(status='PAID').aggregate(Sum('total_amount'))['total_amount__sum'] or 0) +
                        (inv_qs_all.filter(status='PAID').aggregate(Sum('grand_total'))['grand_total__sum'] or 0))

    today_start = datetime.datetime.combine(today_bkk, datetime.time.min)
    today_start = tz_bkk.localize(today_start)
    tomorrow_start = today_start + timedelta(days=1)

    pos_today_count = get_sales_queryset(POSOrder, request.user, target_employees).filter(created_at__gte=today_start, created_at__lt=tomorrow_start).count()
    inv_today_count = get_sales_queryset(Invoice, request.user, target_employees).filter(date=today_bkk).count()
    total_orders_today = pos_today_count + inv_today_count

    qt_all_qs = get_sales_queryset(Quotation, request.user, target_employees)
    pending_approval = qt_all_qs.filter(status='DRAFT').count()
    pending_closing = qt_all_qs.filter(status='APPROVED', is_deposit_paid=False).count()

    # 🌟 [FIXED - Option B] ลบเงื่อนไข is_deposit_verified=True ออกแล้ว
    # ตอนนี้แค่เซลส์รับเงินมา (is_deposit_paid=True) บิลก็จะถูกนับลงช่องนี้ทันที!
    in_production = qt_all_qs.filter(
        Q(status='APPROVED', is_deposit_paid=True) | Q(status='CONVERTED')
    ).exclude(
        production_orders__delivery_status__name__in=['ส่งมอบสำเร็จ', 'ลูกค้าเซ็นรับแล้ว', 'จัดส่งเรียบร้อย']
    ).distinct().count()

    waiting_delivery_count = 0
    if not is_manager_role and not is_supervisor_role:
        waiting_delivery_count = qt_all_qs.filter(
            Q(status='APPROVED', is_deposit_paid=True, is_deposit_verified=True) | Q(status='CONVERTED')
        ).filter(
            Q(production_orders__status='COMPLETED') | Q(production_orders__isnull=False, status='CONVERTED')
        ).exclude(
            production_orders__delivery_status__name__in=['ส่งมอบสำเร็จ', 'ลูกค้าเซ็นรับแล้ว', 'จัดส่งเรียบร้อย']
        ).distinct().count()

    chart_labels, chart_data, chart_title, chart_type = [], [], "", "bar"
    pos_raw = list(pos_qs_all.filter(status='PAID').values('total_amount', 'employee__department__name', 'employee__first_name'))
    inv_raw = list(inv_qs_all.filter(status='PAID').values('grand_total', 'employee__department__name', 'employee__first_name'))

    if is_manager_role:
        if branch_filter == 'sum_only':
            chart_title = "ยอดขายรวมทุกสาขา"
            chart_labels = ["ยอดรวมสุทธิ"]
            chart_data = [total_sales]
        else:
            chart_title = "ยอดขายเปรียบเทียบรายสาขา"
            team_dict = {}
            for p in pos_raw:
                t = p['employee__department__name'] or 'ไม่ระบุสาขา'
                team_dict[t] = team_dict.get(t, 0) + float(p['total_amount'] or 0)
            for i in inv_raw:
                t = i['employee__department__name'] or 'ไม่ระบุสาขา'
                team_dict[t] = team_dict.get(t, 0) + float(i['grand_total'] or 0)

            sorted_data = sorted(team_dict.items(), key=lambda x: x[1], reverse=True)
            chart_labels, chart_data = [x[0] for x in sorted_data], [x[1] for x in sorted_data]

    elif is_supervisor_role:
        if emp_filter == 'sum_only':
            dept_name = emp.department.name if (emp and emp.department) else ''
            chart_title = f"ยอดขายรวมทั้งทีม ({dept_name})"
            chart_labels = ["ยอดรวมสุทธิ"]
            chart_data = [total_sales]
        elif emp_filter and emp_filter != 'compare_all':
            chart_title = "ยอดขายส่วนตัว"
            emp_name = target_employees.first().first_name if target_employees.exists() else "พนักงาน"
            chart_labels = [emp_name]
            chart_data = [total_sales]
        else:
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

    recent_pos = list(get_sales_queryset(POSOrder, request.user, target_employees).filter(created_at__gte=start_date, created_at__lt=end_date_inclusive).select_related('employee', 'employee__department').order_by('-created_at')[:10])
    recent_inv = list(get_sales_queryset(Invoice, request.user, target_employees).filter(date__gte=start_date, date__lte=end_date).select_related('employee', 'employee__department', 'quotation_ref').prefetch_related('quotation_ref__production_orders').order_by('-created_at')[:10])

    combined = sorted(recent_pos + recent_inv, key=lambda x: x.created_at, reverse=True)[:10]
    recent_sales_data = []

    for item in combined:
        is_pos = isinstance(item, POSOrder)
        qt, job = "-", "-"

        if not is_pos and getattr(item, 'quotation_ref', None):
            qt = item.quotation_ref.code
            jobs = item.quotation_ref.production_orders.all()
            if jobs.exists(): job = ", ".join([j.code for j in jobs])

        item_time_bkk = item.created_at.astimezone(tz_bkk)

        recent_sales_data.append({
            'time': item_time_bkk.strftime('%H:%M') if item_time_bkk.date() == today_bkk else item_time_bkk.strftime('%d/%m/%Y'),
            'code': item.code, 'is_pos': is_pos, 'qt_code': qt, 'job_code': job,
            'employee_name': item.employee.first_name if item.employee else '-',
            'employee_branch': item.employee.department.name if item.employee and item.employee.department else '-',
            'employee_photo': item.employee.photo.url if item.employee and getattr(item.employee, 'photo', None) else None,
            'employee_initial': item.employee.first_name[0] if item.employee and item.employee.first_name else '-',
            'amount': float(item.total_amount) if is_pos else float(item.grand_total)
        })

    accumulated_commission = 0
    if emp:
        accumulated_commission = CommissionAllocation.objects.filter(employee=emp, status='PENDING').aggregate(Sum('amount'))['amount__sum'] or 0

    return JsonResponse({
        'total_sales': total_sales, 'total_orders_today': total_orders_today,
        'pending_approval': pending_approval, 'pending_closing': pending_closing,
        'in_production': in_production, 'chart_labels': chart_labels,
        'chart_data': chart_data, 'chart_title': chart_title,
        'chart_type': chart_type, 'scope_title': scope_title,
        'recent_sales': recent_sales_data, 'accumulated_commission': float(accumulated_commission),
        'waiting_delivery_count': waiting_delivery_count
    })

@login_required
def sales_hub(request):
    if not is_sales_authorized(request.user): return redirect('dashboard')
    target_employees, _ = get_target_employees(request.user)
    qt_qs = get_sales_queryset(Quotation, request.user, target_employees)
    inv_qs = get_sales_queryset(Invoice, request.user, target_employees)
    pos_qs = get_sales_queryset(POSOrder, request.user, target_employees)

    tz_bkk = pytz.timezone('Asia/Bangkok')
    today_bkk = timezone.now().astimezone(tz_bkk).date()
    today_start = tz_bkk.localize(datetime.datetime.combine(today_bkk, datetime.time.min))
    tomorrow_start = today_start + timedelta(days=1)

    ready_quotes = qt_qs.filter(status='APPROVED').order_by('-created_at')
    today_invoices = inv_qs.filter(date=today_bkk).order_by('-created_at')
    today_pos = pos_qs.filter(created_at__gte=today_start, created_at__lt=tomorrow_start).order_by('-created_at')

    return render(request, 'sales/sales_hub.html', {
        'ready_quotes': ready_quotes, 'today_invoices': today_invoices, 'today_pos': today_pos
    })

@login_required
def sales_timeline(request):
    if not is_sales_authorized(request.user): return redirect('dashboard')
    tz_bkk = pytz.timezone('Asia/Bangkok')
    today_bkk = timezone.now().astimezone(tz_bkk).date()

    company_info = CompanyInfo.objects.first()
    max_quota = company_info.weekly_job_quota if company_info and company_info.weekly_job_quota else 25

    deposit_date_str = request.GET.get('deposit_date')
    if deposit_date_str:
        try: calc_deposit_date = parse_thai_date(deposit_date_str) or today_bkk
        except: calc_deposit_date = today_bkk
    else: calc_deposit_date = today_bkk

    current_check_date = calc_deposit_date
    weeks_pushed = 0
    while True:
        iso_year, iso_week, _ = current_check_date.isocalendar()
        check_cohort = f"{iso_year}-W{iso_week:02d}"
        total_qty_in_week = ProductionOrder.objects.filter(cohort_week=check_cohort, is_closed=False).aggregate(Sum('quantity'))['quantity__sum'] or 0
        if total_qty_in_week < max_quota: break
        weeks_pushed += 1
        current_check_date += datetime.timedelta(days=7)

    smart_eta_date = calc_deposit_date + datetime.timedelta(days=22 + (weeks_pushed * 7))

    def format_week_range(d):
        iso_y, iso_w, _ = d.isocalendar()
        monday = datetime.date.fromisocalendar(iso_y, iso_w, 1)
        sunday = monday + datetime.timedelta(days=6)
        y_str = str(sunday.year + 543)[-2:]
        if monday.month == sunday.month: return f"จ.{monday.day}-อา.{sunday.day}/{monday.month}/{y_str}"
        else: return f"จ.{monday.day}/{monday.month}-อา.{sunday.day}/{sunday.month}/{y_str}"

    chart_labels, chart_labels_display, chart_week_starts, chart_week_ends = [], [], [], []
    chart1_ordered, chart1_pending, chart1_delivered = [], [], []

    start_date = today_bkk - datetime.timedelta(weeks=4)
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
        try: filter_date = parse_thai_date(filter_date_str) or today_bkk
        except: filter_date = today_bkk
    else: filter_date = today_bkk

    f_iso_year, f_iso_week, _ = filter_date.isocalendar()
    target_cohort = f"{f_iso_year}-W{f_iso_week:02d}"
    filter_week_display = format_week_range(filter_date)

    branches = MfgBranch.objects.all().order_by('id')
    chart2_labels, chart2_data = [], []
    chart2_bg_colors = ['#0d6efd', '#ffc107', '#198754', '#dc3545', '#6f42c1', '#0dcaf0', '#fd7e14']

    for b in branches:
        chart2_labels.append(b.name)
        qty = ProductionOrder.objects.filter(cohort_week=target_cohort, branch=b).aggregate(Sum('quantity'))['quantity__sum'] or 0
        chart2_data.append(int(qty))

    return render(request, 'sales/sales_timeline.html', {
        'today': today_bkk, 'calc_deposit_date': calc_deposit_date, 'smart_eta_date': smart_eta_date,
        'filter_date': filter_date, 'filter_week_display': filter_week_display,
        'chart_labels_display_json': json.dumps(chart_labels_display), 'chart_week_starts_json': json.dumps(chart_week_starts),
        'chart_week_ends_json': json.dumps(chart_week_ends), 'chart1_ordered_json': json.dumps(chart1_ordered),
        'chart1_pending_json': json.dumps(chart1_pending), 'chart1_delivered_json': json.dumps(chart1_delivered),
        'chart2_labels_json': json.dumps(chart2_labels), 'chart2_data_json': json.dumps(chart2_data),
        'chart2_colors_json': json.dumps(chart2_bg_colors[:len(branches)]),
    })

# ==========================================
# 🎨 แดชบอร์ดแผนกกราฟิกและสื่อโฆษณา (Graphic Team)
# ==========================================
@login_required
def graphic_dashboard(request):
    user_groups = list(request.user.groups.values_list('name', flat=True))

    # 1. เช็กสิทธิ์ว่าเป็นระดับหัวหน้าหรือไม่
    is_supervisor = False
    if request.user.is_superuser or 'Executive' in user_groups or 'Manager_Team' in user_groups or 'Supervisor_Team' in user_groups:
        is_supervisor = True

    # 2. เลือกโหลดหน้าจอตามระดับสิทธิ์
    if is_supervisor:
        template_name = 'dashboards/graphic/supervisor.html'
    else:
        template_name = 'dashboards/graphic/staff.html'

    # ส่งตัวแปรไปให้หน้า HTML
    return render(request, template_name, {
        'is_supervisor': is_supervisor
        # หมายเหตุ: ข้อมูลคิวงานกราฟิกจะถูกเพิ่มเข้ามา หลังจากเราทำระบบ "ใบสั่งงานกราฟิก" ครับ
    })

# ==========================================
# 📐 แดชบอร์ดแผนกออกแบบและประเมินราคา (Blueprint Team)
# ==========================================
from manufacturing.models import ProductionOrder, BlueprintClaim

@login_required
def blueprint_dashboard(request):
    user_groups = list(request.user.groups.values_list('name', flat=True))
    current_emp = getattr(request.user, 'employee', None)

    # 1. เช็กสิทธิ์ว่าเป็นระดับหัวหน้าหรือไม่
    is_supervisor = False
    if request.user.is_superuser or 'Executive' in user_groups or 'Manager_Team' in user_groups or 'Supervisor_Team' in user_groups:
        is_supervisor = True

    # 2. ดึงข้อมูล "ตะกร้างานเข้า" (งานที่รอเขียนแบบ หรือกำลังดึง BOM)
    pending_jobs = ProductionOrder.objects.select_related(
        'product', 'salesperson', 'salesperson__branch'
    ).filter(
        status__in=['WAITING_BLUEPRINT', 'PLANNED'],
        is_closed=False
    ).order_by('start_date')

    # 3. ดึงข้อมูล "ประวัติการอนุมัติแบบ"
    history_jobs = ProductionOrder.objects.select_related(
        'product', 'salesperson', 'blueprint_approved_by', 'blueprint_claim'
    ).filter(blueprint_approved_at__isnull=False).order_by('-blueprint_approved_at')[:50]

    # 4. ดึงข้อมูล "งานที่พร้อมตั้งเบิกเงิน" (เฉพาะของพนักงานคนนั้น)
    claimable_jobs = ProductionOrder.objects.select_related(
        'salesperson', 'quotation_ref', 'quotation_ref__invoice'
    ).filter(
        blueprint_approved_by=current_emp,
        blueprint_claim__isnull=True,
        quotation_ref__invoice__isnull=False
    ).order_by('blueprint_approved_at')

    # 5. เลือกโหลดหน้าจอตามระดับสิทธิ์
    if is_supervisor:
        template_name = 'dashboards/blueprint/supervisor.html'
    else:
        template_name = 'dashboards/blueprint/staff.html'

    # ==========================================
    # 🌟 [NEW] คำนวณตัวเลขสำหรับ 4 กล่อง KPI
    # ==========================================
    kpi_waiting_blueprint = pending_jobs.filter(status='WAITING_BLUEPRINT').count()
    kpi_waiting_bom = pending_jobs.filter(status='PLANNED').count()
    kpi_claimable = claimable_jobs.count()
    kpi_history = history_jobs.count()

    # ส่งตัวแปรทั้งหมดไปให้หน้า HTML ใช้งาน
    return render(request, template_name, {
        'is_supervisor': is_supervisor,
        'pending_jobs': pending_jobs,
        'history_jobs': history_jobs,
        'claimable_jobs': claimable_jobs,
        'pending_count': pending_jobs.count(),
        'kpi_waiting_blueprint': kpi_waiting_blueprint,
        'kpi_waiting_bom': kpi_waiting_bom,
        'kpi_claimable': kpi_claimable,
        'kpi_history': kpi_history,
    })