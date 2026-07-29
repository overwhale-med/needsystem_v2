from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.utils import timezone
from django.db.models import Count, Sum, Q
from datetime import datetime, date, timedelta
from django.contrib.auth.models import User, Group
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from .models import Employee, Attendance, LeaveRequest, Payslip, CommissionLog, Position, Department, SalesGroup
from .forms import LeaveRequestForm, EmployeeForm

# ==========================================
# 🛡️ ระบบจัดการสิทธิ์ (Permission Checks)
# ==========================================
def is_hr_or_admin(user):
    """เช็กว่าเป็น HR หรือ Admin หรือไม่"""
    if not user.is_authenticated:
        return False
    return user.is_superuser or user.groups.filter(name='HR_Team').exists()

def is_manager_or_hr_or_admin(user):
    """เช็กว่าเป็น ผู้จัดการ, HR หรือ Admin หรือไม่"""
    if not user.is_authenticated:
        return False
    return user.is_superuser or user.groups.filter(name__in=['Manager_Team', 'HR_Team']).exists()

# ==========================================
# 🟢 1. โซนพนักงานทั่วไป (Employee Zone)
# ==========================================
@login_required(login_url='/login/')
def employee_dashboard(request):
    try:
        employee = request.user.employee
    except AttributeError:
        return render(request, 'hr/error_no_profile.html')

    start_date_str = request.GET.get('start_date')
    end_date_str = request.GET.get('end_date')

    if not start_date_str or not end_date_str:
        today = date.today()
        start_date_str = today.replace(day=1).strftime('%Y-%m-%d')
        end_date_str = today.strftime('%Y-%m-%d')

    latest_payslip = Payslip.objects.filter(employee=employee, status='published').order_by('-year', '-month').first()
    today_attendance = Attendance.objects.filter(employee=employee, date=date.today()).first()
    leaves = LeaveRequest.objects.filter(employee=employee).order_by('-start_date')[:5]

    attendance_history = Attendance.objects.filter(
        employee=employee,
        date__range=[start_date_str, end_date_str]
    ).order_by('-date')

    # 🌟 คำนวณคอมมิชชันสะสมเดือนนี้แบบ Real-time
    current_month = timezone.now().month
    current_year = timezone.now().year
    total_commission = CommissionLog.objects.filter(
        recipient=employee,
        created_at__year=current_year,
        created_at__month=current_month
    ).aggregate(total=Sum('amount'))['total'] or 0

    # 🌟 ดึงยอดเงินกองทุนทีมของพนักงานคนนี้
    group_fund = 0
    if employee.sales_group:
        group_fund = employee.sales_group.fund_balance

    context = {
        'employee': employee,
        'payslip': latest_payslip,
        'leaves': leaves,
        'today_attendance': today_attendance,
        'attendance_history': attendance_history,
        'start_date': start_date_str,
        'end_date': end_date_str,
        'total_commission': total_commission,
        'group_fund': group_fund,
    }
    return render(request, 'hr/dashboard.html', context)

@login_required
def check_in(request):
    if request.method == 'POST':
        try:
            employee = request.user.employee
            today = date.today()

            # 🌟 [NEW] รับค่าพิกัด GPS จากหน้าบ้าน
            lat = request.POST.get('latitude')
            lng = request.POST.get('longitude')

            attendance, created = Attendance.objects.get_or_create(employee=employee, date=today)

            if not attendance.time_in:
                attendance.time_in = timezone.localtime(timezone.now()).time()

                # 🌟 [NEW] บันทึกพิกัดลงฐานข้อมูล
                if lat: attendance.latitude = lat
                if lng: attendance.longitude = lng

                attendance.save()

                msg = f'ลงเวลาเข้างานเรียบร้อย ({attendance.time_in.strftime("%H:%M")})'
                if lat and lng:
                    msg += ' พร้อมบันทึกพิกัด GPS สำเร็จ ✅'
                else:
                    msg += ' (ไม่พบข้อมูลพิกัด GPS)'

                messages.success(request, msg)
        except Exception as e:
            print(f"Error checking in: {e}")
            messages.error(request, "เกิดข้อผิดพลาดในการลงเวลา กรุณาลองใหม่อีกครั้ง")
    return redirect('employee_dashboard')

@login_required
def check_out(request):
    if request.method == 'POST':
        try:
            employee = request.user.employee
            today = date.today()
            attendance = Attendance.objects.filter(employee=employee, date=today).first()

            if attendance:
                attendance.time_out = timezone.localtime(timezone.now()).time()
                attendance.save()
                messages.success(request, f'ลงเวลาออกงานเรียบร้อย ({attendance.time_out.strftime("%H:%M")})')
        except Exception as e:
            print(f"Error checking out: {e}")
    return redirect('employee_dashboard')

@login_required
def leave_create(request):
    if request.method == 'POST':
        form = LeaveRequestForm(request.POST)
        if form.is_valid():
            leave_request = form.save(commit=False)
            leave_request.employee = request.user.employee
            leave_request.save()
            messages.success(request, 'ส่งใบลาเรียบร้อยแล้ว รอหัวหน้าอนุมัติครับ')
            return redirect('employee_dashboard')
    else:
        form = LeaveRequestForm()
    return render(request, 'hr/leave_form.html', {'form': form})

@login_required
def payslip_list(request):
    payslips = Payslip.objects.filter(employee=request.user.employee, status='published').order_by('-year', '-month')
    return render(request, 'hr/payslip_list.html', {'payslips': payslips})

@login_required
def payslip_detail(request, payslip_id):
    payslip = get_object_or_404(Payslip, id=payslip_id, employee=request.user.employee)
    return render(request, 'hr/payslip_detail.html', {'payslip': payslip})


# ==========================================
# 🟡 2. โซนหัวหน้างาน (Manager Zone)
# ==========================================
@user_passes_test(is_manager_or_hr_or_admin, login_url='/')
def manager_dashboard(request):
    pending_leaves = LeaveRequest.objects.filter(status='pending').order_by('start_date')
    history_leaves = LeaveRequest.objects.exclude(status='pending').order_by('-approved_date')[:5]
    context = {'pending_leaves': pending_leaves, 'history_leaves': history_leaves}
    return render(request, 'hr/manager_dashboard.html', context)

@user_passes_test(is_manager_or_hr_or_admin, login_url='/')
def approve_leave(request, leave_id):
    leave = get_object_or_404(LeaveRequest, id=leave_id)
    leave.status = 'approved'
    leave.approved_by = request.user
    leave.approved_date = timezone.now()
    leave.save()
    messages.success(request, f'อนุมัติใบลาของ {leave.employee.first_name} เรียบร้อยแล้ว')
    return redirect('manager_dashboard')

@user_passes_test(is_manager_or_hr_or_admin, login_url='/')
def reject_leave(request, leave_id):
    leave = get_object_or_404(LeaveRequest, id=leave_id)
    leave.status = 'rejected'
    leave.approved_by = request.user
    leave.approved_date = timezone.now()
    leave.save()
    messages.error(request, f'ไม่อนุมัติใบลาของ {leave.employee.first_name}')
    return redirect('manager_dashboard')


# ==========================================
# 🔴 3. โซนฝ่ายบุคคล/ผู้บริหาร (HR/Admin Zone)
# ==========================================
@user_passes_test(is_hr_or_admin, login_url='/')
def hr_executive_dashboard(request):
    today = date.today()
    total_employees = Employee.objects.count()
    present_count = Attendance.objects.filter(date=today, time_in__isnull=False).count()
    on_leave_today = LeaveRequest.objects.filter(start_date__lte=today, end_date__gte=today, status='approved').count()
    pending_leaves = LeaveRequest.objects.filter(status='pending').count()
    total_commission_paid = CommissionLog.objects.aggregate(Sum('amount'))['amount__sum'] or 0

    dept_data = Employee.objects.values('department__name').annotate(count=Count('id')).order_by('-count')
    new_hires = Employee.objects.order_by('-start_date')[:5]

    context = {
        'total_employees': total_employees, 'present_count': present_count,
        'on_leave_today': on_leave_today, 'pending_leaves': pending_leaves,
        'total_commission_paid': total_commission_paid, 'dept_data': dept_data,
        'new_hires': new_hires,
    }
    return render(request, 'hr/admin_dashboard.html', context)

@user_passes_test(is_hr_or_admin, login_url='/')
def employee_add(request):
    if request.method == 'POST':
        form = EmployeeForm(request.POST, request.FILES)
        if form.is_valid():
            emp = form.save(commit=False)

            # 🌟 แปลงปี ค.ศ. เป็น พ.ศ. (บวก 543) แล้วดึง 2 ตัวท้าย 🌟
            now = datetime.now()
            thai_year = str(now.year + 543)[-2:]
            prefix = f"EMP-{thai_year}{now.strftime('%m')}"

            last_emp = Employee.objects.filter(emp_id__startswith=prefix).order_by('emp_id').last()
            if last_emp:
                try: seq = int(last_emp.emp_id.split('-')[-1]) + 1
                except ValueError: seq = 1
            else:
                seq = 1

            emp.emp_id = f"{prefix}-{seq:03d}"

            create_user = form.cleaned_data.get('create_user_account')
            if create_user:
                username = form.cleaned_data.get('username')
                password = form.cleaned_data.get('password')
                email = form.cleaned_data.get('email')

                if username and password:
                    if User.objects.filter(username=username).exists():
                        messages.error(request, f"Username '{username}' มีผู้ใช้งานแล้ว กรุณาเปลี่ยนใหม่")
                        return render(request, 'hr/employee_add.html', {'form': form})
                    user = User.objects.create_user(username=username, password=password, email=email)
                    emp.user = user

            emp.save()
            messages.success(request, f"✅ ลงทะเบียนพนักงาน {emp.first_name} เรียบร้อยแล้ว (รหัส: {emp.emp_id})")
            return redirect('hr_executive_dashboard')
    else:
        form = EmployeeForm()
    return render(request, 'hr/employee_add.html', {'form': form})

# ==========================================
# ✏️ ฟังก์ชันสำหรับแก้ไขข้อมูลพนักงาน (Edit)
# ==========================================
@user_passes_test(is_hr_or_admin, login_url='/')
def employee_edit(request, emp_id):
    employee = get_object_or_404(Employee, emp_id=emp_id)

    if request.method == 'POST':
        form = EmployeeForm(request.POST, request.FILES, instance=employee)
        if form.is_valid():
            emp = form.save(commit=False)

            create_user = form.cleaned_data.get('create_user_account')
            if create_user and not emp.user:
                username = form.cleaned_data.get('username')
                password = form.cleaned_data.get('password')
                email = form.cleaned_data.get('email')

                if username and password:
                    if User.objects.filter(username=username).exists():
                        messages.error(request, f"Username '{username}' มีผู้ใช้งานแล้ว กรุณาเปลี่ยนใหม่")
                        return render(request, 'hr/employee_edit.html', {'form': form, 'employee': employee})
                    user = User.objects.create_user(username=username, password=password, email=email)
                    emp.user = user

            emp.save()
            messages.success(request, f"✅ บันทึกการแก้ไขข้อมูลของ {emp.first_name} เรียบร้อยแล้ว")
            return redirect('role_management')
    else:
        form = EmployeeForm(instance=employee)

    return render(request, 'hr/employee_edit.html', {'form': form, 'employee': employee})

# เลื่อนหาฟังก์ชัน network_tree เดิม แล้ววางทับด้วยโค้ดชุดนี้นะคะ
@user_passes_test(is_hr_or_admin, login_url='/')
def network_tree(request):
    # 🌟 [NEW] ศูนย์บัญชาการผลตอบแทน (Compensation Command Center) 🌟
    from sales.models import POSOrder, Invoice  # นำเข้าเพื่อใช้วิเคราะห์ยอดขายรอจ่าย

    groups = SalesGroup.objects.all().order_by('id')
    now = timezone.now()

    groups_data = []
    for group in groups:
        members = group.members.all().order_by('group_role', 'first_name')
        members_data = []

        # นับจำนวนลูกทีมแต่ละระดับเพื่อหารแบ่ง % (ป้องกันการหาร 0)
        l1_count = members.filter(group_role='LEVEL1').count() or 1
        l2_count = members.filter(group_role='LEVEL2').count() or 1

        for emp in members:
            # 1. ยอดรับไปแล้วทั้งหมด (ดึงประวัติการโอนคอมมิชชันสำเร็จ)
            total_comm = CommissionLog.objects.filter(recipient=emp).aggregate(Sum('amount'))['amount__sum'] or 0

            # 2. ยอดรอจ่ายเดือนนี้ (ประเมินจากบิลเดือนปัจจุบัน ที่สถานะยังไม่ PAID)
            unpaid_pos = POSOrder.objects.filter(
                employee=emp, status__in=['PENDING', 'UNPAID'],
                created_at__year=now.year, created_at__month=now.month
            ).aggregate(Sum('total_amount'))['total_amount__sum'] or 0

            unpaid_inv = Invoice.objects.filter(
                employee=emp, status__in=['PENDING', 'UNPAID'],
                date__year=now.year, date__month=now.month
            ).aggregate(Sum('grand_total'))['grand_total__sum'] or 0

            pending_sales = float(unpaid_pos) + float(unpaid_inv)

            pending_comm = 0
            if pending_sales > 0:
                group_comm = pending_sales * float(group.commission_rate) / 100
                if group.group_type == 'TEAM':
                    if emp.group_role == 'LEADER':
                        pending_comm = group_comm * float(group.share_leader) / 100
                    elif emp.group_role == 'LEVEL1':
                        pending_comm = (group_comm * float(group.share_level1) / 100) / l1_count
                    elif emp.group_role == 'LEVEL2':
                        pending_comm = (group_comm * float(group.share_level2) / 100) / l2_count
                elif group.group_type == 'INDEPENDENT':
                    fund_share = group_comm * float(group.share_fund) / 100
                    pending_comm = group_comm - fund_share

            members_data.append({
                'emp': emp,
                'total_comm': total_comm,
                'pending_comm': pending_comm
            })

        groups_data.append({
            'group': group,
            'members_data': members_data
        })

    unassigned_employees = Employee.objects.filter(sales_group__isnull=True).order_by('-start_date')

    context = {
        'groups_data': groups_data,
        'unassigned_employees': unassigned_employees
    }
    return render(request, 'hr/network_tree.html', context)


# ==========================================
# 🚀 API เสริมสำหรับ Quick Add (+) และ Generate
# ==========================================
@user_passes_test(is_hr_or_admin, login_url='/')
@require_POST
def api_create_position(request):
    title = request.POST.get('title')
    if title:
        position, created = Position.objects.get_or_create(title=title)
        return JsonResponse({'status': 'success', 'id': position.id, 'title': position.title})
    return JsonResponse({'status': 'error', 'message': 'Missing title'}, status=400)

@user_passes_test(is_hr_or_admin, login_url='/')
@require_POST
def api_create_department(request):
    name = request.POST.get('name')
    if name:
        dept, created = Department.objects.get_or_create(name=name)
        return JsonResponse({'status': 'success', 'id': dept.id, 'name': dept.name})
    return JsonResponse({'status': 'error', 'message': 'Missing name'}, status=400)

@user_passes_test(is_hr_or_admin, login_url='/')
@require_POST
def api_generate_emp_id(request):
    """API สำหรับสร้างรหัสพนักงานล่วงหน้า (กดปุ่มแล้วเด้งมาโชว์)"""
    # 🌟 แปลงปี ค.ศ. เป็น พ.ศ. (บวก 543) แล้วดึง 2 ตัวท้าย 🌟
    now = datetime.now()
    thai_year = str(now.year + 543)[-2:]
    prefix = f"EMP-{thai_year}{now.strftime('%m')}"

    last_emp = Employee.objects.filter(emp_id__startswith=prefix).order_by('emp_id').last()

    if last_emp:
        try: seq = int(last_emp.emp_id.split('-')[-1]) + 1
        except ValueError: seq = 1
    else:
        seq = 1

    new_id = f"{prefix}-{seq:03d}"
    return JsonResponse({'status': 'success', 'emp_id': new_id})


# ==========================================
# 🔐 4. โซนจัดการสิทธิ์ (Role Management & Profiles)
# ==========================================
@user_passes_test(is_hr_or_admin, login_url='/')
def role_management(request):
    employees = Employee.objects.select_related('user').prefetch_related('user__groups').order_by('emp_id')
    all_groups = Group.objects.all().order_by('name')

    context = {
        'employees': employees,
        'all_groups': all_groups,
    }
    return render(request, 'hr/role_management.html', context)

@user_passes_test(is_hr_or_admin, login_url='/')
def employee_access_profile(request, emp_id):
    employee = get_object_or_404(Employee, emp_id=emp_id)
    all_groups = Group.objects.all().order_by('name')

    user_groups = []
    if employee.user:
        user_groups = list(employee.user.groups.values_list('id', flat=True))

    # 🌟 [NEW] ดึงข้อมูลทีม และ ตัวเลือกตำแหน่ง ส่งไปให้หน้า HTML 🌟
    sales_groups = SalesGroup.objects.all().order_by('name')
    roles = Employee.ROLE_CHOICES

    context = {
        'employee': employee,
        'all_groups': all_groups,
        'user_groups': user_groups,
        'sales_groups': sales_groups, # 🌟 เพิ่มตรงนี้
        'roles': roles,               # 🌟 เพิ่มตรงนี้
    }
    return render(request, 'hr/employee_access_profile.html', context)

@user_passes_test(is_hr_or_admin, login_url='/')
@require_POST
def api_update_user_role(request):
    try:
        user_id = request.POST.get('user_id')
        group_id = request.POST.get('group_id')

        target_user = get_object_or_404(User, id=user_id)
        target_user.groups.clear()

        if group_id:
            target_group = get_object_or_404(Group, id=group_id)
            target_user.groups.add(target_group)
            role_name = target_group.name
        else:
            role_name = "พนักงานทั่วไป (Employee)"

        return JsonResponse({'status': 'success', 'message': f'อัปเดตสิทธิ์เป็น {role_name} เรียบร้อย'})

    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

@user_passes_test(is_hr_or_admin, login_url='/')
@require_POST
def api_create_group(request):
    name = request.POST.get('name')
    if name:
        group, created = Group.objects.get_or_create(name=name)
        return JsonResponse({'status': 'success', 'id': group.id, 'name': group.name})
    return JsonResponse({'status': 'error', 'message': 'Missing name'}, status=400)

@user_passes_test(is_hr_or_admin, login_url='/')
@require_POST
def api_reset_password(request):
    user_id = request.POST.get('user_id')
    new_password = request.POST.get('new_password')
    try:
        user = get_object_or_404(User, id=user_id)
        user.set_password(new_password)
        user.save()
        return JsonResponse({'status': 'success', 'message': 'เปลี่ยนรหัสผ่านเรียบร้อยแล้ว'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

@user_passes_test(is_hr_or_admin, login_url='/')
@require_POST
def api_toggle_user_group(request):
    user_id = request.POST.get('user_id')
    group_id = request.POST.get('group_id')
    action = request.POST.get('action')

    try:
        user = get_object_or_404(User, id=user_id)
        group = get_object_or_404(Group, id=group_id)

        if action == 'add':
            user.groups.add(group)
        elif action == 'remove':
            user.groups.remove(group)

        return JsonResponse({'status': 'success'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

# ==========================================
# 🌟 ระบบตั้งค่ากลุ่มและกองทุน (Sales Group Settings)
# ==========================================
@user_passes_test(is_hr_or_admin, login_url='/')
def sales_group_settings(request):
    groups = SalesGroup.objects.all().order_by('id')

    if request.method == 'POST':
        action = request.POST.get('action')

        if action in ['add', 'edit']:
            group_id = request.POST.get('group_id')
            name = request.POST.get('name')
            group_type = request.POST.get('group_type')
            commission_rate = request.POST.get('commission_rate') or 0
            flat_rate_amount = request.POST.get('flat_rate_amount') or 0 # 🌟 รับค่าเหมาจ่าย

            share_leader = request.POST.get('share_leader') or 0
            share_level1 = request.POST.get('share_level1') or 0
            share_level2 = request.POST.get('share_level2') or 0

            share_exec1 = request.POST.get('share_exec1') or 0
            share_exec2 = request.POST.get('share_exec2') or 0
            share_exec3 = request.POST.get('share_exec3') or 0
            share_exec4 = request.POST.get('share_exec4') or 0
            share_exec5 = request.POST.get('share_exec5') or 0

            share_fund = request.POST.get('share_fund') or 0

            if action == 'add':
                SalesGroup.objects.create(
                    name=name, group_type=group_type, commission_rate=commission_rate,
                    flat_rate_amount=flat_rate_amount, # 🌟 บันทึก
                    share_leader=share_leader, share_level1=share_level1, share_level2=share_level2,
                    share_exec1=share_exec1, share_exec2=share_exec2, share_exec3=share_exec3,
                    share_exec4=share_exec4, share_exec5=share_exec5, share_fund=share_fund
                )
                messages.success(request, f"✅ เพิ่มกลุ่ม {name} เรียบร้อยแล้ว")

            elif action == 'edit' and group_id:
                group = get_object_or_404(SalesGroup, id=group_id)
                group.name = name
                group.group_type = group_type
                group.commission_rate = commission_rate
                group.flat_rate_amount = flat_rate_amount # 🌟 บันทึก
                group.share_leader = share_leader
                group.share_level1 = share_level1
                group.share_level2 = share_level2
                group.share_exec1 = share_exec1
                group.share_exec2 = share_exec2
                group.share_exec3 = share_exec3
                group.share_exec4 = share_exec4
                group.share_exec5 = share_exec5
                group.share_fund = share_fund
                group.save()
                messages.success(request, f"✅ อัปเดตข้อมูลกลุ่ม {name} เรียบร้อยแล้ว")

        elif action == 'delete':
            group_id = request.POST.get('group_id')
            group = get_object_or_404(SalesGroup, id=group_id)
            if group.members.exists():
                messages.error(request, f"❌ ไม่สามารถลบกลุ่ม {group.name} ได้ เนื่องจากยังมีพนักงานสังกัดอยู่ในกลุ่มนี้")
            else:
                group_name = group.name
                group.delete()
                messages.success(request, f"🗑️ ลบกลุ่ม {group_name} เรียบร้อยแล้ว")

        return redirect('sales_group_settings')
    return render(request, 'hr/sales_group_settings.html', {'groups': groups})

# ==========================================
# 🌟 ระบบทำเนียบพนักงาน (Employee Directory)
# ==========================================
@user_passes_test(is_hr_or_admin, login_url='/')
def employee_directory(request):
    departments = Department.objects.all().order_by('name')
    sales_groups = SalesGroup.objects.all().order_by('name')

    dept_id = request.GET.get('dept')
    search_q = request.GET.get('q', '').strip()

    employees = Employee.objects.all().order_by('-start_date')

    # 🔍 ระบบกรองข้อมูล
    if dept_id:
        employees = employees.filter(department_id=dept_id)
    if search_q:
        employees = employees.filter(
            Q(first_name__icontains=search_q) |
            Q(last_name__icontains=search_q) |
            Q(emp_id__icontains=search_q)
        )

    context = {
        'employees': employees,
        'departments': departments,
        'sales_groups': sales_groups,
        'selected_dept': int(dept_id) if dept_id else '',
        'search_q': search_q,
    }
    return render(request, 'hr/employee_directory.html', context)

@user_passes_test(is_hr_or_admin, login_url='/')
@require_POST
def api_update_sales_role(request):
    """API สำหรับอัปเดตทีมขายและบทบาทผ่านหน้าตาราง (AJAX)"""
    emp_id = request.POST.get('emp_id')
    group_id = request.POST.get('group_id')
    role = request.POST.get('role')

    try:
        employee = get_object_or_404(Employee, emp_id=emp_id)
        if group_id:
            employee.sales_group_id = group_id
        else:
            employee.sales_group = None

        if role:
            employee.group_role = role

        employee.save()
        return JsonResponse({'status': 'success', 'message': f'อัปเดตทีมของ {employee.first_name} เรียบร้อยแล้ว'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

# ==========================================
# 🌟 ระบบตรวจสอบเวลาเข้างานและพิกัด GPS
# ==========================================
@user_passes_test(is_hr_or_admin, login_url='/')
def attendance_map(request):
    today = timezone.now().date()
    date_filter = request.GET.get('date', today.strftime('%Y-%m-%d'))
    search_q = request.GET.get('q', '').strip()

    # ดึงข้อมูลการเข้างานตามวันที่เลือก
    attendances = Attendance.objects.filter(date=date_filter).select_related('employee', 'employee__department').order_by('-time_in')

    if search_q:
        attendances = attendances.filter(
            Q(employee__first_name__icontains=search_q) |
            Q(employee__last_name__icontains=search_q) |
            Q(employee__emp_id__icontains=search_q)
        )

    context = {
        'attendances': attendances,
        'date_filter': date_filter,
        'search_q': search_q,
    }
    return render(request, 'hr/attendance_map.html', context)

@user_passes_test(is_hr_or_admin, login_url='/')
def org_chart_tree(request):
    """สมองกลสำหรับหน้าแผนผังองค์กร (Tree View)"""
    root_employees = Employee.objects.filter(introducer__isnull=True).order_by('id')
    return render(request, 'hr/org_chart_tree.html', {'root_employees': root_employees})

@user_passes_test(is_hr_or_admin, login_url='/')
@require_POST
def api_assign_to_team(request):
    """สมองกลสำหรับย้ายพนักงานเข้าทีม ปลดออกจากทีม และกำหนดตำแหน่ง"""
    emp_id = request.POST.get('emp_id')
    group_id = request.POST.get('group_id')
    role = request.POST.get('role')

    try:
        employee = get_object_or_404(Employee, emp_id=emp_id)

        if group_id:
            # 🌟 กรณีมี group_id แปลว่า ย้ายเข้าทีม
            employee.sales_group_id = group_id
            if role:
                employee.group_role = role
            msg = f"✅ ย้ายคุณ {employee.first_name} เข้าทีมเรียบร้อยแล้วค่ะ"
        else:
            # 🌟 กรณีไม่มี group_id แปลว่า ปลดออกจากทีม กลับไปรอจัดสรร
            employee.sales_group = None
            employee.group_role = 'MEMBER'
            msg = f"🔄 นำคุณ {employee.first_name} กลับไปรอจัดสรรทีมเรียบร้อยแล้วค่ะ"

        employee.save()
        return JsonResponse({'status': 'success', 'message': msg})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)