from decimal import Decimal
from django.db.models import Q, F, Count, Sum
from hr.models import Employee
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import (
    SolarJob, SolarExpense, SubcontractorTeam, SolarJobBOM,
    SolarSurveyClaim, SolarInstallClaim, SolarAdvanceLaborClaim, SolarOtherExpense
)
from .forms import SolarJobForm, SolarBOMFormSet, SolarExpenseForm
from master_data.models import Customer
from solar_sales.models import SolarProduct, SolarQuotation, SolarInvoice, SolarCommissionTicket
from solar_inventory.models import SolarStandardBOM
from django.http import JsonResponse
import json
from django.core.paginator import Paginator
from django.utils import timezone
import datetime

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

    search_q = request.GET.get('q', '').strip()
    team_id = request.GET.get('team', '')
    sales_id = request.GET.get('salesperson', '')
    start_date = request.GET.get('start_date', '')
    end_date = request.GET.get('end_date', '')

    jobs = SolarJob.objects.select_related(
        'customer', 'package_sold', 'salesperson', 'quotation_ref', 'technician_team'
    ).annotate(
        pending_req_count=Count('job_boms', filter=Q(job_boms__planned_quantity__gt=F('job_boms__actual_used_quantity')), distinct=True),
        pending_ppo_count=Count('ppos', filter=Q(ppos__status='PENDING'), distinct=True)
    ).order_by('-created_at')

    if search_q:
        jobs = jobs.filter(Q(code__icontains=search_q) | Q(customer__name__icontains=search_q))
    if team_id:
        jobs = jobs.filter(technician_team_id=team_id)
    if sales_id:
        jobs = jobs.filter(salesperson_id=sales_id)
    if start_date and end_date:
        jobs = jobs.filter(created_at__date__gte=start_date, created_at__date__lte=end_date)

    draft_jobs = jobs.filter(status='DRAFT').count()
    preparing_jobs = jobs.filter(status__in=['PREPARING', 'WAITING_STORE', 'WAITING_PURCHASE']).count()
    in_progress_jobs = jobs.filter(status='IN_PROGRESS').count()

    pending_expenses = SolarExpense.objects.filter(status='PENDING').count()
    from solar_sales.models import SolarExpenseClaim
    approved_expenses = SolarExpenseClaim.objects.filter(status='APPROVED').order_by('created_at')

    teams = SubcontractorTeam.objects.filter(is_active=True)
    salespersons = Employee.objects.filter(department__name__icontains='ขาย') if hasattr(Employee, 'department') else Employee.objects.all()

    context = {
        'jobs': jobs[:50],
        'draft_jobs': draft_jobs,
        'preparing_jobs': preparing_jobs,
        'in_progress_jobs': in_progress_jobs,
        'pending_expenses': pending_expenses,
        'approved_expenses': approved_expenses,
        'teams': teams,
        'salespersons': salespersons,
        'search_q': search_q,
        'team_id': team_id,
        'sales_id': sales_id,
        'start_date': start_date,
        'end_date': end_date,
    }
    return render(request, 'solar_jobs/center_dashboard.html', context)

# ------------------------------------------
# 📊 กระดานควบคุมงานติดตั้ง (Overview Board)
# ------------------------------------------
@login_required
def solar_job_overview(request):
    if not is_center_staff(request.user):
        messages.error(request, "❌ บัญชีของคุณไม่มีสิทธิ์เข้าถึงระบบควบคุมงานติดตั้ง")
        return redirect('dashboard')

    search_q = request.GET.get('q', '').strip()
    team_id = request.GET.get('team', '')
    sales_id = request.GET.get('salesperson', '')
    status_filter = request.GET.get('status', '')
    start_date = request.GET.get('start_date', '')
    end_date = request.GET.get('end_date', '')
    tab = request.GET.get('tab', 'active')

    base_jobs = SolarJob.objects.select_related(
        'customer', 'package_sold', 'salesperson', 'quotation_ref', 'technician_team'
    ).prefetch_related('job_boms').annotate(
        pending_req_count=Count('job_boms', filter=Q(job_boms__planned_quantity__gt=F('job_boms__actual_used_quantity')), distinct=True),
        pending_ppo_count=Count('ppos', filter=Q(ppos__status='PENDING'), distinct=True)
    ).all()

    if search_q:
        base_jobs = base_jobs.filter(Q(code__icontains=search_q) | Q(customer__name__icontains=search_q))
    if team_id:
        base_jobs = base_jobs.filter(technician_team_id=team_id)
    if sales_id:
        base_jobs = base_jobs.filter(salesperson_id=sales_id)
    if status_filter:
        base_jobs = base_jobs.filter(status=status_filter)
    if start_date and end_date:
        base_jobs = base_jobs.filter(created_at__date__gte=start_date, created_at__date__lte=end_date)

    active_count = base_jobs.filter(status__in=['DRAFT', 'PREPARING', 'WAITING_STORE', 'WAITING_PURCHASE', 'IN_PROGRESS']).count()
    completed_count = base_jobs.filter(status__in=['COMPLETED', 'CLOSED', 'CANCELLED']).count()

    if tab == 'history':
        jobs = base_jobs.filter(status__in=['COMPLETED', 'CLOSED', 'CANCELLED']).order_by('-created_at')
    else:
        jobs = base_jobs.filter(status__in=['DRAFT', 'PREPARING', 'WAITING_STORE', 'WAITING_PURCHASE', 'IN_PROGRESS']).order_by('created_at')

    teams = SubcontractorTeam.objects.filter(is_active=True)
    salespersons = Employee.objects.filter(department__name__icontains='ขาย') if hasattr(Employee, 'department') else Employee.objects.all()

    context = {
        'jobs': jobs, 'tab': tab, 'active_count': active_count, 'completed_count': completed_count,
        'teams': teams, 'salespersons': salespersons, 'search_q': search_q, 'team_id': team_id,
        'sales_id': sales_id, 'status_filter': status_filter, 'start_date': start_date, 'end_date': end_date,
    }
    return render(request, 'solar_jobs/job_overview.html', context)

@login_required
def solar_job_create(request):
    if not is_center_staff(request.user): return redirect('solar_center_dashboard')
    if request.method == 'POST':
        customer_id = request.POST.get('customer_id')
        package_id = request.POST.get('package_id')
        customer = Customer.objects.filter(id=customer_id).first()
        package = SolarProduct.objects.filter(id=package_id).first()

        job = SolarJob.objects.create(customer=customer, package_sold=package, status='DRAFT')

        if package:
            standard_boms = SolarStandardBOM.objects.filter(package=package)
            for std_bom in standard_boms:
                SolarJobBOM.objects.create(
                    job=job, product=std_bom.raw_material, planned_quantity=std_bom.quantity,
                    actual_used_quantity=0, unit_cost=std_bom.raw_material.cost_price
                )
        messages.success(request, f"✅ สร้างใบสั่งงาน {job.code} พร้อมกางสูตรเบิกของ (BOM) อัตโนมัติเรียบร้อยแล้ว")
        return redirect('solar_job_manage', job_id=job.id)

    customers = Customer.objects.all()
    packages = SolarProduct.objects.filter(is_active=True, product_type='FG')
    return render(request, 'solar_jobs/job_create_modal.html', {'customers': customers, 'packages': packages})

@login_required
def solar_job_manage(request, job_id):
    if not is_center_staff(request.user): return redirect('solar_center_dashboard')
    job = get_object_or_404(SolarJob, id=job_id)

    if request.method == 'POST':
        mutable_post = request.POST.copy()
        if 'labor_cost_budget' in mutable_post:
            mutable_post['labor_cost_budget'] = mutable_post['labor_cost_budget'].replace(',', '')

        form = SolarJobForm(mutable_post, instance=job)
        formset = SolarBOMFormSet(request.POST, instance=job)

        if form.is_valid() and formset.is_valid():
            saved_job = form.save(commit=False)
            if saved_job.status == 'DRAFT' and saved_job.technician_team:
                saved_job.status = 'PREPARING'
                messages.success(request, "✨ ระบบปรับสถานะเป็น 'เตรียมของ/จัดทีม' อัตโนมัติ")

            saved_job.save()
            formset.save()

            if 'action_fetch_bom' in request.POST:
                if not saved_job.package_sold:
                    messages.error(request, "❌ ไม่สามารถดึงสูตรได้! งานนี้ยังไม่ได้ผูกกับแพ็กเกจหลัก")
                else:
                    standard_boms = SolarStandardBOM.objects.filter(package=saved_job.package_sold)
                    if not standard_boms.exists():
                        messages.warning(request, f"⚠️ ไม่พบสูตรมาตรฐานสำหรับแพ็กเกจ '{saved_job.package_sold.name}'")
                    else:
                        added_count = 0
                        for std_bom in standard_boms:
                            obj, created = SolarJobBOM.objects.get_or_create(
                                job=saved_job, product=std_bom.raw_material,
                                defaults={'planned_quantity': std_bom.quantity, 'actual_used_quantity': 0, 'unit_cost': std_bom.raw_material.cost_price}
                            )
                            if created: added_count += 1
                        if added_count > 0: messages.success(request, f"✅ ดึงสูตร BOM เพิ่ม {added_count} รายการ สำเร็จ!")
                        else: messages.info(request, "✅ บันทึกข้อมูลสำเร็จ! (วัตถุดิบมีครบแล้ว)")
                return redirect('solar_job_manage', job_id=saved_job.id)

            if saved_job.status == 'IN_PROGRESS':
                saved_job.has_unsent_requisition = saved_job.job_boms.filter(planned_quantity__gt=F('actual_used_quantity')).exists()
                saved_job.save()

            messages.success(request, f"✅ บันทึกข้อมูลงาน {job.code} เรียบร้อยแล้ว")
            return redirect('solar_job_manage', job_id=job.id)
        else:
            messages.error(request, "❌ กรุณาตรวจสอบข้อมูลให้ครบถ้วน")
    else:
        form = SolarJobForm(instance=job)
        if job.labor_cost_budget == 0 or job.labor_cost_budget is None:
            if job.quotation_ref and job.quotation_ref.subtotal:
                calculated_labor = job.quotation_ref.subtotal * Decimal('0.155')
                form.initial['labor_cost_budget'] = f"{calculated_labor:,.2f}"
            else:
                form.initial['labor_cost_budget'] = None
        else:
            form.initial['labor_cost_budget'] = f"{job.labor_cost_budget:,.2f}"

        form.fields['labor_cost_budget'].widget.input_type = 'text'
        form.fields['labor_cost_budget'].widget.attrs.update({'inputmode': 'decimal', 'autocomplete': 'off', 'placeholder': '0.00'})

        if job.status in ['WAITING_STORE', 'WAITING_PURCHASE']:
            incomplete_boms = job.job_boms.none()
        else:
            incomplete_boms = job.job_boms.filter(planned_quantity__gt=F('actual_used_quantity'))
        formset = SolarBOMFormSet(instance=job, queryset=incomplete_boms)

    raw_materials = SolarProduct.objects.filter(is_active=True, product_type='RM')
    teams = SubcontractorTeam.objects.filter(is_active=True)
    has_completed_boms = job.job_boms.filter(actual_used_quantity__gt=0).exists()
    rm_prices = {str(rm.id): float(rm.cost_price) for rm in raw_materials}

    return render(request, 'solar_jobs/job_manage.html', {
        'job': job, 'form': form, 'formset': formset, 'raw_materials': raw_materials,
        'teams': teams, 'has_completed_boms': has_completed_boms, 'rm_prices_json': json.dumps(rm_prices)
    })

@login_required
def solar_job_bom_history(request, job_id):
    if not is_center_staff(request.user): return redirect('solar_center_dashboard')
    job = get_object_or_404(SolarJob, id=job_id)
    completed_boms = job.job_boms.filter(actual_used_quantity__gt=0).order_by('id')
    grand_total_cost = sum(bom.total_cost for bom in completed_boms)
    return render(request, 'solar_jobs/job_bom_history.html', {'job': job, 'completed_boms': completed_boms, 'grand_total_cost': grand_total_cost})

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
            name=request.POST.get('name'), leader_name=request.POST.get('leader_name'),
            phone=request.POST.get('phone'), note=request.POST.get('note'), is_active=request.POST.get('is_active') == 'on'
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
            messages.success(request, f"✅ ส่งเรื่องตั้งเบิกยอด {exp.amount:,.2f} บาท เรียบร้อยแล้ว")
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

# ------------------------------------------
# 🔄 API สำหรับอัปเดตสถานะการ์ด (Drag & Drop) & Automation
# ------------------------------------------
@login_required
def update_job_status(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            job_id = data.get('job_id')
            new_status = str(data.get('new_status', '')).strip().upper()
            job = SolarJob.objects.get(id=job_id)
            job.status = new_status
            job.save()

            if new_status == 'COMPLETED':
                if job.quotation_ref_id:
                    SolarQuotation.objects.filter(id=job.quotation_ref_id).update(status='READY')
                elif job.note and "QT-SOL" in str(job.note):
                    for word in str(job.note).split():
                        if "QT-SOL" in word:
                            qt_code = word.strip().replace(',', '').replace(':', '')
                            SolarQuotation.objects.filter(code__icontains=qt_code).update(status='READY')
                            break

            return JsonResponse({'success': True, 'message': 'อัปเดตเรียบร้อย'})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    return JsonResponse({'success': False, 'error': 'Invalid request'})

@login_required
def center_pay_expense(request, expense_id):
    if not (is_center_staff(request.user) or is_accounting_staff(request.user)):
        messages.error(request, "❌ คุณไม่มีสิทธิ์ทำรายการนี้")
        return redirect('solar_center_dashboard')
    from solar_sales.models import SolarExpenseClaim
    expense = get_object_or_404(SolarExpenseClaim, id=expense_id)
    if request.method == 'POST':
        if 'transfer_slip' in request.FILES:
            expense.transfer_slip = request.FILES['transfer_slip']
            expense.status = 'PAID'
            expense.paid_at = timezone.now()
            expense.save()
            messages.success(request, f"✅ บันทึกการโอนเงินและแนบสลิปสำหรับ {expense.code} สำเร็จแล้ว!")
        else:
            messages.error(request, "❌ กรุณาแนบรูปสลิปโอนเงินด้วยครับ")
    return redirect('solar_center_dashboard')

# ------------------------------------------
# 🚀 ฟังก์ชัน Automation Center
# ------------------------------------------
@login_required
def center_submit_requisition(request, job_id):
    if not is_center_staff(request.user): return redirect('solar_center_dashboard')
    job = get_object_or_404(SolarJob, id=job_id)
    if job.status in ['DRAFT', 'PREPARING']:
        job.status = 'WAITING_STORE'
        job.has_unsent_requisition = False
        job.save()
        messages.success(request, f"✅ ส่งใบเบิกวัสดุสำหรับงาน {job.code} ไปยังสโตร์เรียบร้อยแล้ว")
    elif job.status == 'IN_PROGRESS':
        job.has_unsent_requisition = False
        job.save()
        messages.success(request, f"✅ ส่งใบขอเบิกวัสดุเพิ่มเติมให้สโตร์แล้ว")
    return redirect('solar_job_manage', job_id=job.id)

@login_required
def center_start_job(request, job_id):
    if not is_center_staff(request.user): return redirect('solar_center_dashboard')
    job = get_object_or_404(SolarJob, id=job_id)
    if job.status == 'WAITING_STORE':
        job.status = 'IN_PROGRESS'
        job.save()
        messages.success(request, f"🚀 เริ่มดำเนินการติดตั้งงาน {job.code} แล้ว!")
    return redirect('solar_job_manage', job_id=job.id)

@login_required
def center_complete_job(request, job_id):
    if not is_center_staff(request.user): return redirect('solar_center_dashboard')
    job = get_object_or_404(SolarJob, id=job_id)
    if job.status == 'IN_PROGRESS':
        job.status = 'COMPLETED'
        job.actual_finish_date = timezone.now().date()
        if job.package_sold:
            from solar_inventory.models import SolarStockMovement
            SolarStockMovement.objects.create(product=job.package_sold, movement_type='IN', quantity=Decimal('1'), reference_doc=job.code)
        job.save()

        if job.quotation_ref_id:
            SolarQuotation.objects.filter(id=job.quotation_ref_id).update(status='READY')
        elif job.note and "QT-SOL" in str(job.note):
            for word in str(job.note).split():
                if "QT-SOL" in word:
                    qt_code = word.strip().replace(',', '').replace(':', '')
                    SolarQuotation.objects.filter(code__icontains=qt_code).update(status='READY')
                    break
        messages.success(request, f"✅ ปิดจ๊อบงาน {job.code} เรียบร้อย! (แจ้งเตือนแผนกเซลส์อัตโนมัติแล้ว)")
    return redirect('solar_job_manage', job_id=job.id)

# ==========================================
# 🌟 [NEW] ฟังก์ชันสำหรับ Master Job Report - แผนกบัญชี (โซล่าเซลล์) 🌟
# ==========================================
@login_required
def solar_master_job_report(request):
    current_emp = getattr(request.user, 'employee', None)
    is_authorized = request.user.is_superuser
    if current_emp:
        rank = current_emp.business_rank.lower() if current_emp.business_rank else ""
        dept_name = getattr(current_emp.department, 'name', '')
        if rank in ['manager', 'director'] or 'บัญชี' in dept_name or 'Accounting' in dept_name:
            is_authorized = True

    if not is_authorized:
        messages.error(request, "❌ บัญชีของคุณไม่มีสิทธิ์เข้าถึงหน้านี้")
        return redirect('dashboard')

    jobs_query = SolarJob.objects.select_related('quotation_ref', 'customer').prefetch_related(
        'survey_claims', 'install_claims', 'advance_labor_claims', 'other_expenses',
    ).order_by('-id')

    search_query = request.GET.get('q', '')
    if search_query:
        jobs_query = jobs_query.filter(
            Q(code__icontains=search_query) |
            Q(quotation_ref__code__icontains=search_query) |
            Q(customer__name__icontains=search_query)
        ).distinct()

    paginator = Paginator(jobs_query, 20)
    page_obj = paginator.get_page(request.GET.get('page'))

    qt_ids = [job.quotation_ref_id for job in page_obj if job.quotation_ref_id]
    inv_dict = {}
    ticket_dict_2 = {}
    ticket_dict_13_5 = {}
    
    invoices = SolarInvoice.objects.filter(quotation_ref_id__in=qt_ids)
    inv_dict = {inv.quotation_ref_id: inv for inv in invoices}
    
    tickets = SolarCommissionTicket.objects.filter(
        Q(quotation_ref_id__in=qt_ids) | Q(invoice_ref__quotation_ref_id__in=qt_ids)
    )
    for t in tickets:
        if t.ticket_type == '2%' and getattr(t, 'quotation_ref_id', None):
            ticket_dict_2.setdefault(t.quotation_ref_id, []).append(t)
        elif t.ticket_type == '13.5%' and getattr(t.invoice_ref, 'quotation_ref_id', None):
            ticket_dict_13_5.setdefault(t.invoice_ref.quotation_ref_id, []).append(t)

    for job in page_obj:
        if job.quotation_ref_id:
            job.matched_invoice = inv_dict.get(job.quotation_ref_id)
            job.matched_tickets_2 = ticket_dict_2.get(job.quotation_ref_id, [])
            job.matched_tickets_13_5 = ticket_dict_13_5.get(job.quotation_ref_id, [])
        else:
            job.matched_invoice = None
            job.matched_tickets_2 = []
            job.matched_tickets_13_5 = []

    return render(request, 'solar_jobs/solar_master_job_report.html', {
        'page_obj': page_obj, 'search_query': search_query
    })