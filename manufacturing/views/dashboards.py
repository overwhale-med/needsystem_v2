import datetime
from decimal import Decimal
from django.utils import timezone
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Q

from manufacturing.models import (
    ProductionOrder, MfgBranch, ProductionTeam, Salesperson,
    ProductionStatus, DeliveryStatus, Transporter, LogisticsClaim,
    ServiceTicket
)

# ==========================================
# 🌟 [NEW] Control Dashboard (หอคอยควบคุม)
# ==========================================
@login_required
def control_dashboard(request):
    user_groups = list(request.user.groups.values_list('name', flat=True))
    is_manager = request.user.is_superuser or 'Manager_Team' in user_groups or 'Executive' in user_groups
    is_supervisor = 'Supervisor_Team' in user_groups

    if is_manager: template_name = 'dashboards/control/manager.html'
    elif is_supervisor: template_name = 'dashboards/control/supervisor.html'
    else: template_name = 'dashboards/control/staff.html'

    kpi1_planning = ProductionOrder.objects.filter(status__in=['NEW_JOB', 'WAITING_BLUEPRINT'], is_closed=False).count()
    kpi2_purchasing = ProductionOrder.objects.filter(status='WAITING_MATERIALS', is_materials_ordered=False, ppo_ref__isnull=True, is_closed=False).count()
    kpi3_inventory = ProductionOrder.objects.filter(status='WAITING_INVENTORY', is_closed=False).count()
    kpi4_logistics = ProductionOrder.objects.filter(Q(status='COMPLETED') | Q(status='WAITING_QC') | Q(is_onsite=True)).filter(transporter__isnull=True, is_closed=False).distinct().count()

    context = {
        'kpi1_planning': kpi1_planning, 'kpi2_purchasing': kpi2_purchasing,
        'kpi3_inventory': kpi3_inventory, 'kpi4_logistics': kpi4_logistics,
        'is_manager': is_manager, 'is_supervisor': is_supervisor,
    }
    return render(request, template_name, context)

# ==========================================
# 🌟 กระดานวางแผนการผลิต (Planner Board)
# ==========================================
@login_required
def planner_board(request):
    today = timezone.now().date()
    default_start = today - datetime.timedelta(days=30)
    default_end = today + datetime.timedelta(days=30)

    start_date = request.GET.get('start_date', default_start.strftime('%Y-%m-%d'))
    end_date = request.GET.get('end_date', default_end.strftime('%Y-%m-%d'))
    search_q = request.GET.get('q', '')
    search_branch = request.GET.get('branch', '')
    search_team = request.GET.get('team', '')
    search_salesperson = request.GET.get('salesperson', '')

    orders = ProductionOrder.objects.select_related(
        'product', 'branch', 'production_team', 'salesperson', 'salesperson__branch', 'quotation_ref', 'delivery_status'
    ).exclude(
        delivery_status__name__in=['ส่งมอบสำเร็จ', 'ลูกค้าเซ็นรับแล้ว', 'จัดส่งเรียบร้อย']
    ).order_by('-id')

    if start_date: orders = orders.filter(start_date__gte=start_date)
    if end_date: orders = orders.filter(start_date__lte=end_date)
    if search_q: orders = orders.filter(Q(code__icontains=search_q) | Q(customer_name__icontains=search_q) | Q(product__name__icontains=search_q))
    if search_branch: orders = orders.filter(branch_id=search_branch)
    if search_team: orders = orders.filter(production_team_id=search_team)
    if search_salesperson: orders = orders.filter(salesperson_id=search_salesperson)

    branches = MfgBranch.objects.all().order_by('name')
    teams = ProductionTeam.objects.all().order_by('name')
    salespersons = Salesperson.objects.select_related('branch').all().order_by('name')
    prod_statuses = ProductionStatus.objects.all().order_by('sequence', 'id')
    deliv_statuses = DeliveryStatus.objects.all().order_by('name')
    transporters = Transporter.objects.all().order_by('name')

    return render(request, 'manufacturing/planner_board.html', {
        'orders': orders, 'branches': branches, 'teams': teams, 'salespersons': salespersons,
        'prod_statuses': prod_statuses, 'deliv_statuses': deliv_statuses, 'transporters': transporters,
        'start_date': start_date, 'end_date': end_date, 'search_q': search_q,
        'search_branch': search_branch, 'search_team': search_team, 'search_salesperson': search_salesperson,
    })

# ==========================================
# 🌟 กระดานสำหรับหัวหน้าแผนกผลิต (ช่าง)
# ==========================================
@login_required
def production_head_board(request):
    today = timezone.now().date()
    default_start = today - datetime.timedelta(days=30)
    default_end = today + datetime.timedelta(days=30)

    current_monday = today - datetime.timedelta(days=today.weekday())
    current_sunday = current_monday + datetime.timedelta(days=6)
    next_monday = current_monday + datetime.timedelta(days=7)
    next_sunday = next_monday + datetime.timedelta(days=6)

    thai_year_curr = str(current_sunday.year + 543)[-2:]
    thai_year_next = str(next_sunday.year + 543)[-2:]

    if current_monday.month == current_sunday.month: str_current_week = f"{current_monday.day}-{current_sunday.day}/{current_monday.month}/{thai_year_curr}"
    else: str_current_week = f"{current_monday.day}/{current_monday.month}-{current_sunday.day}/{current_sunday.month}/{thai_year_curr}"

    if next_monday.month == next_sunday.month: str_next_week = f"{next_monday.day}-{next_sunday.day}/{next_monday.month}/{thai_year_next}"
    else: str_next_week = f"{next_monday.day}/{next_monday.month}-{next_sunday.day}/{next_sunday.month}/{thai_year_next}"

    start_date = request.GET.get('start_date', default_start.strftime('%Y-%m-%d'))
    end_date = request.GET.get('end_date', default_end.strftime('%Y-%m-%d'))
    search_q = request.GET.get('q', '')
    search_branch = request.GET.get('branch', '')
    search_team = request.GET.get('team', '')
    search_salesperson = request.GET.get('salesperson', '')

    orders = ProductionOrder.objects.select_related(
        'product', 'branch', 'production_team', 'salesperson', 'salesperson__branch', 'quotation_ref'
    ).prefetch_related('completed_departments', 'qc_logs').filter(
        status__in=['WAITING_MATERIALS', 'WAITING_INVENTORY', 'PLANNED', 'IN_PROGRESS', 'REWORK'], is_closed=False
    ).order_by('start_date', '-id')

    emp = getattr(request.user, 'employee', None)
    is_manager = False

    if request.user.is_superuser: is_manager = True
    elif emp:
        rank = emp.business_rank.lower() if emp.business_rank else ""
        job_title = emp.position.title.lower() if emp.position else ""
        if rank in ['manager', 'director'] or 'manager' in job_title: is_manager = True

    if not is_manager and emp and emp.production_team: orders = orders.filter(production_team=emp.production_team)

    if start_date: orders = orders.filter(start_date__gte=start_date)
    if end_date: orders = orders.filter(start_date__lte=end_date)
    if search_q: orders = orders.filter(Q(code__icontains=search_q) | Q(customer_name__icontains=search_q) | Q(product__name__icontains=search_q))
    if search_branch: orders = orders.filter(branch_id=search_branch)
    if search_team: orders = orders.filter(production_team_id=search_team)
    if search_salesperson: orders = orders.filter(salesperson_id=search_salesperson)

    def format_week_range(d):
        iso_y, iso_w, _ = d.isocalendar()
        monday = datetime.date.fromisocalendar(iso_y, iso_w, 1)
        sunday = monday + datetime.timedelta(days=6)
        y_str = str(sunday.year + 543)[-2:]
        if monday.month == sunday.month: return f"จ.{monday.day}-อา.{sunday.day}/{monday.month}/{y_str}"
        else: return f"จ.{monday.day}/{monday.month}-อา.{sunday.day}/{sunday.month}/{y_str}"

    col1_upcoming, col2_current, col3_overdue, col4_rework = [], [], [], []

    for order in orders:
        order.display_cohort = format_week_range(order.start_date)
        if order.status == 'REWORK': col4_rework.append(order)
        else:
            if order.start_date >= next_monday: col1_upcoming.append(order)
            elif order.start_date >= current_monday: col2_current.append(order)
            else: col3_overdue.append(order)

    branches = MfgBranch.objects.all().order_by('name')
    teams = ProductionTeam.objects.all().order_by('name')
    salespersons = Salesperson.objects.select_related('branch').all().order_by('name')
    prod_statuses = ProductionStatus.objects.all().order_by('sequence', 'id')

    return render(request, 'manufacturing/production_head_board.html', {
        'orders': orders, 'col1_upcoming': col1_upcoming, 'col2_current': col2_current,
        'col3_overdue': col3_overdue, 'col4_rework': col4_rework,
        'str_current_week': str_current_week, 'str_next_week': str_next_week,
        'branches': branches, 'teams': teams, 'salespersons': salespersons,
        'prod_statuses': prod_statuses, 'start_date': start_date, 'end_date': end_date,
        'search_q': search_q, 'search_branch': search_branch, 'search_team': search_team, 'search_salesperson': search_salesperson,
    })

# ==========================================
# 🌟 กระดานสำหรับหัวหน้าแผนก QC
# ==========================================
@login_required
def qc_board(request):
    today = timezone.now().date()
    default_start = today - datetime.timedelta(days=30)
    default_end = today + datetime.timedelta(days=30)

    current_monday = today - datetime.timedelta(days=today.weekday())
    current_sunday = current_monday + datetime.timedelta(days=6)
    thai_year_curr = str(current_sunday.year + 543)[-2:]

    if current_monday.month == current_sunday.month: str_current_week = f"{current_monday.day}-{current_sunday.day}/{current_monday.month}/{thai_year_curr}"
    else: str_current_week = f"{current_monday.day}/{current_monday.month}-{current_sunday.day}/{current_sunday.month}/{thai_year_curr}"

    start_date = request.GET.get('start_date', default_start.strftime('%Y-%m-%d'))
    end_date = request.GET.get('end_date', default_end.strftime('%Y-%m-%d'))
    search_q = request.GET.get('q', '')
    search_branch = request.GET.get('branch', '')
    search_team = request.GET.get('team', '')
    search_salesperson = request.GET.get('salesperson', '')

    orders = ProductionOrder.objects.select_related(
        'product', 'branch', 'production_team', 'salesperson', 'salesperson__branch', 'quotation_ref'
    ).prefetch_related('qc_logs').filter(
        status__in=['WAITING_QC', 'REWORK'], is_closed=False
    ).order_by('start_date', '-id')

    if start_date: orders = orders.filter(start_date__gte=start_date)
    if end_date: orders = orders.filter(start_date__lte=end_date)
    if search_q: orders = orders.filter(Q(code__icontains=search_q) | Q(customer_name__icontains=search_q) | Q(product__name__icontains=search_q))
    if search_branch: orders = orders.filter(branch_id=search_branch)
    if search_team: orders = orders.filter(production_team_id=search_team)
    if search_salesperson: orders = orders.filter(salesperson_id=search_salesperson)

    def format_week_range(d):
        iso_y, iso_w, _ = d.isocalendar()
        monday = datetime.date.fromisocalendar(iso_y, iso_w, 1)
        sunday = monday + datetime.timedelta(days=6)
        y_str = str(sunday.year + 543)[-2:]
        if monday.month == sunday.month: return f"จ.{monday.day}-อา.{sunday.day}/{monday.month}/{y_str}"
        else: return f"จ.{monday.day}/{monday.month}-อา.{sunday.day}/{sunday.month}/{y_str}"

    col1_current, col2_overdue, col3_rework = [], [], []

    for order in orders:
        order.display_cohort = format_week_range(order.start_date)
        if order.status == 'REWORK': col3_rework.append(order)
        elif order.status == 'WAITING_QC':
            if order.start_date < current_monday: col2_overdue.append(order)
            else: col1_current.append(order)

    branches = MfgBranch.objects.all().order_by('name')
    teams = ProductionTeam.objects.all().order_by('name')
    salespersons = Salesperson.objects.select_related('branch').all().order_by('name')

    return render(request, 'manufacturing/qc_board.html', {
        'orders': orders, 'col1_current': col1_current, 'col2_overdue': col2_overdue, 'col3_rework': col3_rework,
        'str_current_week': str_current_week, 'branches': branches, 'teams': teams, 'salespersons': salespersons,
        'start_date': start_date, 'end_date': end_date, 'search_q': search_q, 'search_branch': search_branch,
        'search_team': search_team, 'search_salesperson': search_salesperson,
    })

# ==========================================
# 🌟 กระดานแผนกจัดส่งสินค้า (Logistics Board)
# ==========================================
@login_required
def logistics_board(request):
    orders = ProductionOrder.objects.select_related(
        'product', 'branch', 'transporter', 'delivery_status', 'quotation_ref', 'logistics_claim'
    ).filter(
        Q(status='COMPLETED') | Q(status='WAITING_QC') | Q(is_onsite=True)
    ).order_by('delivery_date', '-id')

    col1_pending, col2_delivering, col3_delivered = [], [], []

    for order in orders:
        order.actual_balance = Decimal('0')
        if order.quotation_ref:
            inv = None
            if hasattr(order.quotation_ref, 'invoice_set'): inv = order.quotation_ref.invoice_set.first()
            elif hasattr(order.quotation_ref, 'invoice'): inv = order.quotation_ref.invoice

            if inv: order.actual_balance = getattr(inv, 'balance_amount', Decimal('0'))
            else:
                grand_total = getattr(order.quotation_ref, 'grand_total', Decimal('0'))
                deposit = getattr(order.quotation_ref, 'deposit_amount', Decimal('0'))
                order.actual_balance = getattr(order.quotation_ref, 'balance_due', grand_total - deposit)

        if order.transporter is None: col1_pending.append(order)
        elif order.delivery_status and order.delivery_status.name in ['ส่งมอบสำเร็จ', 'ลูกค้าเซ็นรับแล้ว', 'จัดส่งเรียบร้อย']:
            col3_delivered.append(order)
        else: col2_delivering.append(order)

    transporters = Transporter.objects.all().order_by('name')
    delivery_statuses = DeliveryStatus.objects.all().order_by('name')
    claims = LogisticsClaim.objects.all().order_by('-created_at')[:20]

    return render(request, 'manufacturing/logistics_board.html', {
        'orders': orders, 'col1_pending': col1_pending, 'col2_delivering': col2_delivering,
        'col3_delivered': col3_delivered, 'transporters': transporters,
        'delivery_statuses': delivery_statuses, 'claims': claims
    })

# ==========================================
# 🌟 กระดานคิวงานแจ้งซ่อม (Service Board)
# ==========================================
@login_required
def service_board(request):
    tickets = ServiceTicket.objects.select_related('production_order', 'salesperson', 'production_team').all().order_by('-created_at')

    col1_pending, col2_inprogress, col3_completed = [], [], []

    completed_count = 0
    for t in tickets:
        if t.status in ['PENDING', 'WAITING_APPROVAL']: col1_pending.append(t)
        elif t.status == 'IN_PROGRESS': col2_inprogress.append(t)
        elif t.status in ['COMPLETED', 'CANCELLED']:
            if completed_count < 30:
                col3_completed.append(t)
                completed_count += 1

    teams = ProductionTeam.objects.all().order_by('name')

    return render(request, 'manufacturing/service_board.html', {
        'col1_pending': col1_pending, 'col2_inprogress': col2_inprogress,
        'col3_completed': col3_completed, 'teams': teams
    })