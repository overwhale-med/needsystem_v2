import json
import datetime
import pytz
import base64
import math
from decimal import Decimal
from django.core.files.base import ContentFile
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.db.models import Q, Count, Sum
from django.utils import timezone
from django.db import transaction
from django.core.paginator import Paginator
from django.views.decorators.csrf import csrf_exempt

# Models
from sales.models import Quotation, QuotationItem, QuotationUpsale, QuotationDeposit, UpsaleCategory, UpsaleCatalog
from master_data.models import Customer, CompanyInfo, ShippingRate
from inventory.models import Product, Category
from hr.models import Department, Employee
from manufacturing.models import ProductionOrder, ProductionStatus, Branch, Salesperson as MfgSalesperson
from solar_jobs.models import SolarJob
from sales.forms import QuotationForm

# Services
from sales.services import is_sales_authorized, get_target_employees, get_sales_queryset, get_auto_delivery_date, parse_thai_date, get_thai_baht_text

@login_required
def quotation_list(request):
    if not is_sales_authorized(request.user):
        messages.error(request, "❌ บัญชีของคุณไม่มีสิทธิ์เข้าถึงหน้ารายการใบเสนอราคา")
        return redirect('dashboard')

    target_employees, _ = get_target_employees(request.user)
    queryset = get_sales_queryset(Quotation, request.user, target_employees).order_by('-created_at')

    is_manager = False
    is_supervisor = False
    current_emp = getattr(request.user, 'employee', None)

    # 🌟 เรียงลำดับสิทธิ์ใหม่: เช็ก Supervisor ก่อน ป้องกัน Admin แย่งสิทธิ์แสดงผล
    if current_emp:
        rank = current_emp.business_rank.lower() if current_emp.business_rank else ""
        if rank == 'supervisor':
            is_supervisor = True
            is_manager = False
        elif rank in ['manager', 'director'] or 'manager' in getattr(current_emp.position, 'title', '').lower() or 'บัญชี' in getattr(current_emp.department, 'name', ''):
            is_manager = True
        elif request.user.is_superuser:
            is_manager = True
    elif request.user.is_superuser:
        is_manager = True

    departments = []
    team_members = []

    if is_manager:
        # ผู้จัดการเห็นทุกสาขา
        departments = list(Department.objects.filter(Q(name__icontains='ทีม') | Q(name__icontains='สาขา')).order_by('name'))
        for d in departments: d.name = d.name.replace('แผนก', '').strip()
    elif is_supervisor and current_emp.department:
        # หัวหน้าสาขาให้ดึง "รายชื่อพนักงานในสาขานั้น"
        team_members = Employee.objects.filter(department=current_emp.department).order_by('first_name')

    search_query = request.GET.get('q', '')
    status_filter = request.GET.get('status')
    prod_status_filter = request.GET.get('prod_status')
    deliv_status_filter = request.GET.get('deliv_status')
    branch_filter = request.GET.get('branch', '')
    emp_filter = request.GET.get('emp', '')

    # 🌟 คืนชีพตัวกรองต่างๆ ที่หายไปกลับมา
    if branch_filter and is_manager:
        queryset = queryset.filter(employee__department_id=branch_filter)

    if emp_filter and is_supervisor:
        queryset = queryset.filter(employee_id=emp_filter)

    if status_filter:
        if status_filter == 'PENDING_CLOSING':
            queryset = queryset.filter(status='APPROVED', is_deposit_paid=False).distinct()
        elif status_filter == 'PENDING_VERIFY':
            queryset = queryset.filter(status='APPROVED', is_deposit_paid=True, is_deposit_verified=False).distinct()
        elif status_filter == 'PIPELINE':
            # 🌟 ตัวกรองใหม่: ดึงทั้ง READY (รอสั่งผลิต) และ IN_PRODUCTION (กำลังผลิต)
            queryset = queryset.filter(status='APPROVED', is_deposit_paid=True, is_deposit_verified=True).distinct()
        elif status_filter == 'READY':
            queryset = queryset.filter(status='APPROVED', is_deposit_paid=True, is_deposit_verified=True, production_orders__isnull=True).distinct()
        elif status_filter == 'IN_PRODUCTION':
            queryset = queryset.filter(status='APPROVED', is_deposit_paid=True, is_deposit_verified=True, production_orders__isnull=False).distinct()
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
            elif prod_status_filter == 'WAITING_QC_REWORK':
                 valid_jobs = valid_jobs.filter(status__in=['WAITING_QC', 'REWORK'])
            else:
                  valid_jobs = valid_jobs.filter(status=prod_status_filter)
        valid_job_ids = list(valid_jobs.values_list('id', flat=True))
        queryset = queryset.filter(production_orders__in=valid_job_ids).distinct()

    if deliv_status_filter:
        if deliv_status_filter == 'NO_TRUCK':
            valid_jobs = ProductionOrder.objects.filter(Q(status='COMPLETED') | Q(status='WAITING_QC') | Q(is_onsite=True)).filter(transporter__isnull=True)
        elif deliv_status_filter == 'DELIVERING':
            valid_jobs = ProductionOrder.objects.filter(transporter__isnull=False).exclude(delivery_status__name__in=['ส่งมอบสำเร็จ', 'ลูกค้าเซ็นรับแล้ว', 'จัดส่งเรียบร้อย'])
        elif deliv_status_filter == 'DELIVERED':
            valid_jobs = ProductionOrder.objects.filter(delivery_status__name__in=['ส่งมอบสำเร็จ', 'ลูกค้าเซ็นรับแล้ว', 'จัดส่งเรียบร้อย'])
        valid_job_ids = list(valid_jobs.values_list('id', flat=True))
        queryset = queryset.filter(production_orders__in=valid_job_ids).distinct()

    if search_query:
        queryset = queryset.filter(Q(code__icontains=search_query) | Q(customer_name__icontains=search_query)).distinct()

    tz_bkk = pytz.timezone('Asia/Bangkok')
    today_bkk = timezone.now().astimezone(tz_bkk).date()

    date_start = request.GET.get('start_date')
    date_end = request.GET.get('end_date')

    if not date_start or date_start == 'None':
        date_start = (today_bkk - datetime.timedelta(days=29)).strftime('%Y-%m-%d')
    if not date_end or date_end == 'None':
        date_end = today_bkk.strftime('%Y-%m-%d')

    if not status_filter and not prod_status_filter and not deliv_status_filter:
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
        'date_start': date_start, 'date_end': date_end, 'total_departments_count': total_departments_count,
        'team_members': team_members, 'emp_filter': emp_filter
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

            tz_bkk = pytz.timezone('Asia/Bangkok')
            now_bkk = timezone.now().astimezone(tz_bkk)

            thai_year = (now_bkk.year + 543) % 100
            prefix = f"QT-{thai_year:02d}{now_bkk.strftime('%m')}"
            last = Quotation.objects.filter(code__startswith=prefix).order_by('code').last()
            seq = int(last.code.split('-')[-1]) + 1 if last else 1
            qt.code = f"{prefix}-{seq:03d}"

            if not qt.payment_terms: qt.payment_terms = "-ชำระเงินมัดจำ 50% ของยอดรวมเพื่อยืนยันการสั่งซื้อ ส่วนที่เหลือชำระก่อนการจัดส่ง"
            if not qt.note: qt.note = "-ไม่มี-"

            qt.date = now_bkk.date()
            qt.save()
            messages.success(request, f"ร่างใบเสนอราคา {qt.code} เรียบร้อย กรุณาเพิ่มรายการสินค้า")
            return redirect('quotation_edit', qt_id=qt.id)
    else:
        tz_bkk = pytz.timezone('Asia/Bangkok')
        today_bkk = timezone.now().astimezone(tz_bkk).date()
        form = QuotationForm(initial={'date': today_bkk, 'valid_until': today_bkk + datetime.timedelta(days=15)})
    return render(request, 'sales/quotation_form.html', {'form': form})

@login_required
def quotation_edit(request, qt_id):
    if not is_sales_authorized(request.user): return redirect('dashboard')
    qt = get_object_or_404(Quotation, pk=qt_id)

    main_categories = Category.objects.all()
    products = Product.objects.filter(is_active=True, product_type='FG').exclude(code__contains='-JOB')
    products_list = [{'id': p.id, 'name': p.name, 'code': p.code, 'sell_price': float(p.sell_price), 'category_id': getattr(p, 'category_id', None)} for p in products]

    upsale_categories = UpsaleCategory.objects.filter(is_active=True)
    upsale_catalogs = UpsaleCatalog.objects.filter(is_active=True)
    upsales_list = [{'id': u.id, 'name': u.name, 'default_price': float(u.default_price), 'category_id': u.category_id} for u in upsale_catalogs]

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
    shipping_rates_json = json.dumps([{'origin': r['origin_branch'], 'province': r['destination_province'], 'price': float(r['price'])} for r in shipping_rates])

    if request.method == 'POST':
        if qt.status != 'DRAFT': return redirect('quotation_edit', qt_id=qt.id)

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
    grand_total = max((total_goods + shipping) - discount, 0)
    qt.subtotal = grand_total / Decimal('1.07')
    qt.tax_amount = grand_total - qt.subtotal
    qt.grand_total = grand_total
    qt.save()

@login_required
def delete_item(request, item_id):
    item = get_object_or_404(QuotationItem, pk=item_id)
    qt = item.quotation
    if qt.status != 'DRAFT': return redirect('quotation_edit', qt_id=qt.id)
    item.delete()
    calculate_totals(qt)
    return redirect('quotation_edit', qt_id=qt.id)

@login_required
def quotation_clone(request, qt_id):
    old_qt = get_object_or_404(Quotation, pk=qt_id)
    tz_bkk = pytz.timezone('Asia/Bangkok')
    now_bkk = timezone.now().astimezone(tz_bkk)
    thai_year = (now_bkk.year + 543) % 100
    prefix = f"QT-{thai_year:02d}{now_bkk.strftime('%m')}"
    last = Quotation.objects.filter(code__startswith=prefix).order_by('code').last()
    seq = int(last.code.split('-')[-1]) + 1 if last else 1
    new_code = f"{prefix}-{seq:03d}"

    new_qt = Quotation.objects.create(
        code=new_code, date=now_bkk.date(), valid_until=now_bkk.date() + datetime.timedelta(days=15),
        customer=old_qt.customer, customer_name=old_qt.customer_name, customer_address=old_qt.customer_address,
        customer_tax_id=old_qt.customer_tax_id, customer_phone=old_qt.customer_phone,
        employee=request.user.employee if hasattr(request.user, 'employee') else None,
        subtotal=old_qt.subtotal, discount=old_qt.discount, shipping_cost=old_qt.shipping_cost,
        tax_amount=old_qt.tax_amount, grand_total=old_qt.grand_total, status='DRAFT',
        payment_terms=old_qt.payment_terms if old_qt.payment_terms else "-ชำระเงินมัดจำ 50% ของยอดรวมเพื่อยืนยันการสั่งซื้อ ส่วนที่เหลือชำระก่อนการจัดส่ง",
        note=old_qt.note if old_qt.note else "-ไม่มี-",
    )
    for item in old_qt.items.all():
        QuotationItem.objects.create(quotation=new_qt, product=item.product, item_name=item.item_name, description=item.description, quantity=item.quantity, unit_price=item.unit_price, amount=item.amount)
    for upsale in old_qt.upsales.all():
        QuotationUpsale.objects.create(quotation=new_qt, description=upsale.description, quantity=upsale.quantity, unit_price=upsale.unit_price, total_price=upsale.total_price)

    messages.success(request, f"📋 คัดลอกเอกสารสำเร็จ! (อ้างอิงจาก {old_qt.code})")
    return redirect('quotation_edit', qt_id=new_qt.id)

@login_required
def quotation_approve(request, qt_id):
    qt = get_object_or_404(Quotation, pk=qt_id)
    qt.status = 'APPROVED'
    qt.approved_by = getattr(request.user, 'employee', None)
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
        if qt.production_orders.exists():
            messages.error(request, "❌ ไม่อนุญาตให้ยกเลิก เนื่องจากถูกส่งผลิตแล้ว")
        elif qt.is_deposit_paid:
            messages.error(request, "❌ ไม่สามารถยกเลิกได้ มีการรับมัดจำแล้ว")
        elif qt.status in ['DRAFT', 'APPROVED']:
            qt.status = 'CANCELLED'
            qt.save()
            messages.warning(request, f"⚠️ ยกเลิกใบเสนอราคา {qt.code} เรียบร้อยแล้ว")
        else: messages.error(request, "❌ สถานะไม่ถูกต้อง")
    else: messages.error(request, "❌ คุณไม่มีสิทธิ์ยกเลิกใบเสนอราคานี้")
    return redirect('quotation_list')

@login_required
def quotation_print(request, qt_id):
    qt = get_object_or_404(Quotation, pk=qt_id)
    company = CompanyInfo.objects.first()
    item_total = sum(item.quantity * item.unit_price for item in qt.items.all()) + sum(u.quantity * u.unit_price for u in qt.upsales.all())
    return render(request, 'sales/quotation_print.html', {'qt': qt, 'company': company, 'item_total': item_total})

@login_required
@transaction.atomic
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
            tz_bkk = pytz.timezone('Asia/Bangkok')
            now_bkk = timezone.now().astimezone(tz_bkk)
            thai_year = (now_bkk.year + 543) % 100
            prefix = f"RVD-{thai_year:02d}{now_bkk.strftime('%m')}"
            last_deposit = QuotationDeposit.objects.filter(code__startswith=prefix).order_by('code').last()
            seq = int(last_deposit.code.split('-')[-1]) + 1 if last_deposit else 1
            new_rvd_code = f"{prefix}-{seq:03d}"

            new_deposit = QuotationDeposit.objects.create(
                code=new_rvd_code, quotation=qt, amount=amount, payment_method=method,
                deposit_date=parse_thai_date(date_str) if date_str else now_bkk.date()
            )
            if 'deposit_slip' in request.FILES:
                new_deposit.deposit_slip = request.FILES['deposit_slip']
                new_deposit.save()

            qt.is_deposit_paid = True
            qt.is_deposit_verified = False
            qt.deposit_code = None
            qt.deposit_amount = (qt.deposit_amount if qt.deposit_amount else Decimal('0.00')) + amount
            qt.save()
            messages.success(request, f"💰 บันทึกรับมัดจำ {amount:,.2f} บาท และสร้างใบเสร็จ {new_deposit.code} เรียบร้อยแล้ว")
        if next_url: return redirect(next_url)
    return redirect('quotation_edit', qt_id=qt.id)

@login_required
def create_job_order(request, qt_id):
    qt = get_object_or_404(Quotation, pk=qt_id)
    if qt.production_orders.exists(): return redirect('quotation_list')
    if qt.is_deposit_paid and not qt.is_deposit_verified: return redirect('quotation_list')

    first_item = qt.items.filter(product__isnull=False).first()
    if not first_item: return redirect('quotation_list')

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

    start_date = deposit_date + datetime.timedelta(days=(weeks_pushed * 7))
    delivery_start_date = deposit_date + datetime.timedelta(days=14 + (weeks_pushed * 7))
    days_to_monday = delivery_start_date.weekday()
    monday_of_delivery_week = delivery_start_date - datetime.timedelta(days=days_to_monday)

    total_qty = int(first_item.quantity)
    daily_qty = math.ceil(total_qty / 5.0)
    delivery_plan_note = f"\n\n🚚 แผนการจัดส่ง (เฉลี่ยวันละ {daily_qty} หลัง):\n"
    remaining_qty = total_qty
    for i in range(5):
        current_day = monday_of_delivery_week + datetime.timedelta(days=i)
        qty_today = min(daily_qty, remaining_qty)
        if qty_today > 0: delivery_plan_note += f"- {current_day.strftime('%d/%m/%Y')}: ส่ง {qty_today} หลัง\n"
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
        branch_name = qt.employee.department.name if qt.employee.department else "สำนักงานใหญ่"
        sales_branch_obj, _ = Branch.objects.get_or_create(name=branch_name)
        sales_obj, _ = MfgSalesperson.objects.get_or_create(name=f"{qt.employee.first_name} {qt.employee.last_name}".strip(), branch=sales_branch_obj)

    is_onsite_val = request.POST.get('is_onsite') == 'on'
    job = ProductionOrder.objects.create(
        product=first_item.product, quantity=total_qty, quotation_ref=qt, customer_name=qt.customer_name,
        note=f"อ้างอิงใบเสนอราคา: {qt.code}\n{qt.note}{delivery_plan_note}", salesperson=sales_obj,
        start_date=start_date, delivery_date=deadline, deadline_date=deadline, auto_calculated_date=final_delivery_date,
        requested_date=req_date, date_approval_status=approval_status, cohort_week=assigned_cohort, is_onsite=is_onsite_val
    )

    if first_item.product and first_item.product.standard_blueprint:
        job.blueprint_file = first_item.product.standard_blueprint
        job.save()

    if first_item.product:
        p_name = first_item.product.name.lower()
        c_name = first_item.product.category.name.lower() if hasattr(first_item.product, 'category') and first_item.product.category else ""
        if 'โซล่า' in p_name or 'solar' in p_name or 'โซล่า' in c_name or 'solar' in c_name:
            try:
                SolarJob.objects.create(customer=qt.customer, salesperson=qt.employee, package_sold=first_item.product, status='DRAFT', note=f"📌 สร้างอัตโนมัติจาก {qt.code}")
            except: pass

    messages.success(request, f"🏭 ส่งข้อมูลเข้ากองกลางผลิตสำเร็จ (Job Order: {job.code})")
    return redirect('quotation_list')

@login_required
def print_deposit_contract(request, qt_id):
    qt = get_object_or_404(Quotation, pk=qt_id)
    company = CompanyInfo.objects.first()
    grand_total = qt.grand_total if qt.grand_total else Decimal('0.00')
    balance_due = qt.balance_due if hasattr(qt, 'balance_due') else (grand_total - (qt.deposit_amount or Decimal('0.00')))

    rvd_id = request.GET.get('rvd')
    if rvd_id:
        try:
            specific_deposit = QuotationDeposit.objects.get(pk=rvd_id, quotation=qt)
            deposit_amount = specific_deposit.amount
            rvd_code = specific_deposit.code
            rvd_date = specific_deposit.deposit_date
            rvd_method = specific_deposit.get_payment_method_display()
        except QuotationDeposit.DoesNotExist:
            deposit_amount = qt.deposit_amount if qt.deposit_amount else Decimal('0.00')
            rvd_code = f"QT-{qt.code.split('-')[-1]}"
            rvd_date = qt.deposit_date
            rvd_method = "ไม่ระบุ"
    else:
        # 🌟 [FIXED] แก้จาก qt.quotationdeposit_set.first() เป็น qt.deposits.first()
        first_dep = qt.deposits.first()
        if first_dep:
            deposit_amount = first_dep.amount
            rvd_code = first_dep.code
            rvd_date = first_dep.deposit_date
            rvd_method = first_dep.get_payment_method_display()
        else:
            deposit_amount = qt.deposit_amount if qt.deposit_amount else Decimal('0.00')
            rvd_code = f"QT-{qt.code.split('-')[-1]}"
            rvd_date = qt.deposit_date
            rvd_method = "ไม่ระบุ"

    return render(request, 'sales/print_deposit_contract.html', {
        'qt': qt, 'company': company,
        'grand_total_text': get_thai_baht_text(grand_total),
        'deposit_amount': deposit_amount,
        'deposit_amount_text': get_thai_baht_text(deposit_amount),
        'balance_due': balance_due,
        'balance_due_text': get_thai_baht_text(balance_due),
        'delivery_date': qt.production_orders.first().delivery_date if qt.production_orders.first() else None,
        'rvd_code': rvd_code, 'rvd_date': rvd_date, 'rvd_method': rvd_method
    })

@login_required
def deposit_print(request, qt_id):
    qt = get_object_or_404(Quotation, pk=qt_id)
    company = CompanyInfo.objects.first()
    item_total = sum(item.quantity * item.unit_price for item in qt.items.all()) + sum(u.quantity * u.unit_price for u in qt.upsales.all())
    grand_total = qt.grand_total if qt.grand_total else Decimal('0.00')
    balance_due = qt.balance_due if hasattr(qt, 'balance_due') else (grand_total - (qt.deposit_amount or Decimal('0.00')))

    rvd_id = request.GET.get('rvd')
    if rvd_id:
        try:
            specific_deposit = QuotationDeposit.objects.get(pk=rvd_id, quotation=qt)
            deposit_amount, rvd_code, rvd_date, rvd_method = specific_deposit.amount, specific_deposit.code, specific_deposit.deposit_date, specific_deposit.get_payment_method_display()
        except:
            deposit_amount, rvd_code, rvd_date, rvd_method = (qt.deposit_amount or Decimal('0.00')), f"QT-{qt.code.split('-')[-1]}", qt.deposit_date, "ไม่ระบุ"
    else:
        first_dep = qt.deposits.first()
        if first_dep:
            deposit_amount, rvd_code, rvd_date, rvd_method = first_dep.amount, first_dep.code, first_dep.deposit_date, first_dep.get_payment_method_display()
        else:
            deposit_amount, rvd_code, rvd_date, rvd_method = (qt.deposit_amount or Decimal('0.00')), f"QT-{qt.code.split('-')[-1]}", qt.deposit_date, "ไม่ระบุ"

    return render(request, 'sales/deposit_print.html', {
        'qt': qt, 'company': company, 'item_total': item_total, 'balance_due': balance_due,
        'balance_due_text': get_thai_baht_text(balance_due), 'grand_total_text': get_thai_baht_text(grand_total),
        'deposit_amount': deposit_amount, 'deposit_amount_text': get_thai_baht_text(deposit_amount),
        'rvd_code': rvd_code, 'rvd_date': rvd_date, 'rvd_method': rvd_method
    })

@csrf_exempt
def customer_sign_quotation(request, token):
    qt = get_object_or_404(Quotation, signature_token=token)
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            if data.get('signature_data'):
                format, imgstr = data.get('signature_data').split(';base64,')
                qt.customer_signature.save(f"sign_QT_{qt.code}.{format.split('/')[-1]}", ContentFile(base64.b64decode(imgstr)), save=False)
                qt.signature_date = timezone.now()
                qt.save()
                return JsonResponse({'success': True})
        except Exception as e: return JsonResponse({'success': False, 'error': str(e)})

    return render(request, 'sales/customer_sign.html', {
        'qt': qt, 'company': CompanyInfo.objects.first(),
        'item_total': sum(item.quantity * item.unit_price for item in qt.items.all()) + sum(u.quantity * u.unit_price for u in qt.upsales.all())
    })

@csrf_exempt
def customer_sign_deposit(request, token):
    qt = get_object_or_404(Quotation, deposit_signature_token=token)
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            if data.get('signature_data'):
                format, imgstr = data.get('signature_data').split(';base64,')
                qt.customer_deposit_signature.save(f"sign_DEP_{qt.code}.{format.split('/')[-1]}", ContentFile(base64.b64decode(imgstr)), save=False)
                qt.deposit_signature_date = timezone.now()
                qt.save()
                return JsonResponse({'success': True})
        except Exception as e: return JsonResponse({'success': False, 'error': str(e)})

    grand_total = qt.grand_total or Decimal('0.00')
    deposit_amount = qt.deposit_amount or Decimal('0.00')
    return render(request, 'sales/customer_sign_deposit.html', {
        'qt': qt, 'company': CompanyInfo.objects.first(),
        'grand_total_text': get_thai_baht_text(grand_total),
        'deposit_amount_text': get_thai_baht_text(deposit_amount),
        'balance_due': grand_total - deposit_amount,
        'balance_due_text': get_thai_baht_text(grand_total - deposit_amount),
        'delivery_date': qt.production_orders.first().delivery_date if qt.production_orders.first() else None,
    })

@login_required
def api_search_customer(request):
    query = request.GET.get('q', '').strip()
    if not query: return JsonResponse({'results': []})
    customers = Customer.objects.filter(Q(name__icontains=query) | Q(code__icontains=query) | Q(phone__icontains=query))[:10]
    results = [{'id': c.id, 'name': c.name, 'code': c.code, 'address': " ".join(filter(None, [c.address, f"ต.{c.sub_district}" if c.sub_district else "", f"อ.{c.district}" if c.district else "", f"จ.{c.province}" if c.province else "", c.zip_code])), 'tax_id': c.tax_id, 'phone': c.phone} for c in customers]
    return JsonResponse({'results': results})

@csrf_exempt
@login_required
def api_create_customer(request):
    if request.method == 'POST':
        try:
            name, code, phone, tax_id, address = request.POST.get('name'), request.POST.get('code'), request.POST.get('phone'), request.POST.get('tax_id'), request.POST.get('address')
            if not code: code = f"C{Customer.objects.count() + 1:04d}"
            c = Customer.objects.create(name=name, code=code, phone=phone, tax_id=tax_id, address=address)
            return JsonResponse({'success': True, 'customer': {'id': c.id, 'name': c.name, 'address': c.address, 'tax_id': c.tax_id, 'phone': c.phone}})
        except Exception as e: return JsonResponse({'success': False, 'error': str(e)})
    return JsonResponse({'success': False, 'error': 'Invalid Method'})