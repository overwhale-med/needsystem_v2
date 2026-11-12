import json
import datetime
import pytz
import openpyxl
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Q, Sum
from django.db import transaction
from django.core.paginator import Paginator
from django.utils import timezone
from django.utils.dateparse import parse_date

# Models
from sales.models import POSOrder, POSOrderItem, Invoice, InvoicePayment, QuotationDeposit, CommissionTicket
from master_data.models import CompanyInfo, Customer
from hr.models import Department, Employee
from inventory.models import Product, Category, StockMovement
from manufacturing.models import ProductionOrder, JobLaborClaim, JobAirconClaim, JobOtherExpense, MasterExpenseClaim, ServiceLaborClaim

# Services (เรียกใช้สมองกล)
from sales.services import is_sales_authorized, get_target_employees, get_sales_queryset, parse_thai_date, process_commission_logic, get_next_document_number

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
def pos_home(request):
    if not is_sales_authorized(request.user):
        messages.error(request, "❌ บัญชีของคุณไม่มีสิทธิ์ใช้งานระบบ POS")
        return redirect('dashboard')
    products = Product.objects.filter(is_active=True, stock_qty__gt=0, product_type='FG')
    categories = Category.objects.all()
    return render(request, 'sales/pos_home.html', {'products': products, 'categories': categories})

@csrf_exempt
@login_required
@transaction.atomic
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
                code=order_code, employee=current_emp, total_amount=total_amount,
                received_amount=received_amount, change_amount=received_amount - total_amount,
                payment_method=payment_method, status='PENDING', customer=customer_obj,
                customer_name=cust_name, customer_address=cust_addr,
                customer_phone=cust_phone, customer_tax_id=cust_tax
            )

            if payment_method == 'TRANSFER':
                if 'transfer_slip' in request.FILES: order.transfer_slip = request.FILES['transfer_slip']
            elif payment_method == 'CHECK':
                order.check_number = request.POST.get('check_number', '')
                order.check_bank = request.POST.get('check_bank', '')
                if 'check_slip' in request.FILES: order.check_slip = request.FILES['check_slip']

            order.save()

            for item in cart:
                product = Product.objects.get(id=item['id'])
                POSOrderItem.objects.create(
                    order=order, product=product, product_name=product.name,
                    quantity=item['qty'], price=item['price'],
                    total_price=float(item['qty']) * float(item['price'])
                )

                StockMovement.objects.create(
                    doc=None, product=product, quantity=Decimal(str(item['qty'])),
                    movement_type='RESERVE', reference_doc=order_code,
                    note=f"ขายหน้าร้าน (POS) บิลเลขที่ {order_code}", created_by=request.user
                )
                product.stock_qty -= int(item['qty'])
                product.save()

            if current_emp: process_commission_logic(total_amount, current_emp, order_code)
            return JsonResponse({'success': True, 'order_code': order_code})
        except Exception as e: return JsonResponse({'success': False, 'error': str(e)})
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
    if order.payment_method == 'TRANSFER': payment_note = "ชำระโดย: โอนเงิน (Bank Transfer)"
    elif order.payment_method == 'CHECK': payment_note = f"ชำระโดย: เช็คธนาคาร {order.check_bank} #{order.check_number}"

    grand_total = order.total_amount
    subtotal = grand_total / Decimal('1.07')
    tax_amount = grand_total - subtotal

    context = {
        'inv': order, 'company': company, 'items': items, 'item_total': item_total,
        'subtotal': subtotal, 'tax_amount': tax_amount, 'discount': Decimal('0.00'),
        'shipping_cost': Decimal('0.00'), 'note': payment_note, 'is_pos': True
    }
    return render(request, 'sales/invoice_print.html', context)

@login_required
def invoice_list(request):
    if not is_sales_authorized(request.user):
        messages.error(request, "❌ บัญชีของคุณไม่มีสิทธิ์เข้าถึงหน้ารายการใบเสร็จ")
        return redirect('dashboard')

    target_employees, _ = get_target_employees(request.user)
    qs_invoice = get_sales_queryset(Invoice, request.user, target_employees).prefetch_related('payment_history', 'quotation_ref__production_orders')
    qs_pos = get_sales_queryset(POSOrder, request.user, target_employees)

    is_manager = False
    is_supervisor = False
    current_emp = getattr(request.user, 'employee', None)
    user_groups = list(request.user.groups.values_list('name', flat=True))

    # 🌟 [NEW] เช็กสิทธิ์ Manager และ บัญชี จากสวิตช์หน้าเว็บแทน
    if request.user.is_superuser or 'Manager_Team' in user_groups or 'Executive' in user_groups or 'Accounting_Team' in user_groups:
        is_manager = True
    elif current_emp:
        rank = current_emp.business_rank.lower() if current_emp.business_rank else ""
        if rank == 'supervisor':
            is_supervisor = True

    if is_manager:
        departments = list(Department.objects.filter(Q(name__icontains='ทีม') | Q(name__icontains='สาขา')).order_by('name'))
    elif is_supervisor and current_emp and current_emp.department:
        departments = list(Department.objects.filter(id=current_emp.department.id))
    else:
        departments = []

    for d in departments: d.name = d.name.replace('แผนก', '').strip()

    search_query = request.GET.get('q', '')
    status_filter = request.GET.get('status', '')
    branch_filter = request.GET.get('branch', '')

    if branch_filter and (is_manager or is_supervisor):
        qs_invoice = qs_invoice.filter(employee__department_id=branch_filter)
        qs_pos = qs_pos.filter(employee__department_id=branch_filter)

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

    tz_bkk = pytz.timezone('Asia/Bangkok')
    today_bkk = timezone.now().astimezone(tz_bkk).date()
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')

    if not start_date or start_date == 'None': start_date = today_bkk.strftime('%Y-%m-%d')
    if not end_date or end_date == 'None': end_date = today_bkk.strftime('%Y-%m-%d')

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
    current_emp = getattr(request.user, 'employee', None)
    if doc_type == 'pos':
        obj = get_object_or_404(POSOrder, id=doc_id)
        if obj.status != 'PAID':
            obj.status = 'PAID'
            obj.save()
            sale_amt = getattr(obj, 'total_amount', getattr(obj, 'grand_total', 0))
            if obj.employee: process_commission_logic(sale_amt, obj.employee, obj.code)
        messages.success(request, f"✅ ยืนยันรับชำระเงินเอกสาร {obj.code} ปิดการขายเรียบร้อยแล้ว!")
    else:
        obj = get_object_or_404(Invoice, id=doc_id)
        if obj.status == 'PENDING':
            pending_payments = obj.payment_history.filter(status='PENDING')
            pending_payments.update(status='VERIFIED')
            if obj.balance_amount <= 0:
                obj.status = 'PAID'
                obj.verified_by = current_emp
                obj.save()
                sale_amt = getattr(obj, 'total_amount', getattr(obj, 'grand_total', 0))
                if obj.employee:
                    process_commission_logic(sale_amt, obj.employee, obj.code)
                    if obj.quotation_ref and obj.quotation_ref.grand_total > 0:
                        if not CommissionTicket.objects.filter(quotation_ref=obj.quotation_ref, ticket_type__in=['2.5%', '3%']).exists():
                            grand_total = obj.quotation_ref.grand_total
                            base_amount = grand_total - (grand_total * Decimal('0.10'))
                            comm_amount = base_amount * Decimal('0.025')
                            CommissionTicket.objects.create(
                                ticket_type='2.5%',
                                quotation_ref=obj.quotation_ref,
                                invoice_ref=obj,
                                base_amount=base_amount,
                                commission_amount=comm_amount,
                                status='AVAILABLE'
                            )
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
        try: amount = Decimal(amount_str)
        except: amount = Decimal('0.00')

        if amount > 0:
            payment = InvoicePayment(invoice=inv, amount=amount, payment_method=method, payment_date=parse_thai_date(date_str) if date_str else timezone.now().date())
            if method == 'TRANSFER' and 'transfer_slip' in request.FILES: payment.transfer_slip = request.FILES['transfer_slip']
            elif method == 'CHECK':
                payment.check_number = request.POST.get('check_number', '')
                payment.check_bank = request.POST.get('check_bank', '')
                if 'check_slip' in request.FILES: payment.check_slip = request.FILES['check_slip']
            payment.save()

            inv.balance_amount -= amount
            if inv.balance_amount < 0: inv.balance_amount = Decimal('0.00')
            inv.status = 'PENDING'
            inv.save()
            messages.success(request, f"💰 บันทึกรับชำระเงิน {amount:,.2f} บาท สำหรับเอกสาร {inv.code} สำเร็จ! (รอตรวจสอบยอดจากฝ่ายบัญชี)")
    return redirect('invoice_list')

@login_required
def delete_invoice_payment(request, pay_id):
    if not is_sales_authorized(request.user):
        messages.error(request, "❌ บัญชีของคุณไม่มีสิทธิ์ดำเนินการนี้")
        return redirect('invoice_list')
    payment = get_object_or_404(InvoicePayment, pk=pay_id)
    inv = payment.invoice
    if payment.status == 'VERIFIED':
        messages.error(request, "❌ ไม่สามารถลบได้ เนื่องจากฝ่ายบัญชีได้ทำการตรวจสอบและรับเงินเข้าระบบไปแล้ว")
        return redirect('invoice_list')
    amount_to_return = payment.amount
    payment.delete()
    inv.balance_amount += amount_to_return
    if inv.balance_amount >= inv.grand_total: inv.status = 'UNPAID'
    else: inv.status = 'PENDING'
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
        if inv.payment_method == 'TRANSFER': note = f"ชำระโดย: โอนเงินเข้าบัญชี (วันที่ {p_date})"
        elif inv.payment_method == 'CHECK': note = f"ชำระโดย: เช็คธนาคาร {inv.check_bank} เลขที่ {inv.check_number} (วันที่ {p_date})"
        elif inv.payment_method == 'CASH': note = f"ชำระโดย: เงินสด (วันที่ {p_date})"
        else: note = "ชำระเงินเรียบร้อยแล้ว"
    else:
        if inv.quotation_ref:
            if inv.quotation_ref.payment_terms and inv.quotation_ref.payment_terms != "-ไม่มี-": note = f"เงื่อนไขการชำระเงิน:\n{inv.quotation_ref.payment_terms}"
            elif inv.quotation_ref.note: note = inv.quotation_ref.note

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

    if not hasattr(inv, 'total_amount'): inv.total_amount = inv.grand_total
    if not hasattr(inv, 'deposit_amount'):
        inv.deposit_amount = Decimal('0.00')
        inv.balance_amount = inv.grand_total

    context = {
        'inv': inv, 'company': company, 'items': items, 'item_total': item_total,
        'subtotal': subtotal, 'tax_amount': tax_amount, 'discount': discount,
        'shipping_cost': shipping_cost, 'note': note,
    }
    return render(request, 'sales/invoice_print.html', context)

@login_required
def deposit_list(request):
    target_employees, _ = get_target_employees(request.user)
    qs = QuotationDeposit.objects.filter(quotation__employee_id__in=target_employees.values_list('id', flat=True)).select_related('quotation', 'quotation__customer', 'quotation__employee', 'quotation__employee__department')

    search_query = request.GET.get('q', '')
    status_filter = request.GET.get('status')
    start_date_str = request.GET.get('start_date')
    end_date_str = request.GET.get('end_date')

    if search_query: qs = qs.filter(Q(code__icontains=search_query) | Q(quotation__code__icontains=search_query) | Q(quotation__customer_name__icontains=search_query))
    if status_filter == 'VERIFIED': qs = qs.filter(is_verified=True)
    elif status_filter == 'PENDING': qs = qs.filter(is_verified=False)

    if start_date_str and end_date_str:
        try:
            start_date = parse_date(start_date_str)
            end_date = parse_date(end_date_str)
            if start_date and end_date: qs = qs.filter(deposit_date__range=[start_date, end_date])
        except Exception: pass

    qs = qs.order_by('-deposit_date', '-created_at')
    paginator = Paginator(qs, 15)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'sales/deposit_list.html', {
        'page_obj': page_obj, 'search_query': search_query, 'status_filter': status_filter,
        'start_date': start_date_str, 'end_date': end_date_str
    })

@login_required
@transaction.atomic
def verify_deposit(request, deposit_id):
    deposit = get_object_or_404(QuotationDeposit, pk=deposit_id)
    deposit.is_verified = True
    deposit.save()

    qt = deposit.quotation
    qt.is_deposit_verified = True
    qt.save()

    if qt.employee and deposit.amount > 0:
        grand_total = qt.grand_total if qt.grand_total else Decimal('0.00')
        base_amount = grand_total - (grand_total * Decimal('0.10'))
        if not CommissionTicket.objects.filter(quotation_ref=qt, ticket_type='2%').exists():
            CommissionTicket.objects.create(ticket_type='2%', quotation_ref=qt, base_amount=base_amount, commission_amount=base_amount * Decimal('0.02'))
        if not CommissionTicket.objects.filter(quotation_ref=qt, ticket_type='0.5%').exists():
            CommissionTicket.objects.create(ticket_type='0.5%', quotation_ref=qt, base_amount=base_amount, commission_amount=base_amount * Decimal('0.005'))

    messages.success(request, f"✅ บัญชียืนยันตรวจสอบยอดมัดจำใบเสร็จ {deposit.code} เรียบร้อยแล้ว! (ระบบสร้างตั๋วคอมมิชชัน 0.5% และ 2% ให้พนักงานขายแล้ว)")
    return redirect('deposit_list')

@login_required
def master_job_report(request):
    current_emp = getattr(request.user, 'employee', None)
    is_authorized = False
    user_groups = list(request.user.groups.values_list('name', flat=True))
    
    # 🌟 [NEW] เช็กสิทธิ์ Manager และ บัญชี จากสวิตช์หน้าเว็บแทน
    if request.user.is_superuser or 'Manager_Team' in user_groups or 'Executive' in user_groups or 'Accounting_Team' in user_groups:
        is_authorized = True

    if not is_authorized:
        messages.error(request, "❌ บัญชีของคุณไม่มีสิทธิ์เข้าถึงหน้า Master Job Report")
        return redirect('dashboard')

    if request.method == 'POST' and 'action' in request.POST:
        action = request.POST.get('action')
        if action == 'submit_expense_claim':
            job_id = request.POST.get('job_id')
            claim_type = request.POST.get('claim_type')
            if not job_id:
                messages.error(request, "❌ ไม่พบรหัสอ้างอิง JOB")
                return redirect('master_job_report')
            order = get_object_or_404(ProductionOrder, pk=job_id)
            try:
                amount = Decimal(request.POST.get('claim_amount', '0').replace(',', ''))
                slip_file = request.FILES.get('claim_slip')
                if amount <= 0:
                    messages.error(request, "❌ ยอดเงินเบิกต้องมากกว่า 0 บาท")
                    return redirect('master_job_report')
                if not slip_file:
                    messages.error(request, "❌ กรุณาแนบรูปบิล/หลักฐานหน้างาน")
                    return redirect('master_job_report')

                if claim_type == 'LABOR':
                    if order.labor_claims.exists():
                        messages.error(request, "❌ งานนี้มีรายการเบิกค่าแรงอยู่แล้ว ไม่สามารถตั้งเบิกซ้ำได้")
                        return redirect('master_job_report')
                    JobLaborClaim.objects.create(production_order=order, requester=current_emp, contractor_name=request.POST.get('contractor_name', ''), amount=amount, slip_image=slip_file, status='UNCLAIMED')
                elif claim_type == 'AIRCON':
                    if order.aircon_claims.exists():
                        messages.error(request, "❌ งานนี้มีรายการเบิกค่าแอร์อยู่แล้ว ไม่สามารถตั้งเบิกซ้ำได้")
                        return redirect('master_job_report')
                    JobAirconClaim.objects.create(production_order=order, requester=current_emp, technician_name=request.POST.get('technician_name', ''), description=request.POST.get('aircon_desc', ''), amount=amount, slip_image=slip_file, status='UNCLAIMED')
                elif claim_type == 'OTHER':
                    JobOtherExpense.objects.create(production_order=order, requester=current_emp, description=request.POST.get('other_desc', ''), amount=amount, receipt_image=slip_file, status='UNCLAIMED')
                messages.success(request, f"🛒 หยอดบิลงาน {order.code} ลงตะกร้าเบิกส่วนตัวสำเร็จ!")
            except Exception as e: messages.error(request, f"❌ เกิดข้อผิดพลาด: {str(e)}")

        elif action == 'edit_expense_claim':
            claim_id = request.POST.get('claim_id')
            claim_type = request.POST.get('claim_type')
            try:
                amount = Decimal(request.POST.get('claim_amount', '0').replace(',', ''))
                slip_file = request.FILES.get('claim_slip')
                if amount <= 0:
                    messages.error(request, "❌ ยอดเงินต้องมากกว่า 0 บาท")
                    return redirect('master_job_report')
                if claim_type == 'LABOR':
                    claim = get_object_or_404(JobLaborClaim, pk=claim_id, status='UNCLAIMED')
                    claim.contractor_name = request.POST.get('contractor_name', claim.contractor_name)
                    claim.amount = amount
                    if slip_file: claim.slip_image = slip_file
                    claim.save()
                elif claim_type == 'AIRCON':
                    claim = get_object_or_404(JobAirconClaim, pk=claim_id, status='UNCLAIMED')
                    claim.technician_name = request.POST.get('technician_name', claim.technician_name)
                    claim.description = request.POST.get('aircon_desc', claim.description)
                    claim.amount = amount
                    if slip_file: claim.slip_image = slip_file
                    claim.save()
                elif claim_type == 'OTHER':
                    claim = get_object_or_404(JobOtherExpense, pk=claim_id, status='UNCLAIMED')
                    claim.description = request.POST.get('other_desc', claim.description)
                    claim.amount = amount
                    if slip_file: claim.receipt_image = slip_file
                    claim.save()
                messages.success(request, "✅ บันทึกการแก้ไขข้อมูลสำเร็จ!")
            except Exception: messages.error(request, "❌ ไม่สามารถแก้ไขได้ หรือบิลนี้ถูกส่งไปแล้ว")

        elif action == 'delete_expense_claim':
            claim_id = request.POST.get('claim_id')
            claim_type = request.POST.get('claim_type')
            try:
                if claim_type == 'LABOR': get_object_or_404(JobLaborClaim, pk=claim_id, status='UNCLAIMED').delete()
                elif claim_type == 'AIRCON': get_object_or_404(JobAirconClaim, pk=claim_id, status='UNCLAIMED').delete()
                elif claim_type == 'OTHER': get_object_or_404(JobOtherExpense, pk=claim_id, status='UNCLAIMED').delete()
                messages.success(request, "🗑️ ลบรายการตั้งเบิกออกจากตะกร้าเรียบร้อยแล้ว")
            except Exception: messages.error(request, "❌ ไม่สามารถลบได้ หรือบิลนี้ถูกส่งไปแล้ว")
        return redirect('master_job_report')

    jobs_query = ProductionOrder.objects.select_related('quotation_ref', 'logistics_claim').prefetch_related(
        'labor_claims', 'aircon_claims', 'other_expenses', 'service_tickets', 'service_tickets__labor_claims', 'service_tickets__labor_claims__master_claim'
    ).order_by('-id')

    search_query = request.GET.get('q', '')
    if search_query:
        jobs_query = jobs_query.filter(Q(code__icontains=search_query) | Q(quotation_ref__code__icontains=search_query) | Q(customer_name__icontains=search_query)).distinct()

    paginator = Paginator(jobs_query, 20)
    page_obj = paginator.get_page(request.GET.get('page'))

    qt_ids = [job.quotation_ref_id for job in page_obj if job.quotation_ref_id]
    inv_dict = {inv.quotation_ref_id: inv for inv in Invoice.objects.filter(quotation_ref_id__in=qt_ids)}
    tickets = CommissionTicket.objects.filter(Q(quotation_ref_id__in=qt_ids) | Q(invoice_ref__quotation_ref_id__in=qt_ids))

    ticket_dict_05, ticket_dict_2, ticket_dict_3 = {}, {}, {}
    for t in tickets:
        if t.ticket_type == '0.5%' and t.quotation_ref_id: ticket_dict_05.setdefault(t.quotation_ref_id, []).append(t)
        elif t.ticket_type == '2%' and t.quotation_ref_id: ticket_dict_2.setdefault(t.quotation_ref_id, []).append(t)
        elif t.ticket_type in ['2.5%', '3%']:
            q_id = t.quotation_ref_id or getattr(t.invoice_ref, 'quotation_ref_id', None)
            if q_id: ticket_dict_3.setdefault(q_id, []).append(t)

    cart_count = 0
    if current_emp:
        cart_count = JobLaborClaim.objects.filter(requester=current_emp, status='UNCLAIMED').count() + JobAirconClaim.objects.filter(requester=current_emp, status='UNCLAIMED').count() + JobOtherExpense.objects.filter(requester=current_emp, status='UNCLAIMED').count()

    for job in page_obj:
        if job.quotation_ref_id:
            job.matched_invoice = inv_dict.get(job.quotation_ref_id)
            job.matched_tickets_05 = ticket_dict_05.get(job.quotation_ref_id, [])
            job.matched_tickets_2 = ticket_dict_2.get(job.quotation_ref_id, [])
            job.matched_tickets_3 = ticket_dict_3.get(job.quotation_ref_id, [])
        else:
            job.matched_invoice = None
            job.matched_tickets_05, job.matched_tickets_2, job.matched_tickets_3 = [], [], []

    return render(request, 'sales/master_job_report.html', {'page_obj': page_obj, 'search_query': search_query, 'cart_count': cart_count})

@login_required
def expense_cart_view(request):
    current_emp = getattr(request.user, 'employee', None)
    if not current_emp:
        messages.error(request, "❌ ข้อมูลพนักงานไม่สมบูรณ์")
        return redirect('master_job_report')

    labor_items = JobLaborClaim.objects.filter(requester=current_emp, status='UNCLAIMED').order_by('created_at')
    aircon_items = JobAirconClaim.objects.filter(requester=current_emp, status='UNCLAIMED').order_by('created_at')
    other_items = JobOtherExpense.objects.filter(requester=current_emp, status='UNCLAIMED').order_by('created_at')
    service_labor_items = ServiceLaborClaim.objects.filter(requester=current_emp, status='UNCLAIMED').order_by('created_at')
    master_claims = MasterExpenseClaim.objects.filter(requester=current_emp).order_by('-created_at')
    bank_choices = MasterExpenseClaim.BANK_CHOICES

    return render(request, 'sales/expense_cart.html', {
        'labor_items': labor_items, 'aircon_items': aircon_items, 'other_items': other_items,
        'service_labor_items': service_labor_items, 'master_claims': master_claims, 'bank_choices': bank_choices
    })

@login_required
@transaction.atomic
def submit_expense_cart(request):
    if request.method == 'POST':
        current_emp = getattr(request.user, 'employee', None)
        selected_labors = request.POST.getlist('labor_ids')
        selected_aircons = request.POST.getlist('aircon_ids')
        selected_others = request.POST.getlist('other_ids')
        selected_service_labors = request.POST.getlist('service_labor_ids')
        bank_name, bank_acc_num, bank_acc_name = request.POST.get('bank_name'), request.POST.get('bank_account_number'), request.POST.get('bank_account_name')

        if not (selected_labors or selected_aircons or selected_others or selected_service_labors):
            messages.error(request, "❌ กรุณาเลือกบิลอย่างน้อย 1 รายการเพื่อสร้างใบคุมรวม")
            return redirect('expense_cart_view')
        if not bank_name or not bank_acc_num or not bank_acc_name:
            messages.error(request, "❌ กรุณากรอกข้อมูลบัญชีธนาคารให้ครบถ้วนเพื่อความรวดเร็วในการโอนเงิน")
            return redirect('expense_cart_view')

        labor_qs = JobLaborClaim.objects.filter(id__in=selected_labors, requester=current_emp, status='UNCLAIMED')
        aircon_qs = JobAirconClaim.objects.filter(id__in=selected_aircons, requester=current_emp, status='UNCLAIMED')
        other_qs = JobOtherExpense.objects.filter(id__in=selected_others, requester=current_emp, status='UNCLAIMED')
        service_labor_qs = ServiceLaborClaim.objects.filter(id__in=selected_service_labors, requester=current_emp, status='UNCLAIMED')

        grand_total = sum(item.amount for item in labor_qs) + sum(item.amount for item in aircon_qs) + sum(item.amount for item in other_qs) + sum(item.amount for item in service_labor_qs)

        if grand_total > 0:
            master_claim = MasterExpenseClaim.objects.create(requester=current_emp, total_amount=grand_total, bank_name=bank_name, bank_account_number=bank_acc_num, bank_account_name=bank_acc_name, status='PENDING')
            labor_qs.update(master_claim=master_claim, status='PENDING')
            aircon_qs.update(master_claim=master_claim, status='PENDING')
            other_qs.update(master_claim=master_claim, status='PENDING')
            service_labor_qs.update(master_claim=master_claim, status='PENDING')
            messages.success(request, f"🎉 สร้างใบคุมรวม {master_claim.code} จำนวน {grand_total:,.2f} บาท สำเร็จ!")
        else: messages.error(request, "❌ ยอดเงินเบิกต้องมากกว่า 0 บาท")
    return redirect('expense_cart_view')