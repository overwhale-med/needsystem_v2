from django.db.models import Q
from hr.models import Employee # ใช้สำหรับดึงรายชื่อเซลส์มาลงในตัวกรอง
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Count, Sum
from .models import SolarJob, SolarExpense, SubcontractorTeam, SolarJobBOM # 🌟 เพิ่ม SolarJobBOM
from .forms import SolarJobForm, SolarBOMFormSet, SolarExpenseForm
from master_data.models import Customer
from solar_sales.models import SolarProduct, SolarQuotation
from solar_inventory.models import SolarStandardBOM # 🌟 ดึงโมเดลสูตรมาตรฐานมาจากคลังสินค้า
from django.http import JsonResponse
import json

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

    # 🌟 1. รับค่าจากฟอร์มค้นหา
    search_q = request.GET.get('q', '').strip()
    team_id = request.GET.get('team', '')
    sales_id = request.GET.get('salesperson', '')
    start_date = request.GET.get('start_date', '')
    end_date = request.GET.get('end_date', '')

    # 🌟 2. ดึงข้อมูลพื้นฐานทั้งหมด
    jobs = SolarJob.objects.select_related('customer', 'package_sold', 'salesperson', 'quotation_ref', 'technician_team').all().order_by('-created_at')

    # 🌟 3. นำข้อมูลมากรองตามเงื่อนไข (Filters)
    if search_q:
        jobs = jobs.filter(Q(code__icontains=search_q) | Q(customer__name__icontains=search_q))
    if team_id:
        jobs = jobs.filter(technician_team_id=team_id)
    if sales_id:
        jobs = jobs.filter(salesperson_id=sales_id)
    if start_date and end_date:
        # สมมติใช้ created_at เป็นเกณฑ์ในการค้นหาช่วงเวลา
        jobs = jobs.filter(created_at__date__gte=start_date, created_at__date__lte=end_date)

    # 🌟 4. นับจำนวนและแยกการ์ด (อ้างอิงจากข้อมูลที่ถูกกรองแล้ว)
    draft_jobs = jobs.filter(status='DRAFT').count()

    # 🌟 [FIXED] ให้นับรวมงานที่รอสโตร์เบิกของ (WAITING_STORE) เข้าไปในกล่อง 'เตรียมของ' ด้วย
    preparing_jobs = jobs.filter(status__in=['PREPARING', 'WAITING_STORE']).count()

    in_progress_jobs = jobs.filter(status='IN_PROGRESS').count()

    pending_expenses = SolarExpense.objects.filter(status='PENDING').count()
    from solar_sales.models import SolarExpenseClaim
    approved_expenses = SolarExpenseClaim.objects.filter(status='APPROVED').order_by('created_at')

    # 🌟 5. เตรียมข้อมูลตัวเลือกสำหรับ Dropdown ค้นหา
    teams = SubcontractorTeam.objects.filter(is_active=True)
    # สมมติกรองเซลส์ด้วยชื่อแผนก หรือดึงมาทั้งหมดถ้าไม่ได้แยก
    salespersons = Employee.objects.filter(department__name__icontains='ขาย') if hasattr(Employee, 'department') else Employee.objects.all()

    context = {
        'jobs': jobs[:50], # ลิมิตไว้ 50 งานเพื่อไม่ให้โหลดช้า
        'draft_jobs': draft_jobs,
        'preparing_jobs': preparing_jobs,
        'in_progress_jobs': in_progress_jobs,
        'pending_expenses': pending_expenses,
        'approved_expenses': approved_expenses,

        # ส่งค่าตัวกรองกลับไปที่หน้าเว็บ
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
# 📊 กระดานควบคุมงานติดตั้ง (ดูภาพรวม / Overview Board)
# ------------------------------------------
@login_required
def solar_job_overview(request):
    if not is_center_staff(request.user):
        messages.error(request, "❌ บัญชีของคุณไม่มีสิทธิ์เข้าถึงระบบควบคุมงานติดตั้ง")
        return redirect('dashboard')

    # 1. รับค่าตัวกรองและค้นหา
    search_q = request.GET.get('q', '').strip()
    team_id = request.GET.get('team', '')
    sales_id = request.GET.get('salesperson', '')
    status_filter = request.GET.get('status', '')
    start_date = request.GET.get('start_date', '')
    end_date = request.GET.get('end_date', '')
    tab = request.GET.get('tab', 'active') # active หรือ history

    # 2. Query ข้อมูลพื้นฐาน
    base_jobs = SolarJob.objects.select_related(
        'customer', 'package_sold', 'salesperson', 'quotation_ref', 'technician_team'
    ).prefetch_related('job_boms').all()

    # 3. กรองตามเงื่อนไขการค้นหา
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

    # 4. นับจำนวนสำหรับแสดงบนปุ่มแท็บ
    active_count = base_jobs.filter(status__in=['DRAFT', 'PREPARING', 'IN_PROGRESS']).count()
    completed_count = base_jobs.filter(status__in=['COMPLETED', 'CANCELLED']).count()

    # 5. แยกข้อมูลตามแท็บที่เลือก
    if tab == 'history':
        jobs = base_jobs.filter(status__in=['COMPLETED', 'CANCELLED']).order_by('-created_at')
    else:
        jobs = base_jobs.filter(status__in=['DRAFT', 'PREPARING', 'IN_PROGRESS']).order_by('created_at')

    # 6. ข้อมูลสำหรับ Dropdowns
    teams = SubcontractorTeam.objects.filter(is_active=True)
    salespersons = Employee.objects.filter(department__name__icontains='ขาย') if hasattr(Employee, 'department') else Employee.objects.all()

    context = {
        'jobs': jobs,
        'tab': tab,
        'active_count': active_count,
        'completed_count': completed_count,
        'teams': teams,
        'salespersons': salespersons,
        'search_q': search_q,
        'team_id': team_id,
        'sales_id': sales_id,
        'status_filter': status_filter,
        'start_date': start_date,
        'end_date': end_date,
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

        # 1. สร้างใบสั่งงาน (Job)
        job = SolarJob.objects.create(customer=customer, package_sold=package, status='DRAFT')

        # 🌟 2. [NEW] ระบบกางสูตร BOM อัตโนมัติ 🌟
        if package:
            # ค้นหาสูตรมาตรฐานที่ผูกกับแพ็กเกจนี้
            standard_boms = SolarStandardBOM.objects.filter(package=package)
            for std_bom in standard_boms:
                # คัดลอกมาสร้างเป็นสูตรของงานนี้ (Job BOM)
                SolarJobBOM.objects.create(
                    job=job,
                    product=std_bom.raw_material,
                    planned_quantity=std_bom.quantity,
                    actual_used_quantity=0, # เริ่มต้นเบิกจริงเป็น 0
                    unit_cost=std_bom.raw_material.cost_price # ดึงต้นทุนปัจจุบันมาเป็นฐาน
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
        form = SolarJobForm(request.POST, instance=job)
        formset = SolarBOMFormSet(request.POST, instance=job)

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

        formset = SolarBOMFormSet(instance=job)

    raw_materials = SolarProduct.objects.filter(is_active=True, product_type='RM')
    teams = SubcontractorTeam.objects.filter(is_active=True)

    return render(request, 'solar_jobs/job_manage.html', {
        'job': job,
        'form': form,
        'formset': formset,
        'raw_materials': raw_materials,
        'teams': teams
    })

# 🌟 [NEW] ฟังก์ชันดึงสูตรมาตรฐาน (BOM) มาใส่ในใบสั่งงานอัตโนมัติ 🌟
@login_required
def fetch_standard_bom(request, job_id):
    if not is_center_staff(request.user):
        messages.error(request, "❌ บัญชีของคุณไม่มีสิทธิ์ดึงสูตรการผลิต")
        return redirect('solar_center_dashboard')

    job = get_object_or_404(SolarJob, id=job_id)

    # 1. เช็คว่าใบสั่งงานนี้เลือก "แพ็กเกจ" แล้วหรือยัง
    if not job.package_sold:
        messages.error(request, "❌ ไม่สามารถดึงสูตรได้! กรุณาเลือก 'แพ็กเกจที่ต้องติดตั้ง' และกดบันทึกข้อมูลก่อนครับ")
        return redirect('solar_job_manage', job_id=job.id)

    # 2. ค้นหาสูตรมาตรฐานทั้งหมดที่ผูกกับแพ็กเกจนี้
    standard_boms = SolarStandardBOM.objects.filter(package=job.package_sold)

    if not standard_boms.exists():
        messages.warning(request, f"⚠️ ไม่พบสูตรมาตรฐานสำหรับแพ็กเกจ '{job.package_sold.name}' ในฐานข้อมูลคลังสินค้า")
        return redirect('solar_job_manage', job_id=job.id)

    # 3. ตรวจสอบว่าในงานนี้ (Job BOM) มีการดึงข้อมูลไปแล้วหรือยัง เพื่อป้องกันการกดปุ่มเบิ้ลแล้วได้สูตรซ้ำซ้อน
    existing_items_count = SolarJobBOM.objects.filter(job=job).count()
    if existing_items_count > 0:
        # ถ้าระบบเจอว่ามีแถววัตถุดิบอยู่แล้ว จะถามยืนยันผ่าน UI แต่อันนี้เป็นการดักหลังบ้านครับ
        pass

    # 4. วนลูปกางสูตร: คัดลอกข้อมูลจาก Standard BOM มาใส่ Job BOM
    added_count = 0
    for std_bom in standard_boms:
        # เช็คว่ามีวัตถุดิบตัวนี้ในรายการอยู่แล้วหรือไม่ (ป้องกันการดึงซ้ำทีละรายการ)
        obj, created = SolarJobBOM.objects.get_or_create(
            job=job,
            product=std_bom.raw_material,
            defaults={
                'planned_quantity': std_bom.quantity,
                'actual_used_quantity': 0, # ยังไม่ได้เบิกจริง
                'unit_cost': std_bom.raw_material.cost_price # ดึงต้นทุนปัจจุบันมาเป็นฐานเบื้องต้น
            }
        )
        if created:
            added_count += 1

    if added_count > 0:
        messages.success(request, f"✅ ดึงรายการวัตถุดิบตามสูตร '{job.package_sold.name}' เข้ามาเพิ่ม {added_count} รายการ สำเร็จแล้ว!")
    else:
        messages.info(request, "ℹ️ ไม่มีการเพิ่มรายการใหม่ (วัตถุดิบตามสูตรมีอยู่ในตารางครบแล้ว)")

    # 5. รีโหลดกลับไปหน้าจัดการงานเดิม เพื่อให้ตาราง Formset แสดงข้อมูลใหม่
    return redirect('solar_job_manage', job_id=job.id)

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

            # 1. อัปเดตสถานะของใบสั่งงานในกระดาน Center
            job = SolarJob.objects.get(id=job_id)
            job.status = new_status
            job.save()

            # 2. 🌟 AUTOMATION: ยิงตรงเข้าฐานข้อมูลใบเสนอราคา 🌟
            if new_status == 'COMPLETED':
                if job.quotation_ref_id:
                    # 🌟 [FIXED] ใช้คำสั่ง update() ยิงตรงเข้าระดับฐานข้อมูล ชัวร์ 100% ทะลุทุกเงื่อนไข
                    SolarQuotation.objects.filter(id=job.quotation_ref_id).update(status='READY')
                elif job.note and "QT-SOL" in str(job.note):
                    # กรณีเผื่อสร้างงานแบบไม่ผูก FK ให้ค้นหาจากใน Note
                    for word in str(job.note).split():
                        if "QT-SOL" in word:
                            qt_code = word.strip().replace(',', '').replace(':', '')
                            SolarQuotation.objects.filter(code__icontains=qt_code).update(status='READY')
                            break

            return JsonResponse({'success': True, 'message': 'อัปเดตเรียบร้อย'})
        except Exception as e:
            print(f"Error updating job: {str(e)}") # ปริ้นท์ error ลง Console ไว้เช็ค
            return JsonResponse({'success': False, 'error': str(e)})
    return JsonResponse({'success': False, 'error': 'Invalid request'})

# 🌟 [NEW] ฟังก์ชันสำหรับให้แผนก Center/บัญชี จ่ายเงินและแนบสลิปให้ช่าง 🌟
@login_required
def center_pay_expense(request, expense_id):
    if not (is_center_staff(request.user) or is_accounting_staff(request.user)):
        messages.error(request, "❌ คุณไม่มีสิทธิ์ทำรายการนี้")
        return redirect('solar_center_dashboard')

    # 🌟 [FIXED] ดึงโมเดล SolarExpenseClaim ของฝั่งช่างโซล่าเซลล์มาใช้
    from solar_sales.models import SolarExpenseClaim
    from django.utils import timezone

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

    # หลังจากอัปเดตเสร็จ ให้เด้งกลับไปที่หน้า Dashboard ของ Center
    return redirect('solar_center_dashboard')

# ------------------------------------------
# 🚀 ฟังก์ชันสำหรับ Center ส่งใบขอเบิกให้สโตร์
# ------------------------------------------
@login_required
def center_submit_requisition(request, job_id):
    if not is_center_staff(request.user):
        messages.error(request, "❌ บัญชีของคุณไม่มีสิทธิ์ทำรายการนี้")
        return redirect('solar_center_dashboard')

    job = get_object_or_404(SolarJob, id=job_id)

    if job.status == 'PREPARING' or job.status == 'DRAFT':
        job.status = 'WAITING_STORE'
        job.save()
        messages.success(request, f"✅ ส่งใบเบิกวัสดุสำหรับงาน {job.code} ไปยังสโตร์เรียบร้อยแล้ว")
    else:
        messages.warning(request, "⚠️ ไม่สามารถส่งใบเบิกได้ เนื่องจากสถานะงานไม่ถูกต้อง")

    return redirect('solar_job_manage', job_id=job.id)