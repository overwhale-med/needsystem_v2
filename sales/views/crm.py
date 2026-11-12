import pytz
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from django.core.paginator import Paginator
from django.utils import timezone

# Models
from sales.models import CustomerLead, Appointment
from hr.models import Employee

# Services
from sales.services import is_sales_authorized, get_target_employees, get_sales_queryset

@login_required
def crm_board(request):
    if not is_sales_authorized(request.user):
        messages.error(request, "❌ บัญชีของคุณไม่มีสิทธิ์เข้าถึงระบบ CRM")
        return redirect('dashboard')

    target_employees, scope_title = get_target_employees(request.user)
    leads = get_sales_queryset(CustomerLead, request.user, target_employees)\
        .select_related('employee', 'employee__department')\
        .order_by('-created_at')

    all_emps_in_scope = target_employees.filter(
        Q(department__name__icontains='ขาย') |
        Q(department__name__icontains='Sales') |
        Q(department__name__icontains='Marketing')
    ).order_by('first_name')

    search_q = request.GET.get('q', '')
    status_f = request.GET.get('status', '')
    channel_f = request.GET.get('channel', '')
    start_date = request.GET.get('start_date', '')
    end_date = request.GET.get('end_date', '')
    emp_f = request.GET.get('employee', '')

    if search_q: leads = leads.filter(Q(code__icontains=search_q) | Q(customer_name__icontains=search_q) | Q(phone__icontains=search_q))
    if status_f: leads = leads.filter(status=status_f)
    if channel_f: leads = leads.filter(channel=channel_f)
    if start_date: leads = leads.filter(date__date__gte=start_date)
    if end_date: leads = leads.filter(date__date__lte=end_date)
    if emp_f: leads = leads.filter(employee_id=emp_f)

    paginator = Paginator(leads, 20)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'sales/crm_board.html', {
        'leads': page_obj, 'search_q': search_q, 'status_f': status_f,
        'channel_f': channel_f, 'start_date': start_date, 'end_date': end_date,
        'emp_f': emp_f, 'scope_title': scope_title,
        'status_choices': CustomerLead.STATUS_CHOICES, 'channel_choices': CustomerLead.CHANNEL_CHOICES,
        'employees': all_emps_in_scope
    })

@login_required
def crm_lead_create(request):
    if request.method == 'POST':
        name = request.POST.get('customer_name')
        phone = request.POST.get('phone', '')
        channel = request.POST.get('channel', 'LINE')
        requirements = request.POST.get('requirements', '')

        tz_bkk = pytz.timezone('Asia/Bangkok')
        now_bkk = timezone.now().astimezone(tz_bkk)
        thai_year = (now_bkk.year + 543) % 100
        prefix = f"LD-{thai_year:02d}{now_bkk.strftime('%m')}"
        last = CustomerLead.objects.filter(code__startswith=prefix).order_by('code').last()
        seq = int(last.code.split('-')[-1]) + 1 if last else 1
        new_code = f"{prefix}-{seq:04d}"

        CustomerLead.objects.create(
            code=new_code, customer_name=name, phone=phone, channel=channel,
            requirements=requirements, employee=getattr(request.user, 'employee', None)
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
        lead.date = timezone.now()
        lead.save()
        messages.success(request, f"✅ อัปเดตสถานะข้อมูลลูกค้า {lead.code} เรียบร้อยแล้ว!")
    return redirect('crm_board')

@login_required
def appointment_board(request):
    if not is_sales_authorized(request.user):
        messages.error(request, "❌ บัญชีของคุณไม่มีสิทธิ์เข้าถึงระบบนัดหมาย")
        return redirect('dashboard')

    target_employees, _ = get_target_employees(request.user)
    appointments = get_sales_queryset(Appointment, request.user, target_employees).select_related('employee', 'employee__department', 'lead').order_by('-appointment_date')

    search_q = request.GET.get('q', '')
    type_f = request.GET.get('type', '')
    status_f = request.GET.get('status', '')
    start_date = request.GET.get('start_date', '')
    end_date = request.GET.get('end_date', '')

    if search_q: appointments = appointments.filter(Q(lead__customer_name__icontains=search_q) | Q(lead__code__icontains=search_q) | Q(details__icontains=search_q) | Q(employee__first_name__icontains=search_q))
    if type_f: appointments = appointments.filter(appointment_type=type_f)
    if status_f: appointments = appointments.filter(status=status_f)
    if start_date: appointments = appointments.filter(appointment_date__date__gte=start_date)
    if end_date: appointments = appointments.filter(appointment_date__date__lte=end_date)

    paginator = Paginator(appointments, 20)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'sales/appointment_board.html', {
        'appointments': page_obj, 'search_q': search_q, 'type_f': type_f,
        'status_f': status_f, 'start_date': start_date, 'end_date': end_date,
        'type_choices': Appointment.TYPE_CHOICES, 'status_choices': Appointment.STATUS_CHOICES,
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
                lead=lead_to_book, appointment_date=apt_date_str, appointment_type=apt_type,
                details=details, employee=getattr(request.user, 'employee', None)
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
        if apt_date_str: apt.appointment_date = apt_date_str
        apt.save()
        messages.success(request, "✅ อัปเดตข้อมูลการนัดหมายเรียบร้อยแล้ว!")
    return redirect('appointment_board_global')