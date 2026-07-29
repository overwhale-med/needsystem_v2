from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Count, Sum
from .models import SolarJob, SolarExpense, SubcontractorTeam
from .forms import SolarJobForm, SolarMaterialFormSet, SolarExpenseForm
from master_data.models import Customer
from solar_sales.models import SolarProduct

# ------------------------------------------
# 🛡️ ระบบเช็คสิทธิ์สำหรับแผนก Center / ปฏิบัติการ
# ------------------------------------------
def is_center_staff(user):
    if user.is_superuser: return True
    if hasattr(user, 'employee') and user.employee:
        dept = getattr(user.employee.department, 'name', '')
        if 'Center' in dept or 'Manager' in dept or 'บริหาร' in dept or 'ปฏิบัติการ' in dept:
            return True
    return False

@login_required
def center_dashboard(request):
    if not is_center_staff(request.user):
        messages.error(request, "❌ บัญชีของคุณไม่มีสิทธิ์เข้าถึงระบบ Center (Solar)")
        return redirect('dashboard')

    all_jobs = SolarJob.objects.all().order_by('-created_at')
    draft_jobs = all_jobs.filter(status='DRAFT').count()
    preparing_jobs = all_jobs.filter(status='PREPARING').count()
    in_progress_jobs = all_jobs.filter(status='IN_PROGRESS').count()
    pending_expenses = SolarExpense.objects.filter(status='PENDING').count()

    context = {
        'jobs': all_jobs[:20],
        'draft_jobs': draft_jobs,
        'preparing_jobs': preparing_jobs,
        'in_progress_jobs': in_progress_jobs,
        'pending_expenses': pending_expenses,
    }
    return render(request, 'solar_jobs/center_dashboard.html', context)

@login_required
def solar_job_create(request):
    if not is_center_staff(request.user): return redirect('solar_center_dashboard')

    if request.method == 'POST':
        customer_id = request.POST.get('customer_id')
        package_id = request.POST.get('package_id')
        customer = Customer.objects.filter(id=customer_id).first()
        package = SolarProduct.objects.filter(id=package_id).first()
        job = SolarJob.objects.create(customer=customer, package_sold=package, status='DRAFT')
        messages.success(request, f"✅ สร้างใบสั่งงาน {job.code} เรียบร้อยแล้ว ระบบกำลังพาไปหน้าจัดการงาน")
        return redirect('solar_job_manage', job_id=job.id)

    customers = Customer.objects.all()
    packages = SolarProduct.objects.filter(is_active=True, product_type='FG')
    return render(request, 'solar_jobs/job_create_modal.html', {'customers': customers, 'packages': packages})

@login_required
def solar_job_manage(request, job_id):
    if not is_center_staff(request.user): return redirect('solar_center_dashboard')

    job = get_object_or_404(SolarJob, id=job_id)

    if request.method == 'POST':
        form = SolarJobForm(request.POST, instance=job)
        formset = SolarMaterialFormSet(request.POST, instance=job)

        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            messages.success(request, f"✅ บันทึกข้อมูลการจัดทีมและเบิกวัตถุดิบของงาน {job.code} เรียบร้อยแล้ว")
            return redirect('solar_center_dashboard')
        else:
            messages.error(request, "❌ กรุณาตรวจสอบข้อมูลให้ครบถ้วน")
    else:
        form = SolarJobForm(instance=job)

        # 🌟 [FIXED] 1. เคลียร์ค่า 0.00 ออกถ้ายังไม่มีการระบุ เพื่อให้ช่องว่างเปล่า พิมพ์ง่าย
        if job.labor_cost_budget == 0:
            form.initial['labor_cost_budget'] = None

        # 🌟 [FIXED] 2. เปลี่ยนชนิดกล่องเป็น Text เพื่อซ่อนลูกศรขึ้น/ลง และบังคับโหมดคีย์บอร์ดตัวเลข
        form.fields['labor_cost_budget'].widget.input_type = 'text'
        form.fields['labor_cost_budget'].widget.attrs.update({
            'inputmode': 'decimal',
            'autocomplete': 'off',
            'placeholder': '0.00'
        })

        formset = SolarMaterialFormSet(instance=job)

    raw_materials = SolarProduct.objects.filter(is_active=True, product_type='RM')
    teams = SubcontractorTeam.objects.filter(is_active=True)

    return render(request, 'solar_jobs/job_manage.html', {
        'job': job,
        'form': form,
        'formset': formset,
        'raw_materials': raw_materials,
        'teams': teams
    })

# ------------------------------------------
# 🛠️ ฟังก์ชันจัดการทีมช่างรับเหมา
# ------------------------------------------
@login_required
def subcontractor_list(request):
    teams = SubcontractorTeam.objects.all().order_by('-is_active', 'name')
    return render(request, 'solar_jobs/subcontractor_list.html', {'teams': teams})

@login_required
def subcontractor_create(request):
    if request.method == 'POST':
        SubcontractorTeam.objects.create(
            name=request.POST.get('name'),
            leader_name=request.POST.get('leader_name'),
            phone=request.POST.get('phone'),
            note=request.POST.get('note'),
            is_active=request.POST.get('is_active') == 'on'
        )
        messages.success(request, "✅ บันทึกข้อมูลทีมช่างติดตั้งเรียบร้อยแล้ว")
        return redirect('subcontractor_list')
    return render(request, 'solar_jobs/subcontractor_form.html')

@login_required
def subcontractor_edit(request, pk):
    team = get_object_or_404(SubcontractorTeam, pk=pk)
    if request.method == 'POST':
        team.name = request.POST.get('name')
        team.leader_name = request.POST.get('leader_name')
        team.phone = request.POST.get('phone')
        team.note = request.POST.get('note')
        team.is_active = request.POST.get('is_active') == 'on'
        team.save()
        messages.success(request, "✅ อัปเดตข้อมูลทีมช่างติดตั้งเรียบร้อยแล้ว")
        return redirect('subcontractor_list')
    return render(request, 'solar_jobs/subcontractor_form.html', {'team': team})

# ------------------------------------------
# 🛡️ ระบบเช็คสิทธิ์สำหรับแผนกบัญชี
# ------------------------------------------
def is_accounting_staff(user):
    if user.is_superuser: return True
    if hasattr(user, 'employee') and user.employee:
        dept = getattr(user.employee.department, 'name', '')
        if 'บัญชี' in dept or 'Accounting' in dept: return True
    return False

# ------------------------------------------
# 💸 ระบบตั้งเบิกค่าใช้จ่าย (Expenses)
# ------------------------------------------
@login_required
def expense_list(request):
    expenses = SolarExpense.objects.all().order_by('-created_at')
    if not (is_accounting_staff(request.user) or is_center_staff(request.user)):
        expenses = expenses.filter(requester=getattr(request.user, 'employee', None))
    is_accounting = is_accounting_staff(request.user)
    return render(request, 'solar_jobs/expense_list.html', {'expenses': expenses, 'is_accounting': is_accounting})

@login_required
def expense_create(request):
    if request.method == 'POST':
        form = SolarExpenseForm(request.POST, request.FILES)
        if form.is_valid():
            exp = form.save(commit=False)
            exp.requester = getattr(request.user, 'employee', None)
            exp.save()
            messages.success(request, f"✅ ส่งเรื่องตั้งเบิกยอด {exp.amount:,.2f} บาท เรียบร้อยแล้ว (รอฝ่ายบัญชีตรวจสอบ)")
            return redirect('solar_expense_list')
        else:
            messages.error(request, "❌ กรุณาตรวจสอบข้อมูลให้ครบถ้วน")
    else:
        initial_job = request.GET.get('job_id')
        form = SolarExpenseForm(initial={'job': initial_job} if initial_job else None)
    return render(request, 'solar_jobs/expense_form.html', {'form': form})

@login_required
def expense_approve(request, expense_id):
    if not is_accounting_staff(request.user):
        messages.error(request, "❌ เฉพาะพนักงานฝ่ายบัญชีเท่านั้นที่สามารถอนุมัติการจ่ายเงินได้")
        return redirect('solar_expense_list')

    expense = get_object_or_404(SolarExpense, id=expense_id)
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'approve':
            expense.status = 'APPROVED'
            expense.approved_by = getattr(request.user, 'employee', None)
            messages.success(request, f"✅ อนุมัติการเบิกจ่ายยอด {expense.amount:,.2f} บาท เรียบร้อยแล้ว")
        elif action == 'reject':
            expense.status = 'REJECTED'
            messages.warning(request, f"⚠️ ปฏิเสธรายการตั้งเบิกของ {expense.requester.first_name if expense.requester else 'พนักงาน'}")
        expense.save()

    return redirect('solar_expense_list')