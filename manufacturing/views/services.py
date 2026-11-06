from decimal import Decimal
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from django.core.paginator import Paginator
from django.db import transaction

from manufacturing.models import ServiceTicket, ProductionTeam, ServiceTicketMedia, ServiceLaborClaim

# ==========================================
# 🌟 ฟังก์ชันตรวจสอบสิทธิ์ (สำหรับแผนกเซลส์และแอดมิน)
# ==========================================
def is_sales_authorized(user):
    if user.is_superuser: return True
    if hasattr(user, 'employee') and user.employee:
        dept = user.employee.department.name if user.employee.department else ''
        if 'ขาย' in dept or 'Sales' in dept: return True
    return False

# ==========================================
# 🌟 ประมวลผลและจัดการใบแจ้งซ่อม
# ==========================================
@login_required
def process_service_ticket(request, ticket_id):
    ticket = get_object_or_404(ServiceTicket, pk=ticket_id)

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'estimate_cost':
            cost_str = request.POST.get('estimated_cost', '0')
            if not cost_str: cost_str = '0'
            cost = cost_str.replace(',', '')
            comment = request.POST.get('cost_comment', '')

            ticket.estimated_cost = Decimal(cost)
            ticket.cost_comment = comment
            ticket.status = 'WAITING_APPROVAL'
            ticket.save()
            messages.warning(request, f"ส่งประเมินราคา ฿{ticket.estimated_cost:,.2f} ให้เซลส์เพื่อคอนเฟิร์มกับลูกค้าแล้ว")

        elif action == 'free_repair':
            ticket.estimated_cost = Decimal('0.00')
            ticket.cost_comment = "อนุโลมซ่อมฟรี (หัวหน้าช่างประเมินแล้วไม่มีค่าใช้จ่าย)"
            ticket.save()
            messages.success(request, f"🎁 ดำเนินการอนุโลมซ่อมฟรี! คุณสามารถจ่ายงานให้ทีมช่างเข้าพื้นที่ได้เลยครับ")

        elif action == 'assign_team':
            team_id = request.POST.get('production_team')
            apt_date = request.POST.get('appointment_date')
            if team_id:
                ticket.production_team_id = team_id
                if apt_date: ticket.appointment_date = parse_date(apt_date)
                ticket.status = 'IN_PROGRESS'
                ticket.save()
                messages.success(request, f"✅ จ่ายงานแจ้งซ่อม {ticket.code} ให้ทีมช่างเข้าพื้นที่เรียบร้อยแล้ว!")

        elif action == 'close_ticket':
            after_files = request.FILES.getlist('after_media_files')
            if after_files:
                for f in after_files:
                    ServiceTicketMedia.objects.create(ticket=ticket, media_type='AFTER', file=f)
                ticket.status = 'COMPLETED'
                ticket.completed_at = timezone.now()
                ticket.save()
                messages.success(request, f"🎉 ปิดจ๊อบงานซ่อม {ticket.code} และบันทึกรูปลง Media Hub สำเร็จ!")
            else:
                messages.error(request, "❌ กรุณาแนบรูปภาพ/วิดีโอหลังซ่อมเสร็จอย่างน้อย 1 ไฟล์เพื่อปิดงาน")

        elif action == 'archive_ticket':
            ticket.status = 'CLOSED'
            ticket.save()
            messages.success(request, f"📦 ปิดงานซ่อม {ticket.code} ถาวร! การ์ดถูกย้ายไปที่ตารางประวัติเรียบร้อยแล้วครับ")

    return redirect('service_board')

# ==========================================
# 🌟 ตารางประวัติแจ้งซ่อม
# ==========================================
@login_required
def service_history_list(request):
    if not is_sales_authorized(request.user):
        messages.error(request, "❌ บัญชีของคุณไม่มีสิทธิ์เข้าถึง")
        return redirect('dashboard')

    tickets = ServiceTicket.objects.select_related('production_order', 'salesperson', 'production_team').all().order_by('-created_at')
    search_q = request.GET.get('q', '')
    status_filter = request.GET.get('status', '')
    search_team = request.GET.get('team', '')
    start_date = request.GET.get('start_date', '')
    end_date = request.GET.get('end_date', '')

    if search_q: tickets = tickets.filter(Q(code__icontains=search_q) | Q(production_order__customer_name__icontains=search_q) | Q(production_order__code__icontains=search_q))
    if status_filter: tickets = tickets.filter(status=status_filter)
    if search_team: tickets = tickets.filter(production_order__production_team_id=search_team)
    if start_date: tickets = tickets.filter(created_at__date__gte=start_date)
    if end_date: tickets = tickets.filter(created_at__date__lte=end_date)

    paginator = Paginator(tickets, 20)
    page_obj = paginator.get_page(request.GET.get('page'))
    teams = ProductionTeam.objects.all().order_by('name')

    return render(request, 'manufacturing/service_history_list.html', {
        'page_obj': page_obj, 'search_q': search_q, 'status_filter': status_filter,
        'search_team': search_team, 'start_date': start_date, 'end_date': end_date,
        'status_choices': ServiceTicket.STATUS_CHOICES, 'teams': teams,
    })

# ==========================================
# 🌟 ส่งใบตั้งเบิกค่าแรงซ่อม
# ==========================================
@login_required
@transaction.atomic
def submit_service_labor_claim(request, ticket_id):
    if request.method == 'POST':
        ticket = get_object_or_404(ServiceTicket, pk=ticket_id)
        current_emp = getattr(request.user, 'employee', None)

        if ticket.labor_claims.exists():
            messages.error(request, f"❌ ตั๋วแจ้งซ่อม {ticket.code} ถูกตั้งเบิกค่าแรงไปแล้ว ไม่สามารถตั้งเบิกซ้ำได้")
            return redirect('service_history_list')

        try:
            amount_str = request.POST.get('claim_amount', '0').replace(',', '')
            amount = Decimal(amount_str)
            contractor_name = request.POST.get('technician_name', '')
            slip_file = request.FILES.get('claim_slip')

            if amount <= 0:
                messages.error(request, "❌ ยอดเงินเบิกต้องมากกว่า 0 บาท")
                return redirect('service_history_list')
            if not slip_file:
                messages.error(request, "❌ กรุณาแนบรูปบิล/หลักฐานหน้างาน")
                return redirect('service_history_list')

            ServiceLaborClaim.objects.create(
                service_ticket=ticket, requester=current_emp, technician_name=contractor_name,
                amount=amount, slip_image=slip_file, status='UNCLAIMED'
            )
            messages.success(request, f"🛒 หยอดบิลค่าแรงซ่อม {ticket.code} ลงตะกร้าเบิกส่วนตัวสำเร็จ!")
        except Exception as e:
            messages.error(request, f"❌ เกิดข้อผิดพลาด: {str(e)}")

    return redirect('service_history_list')