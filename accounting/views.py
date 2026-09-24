from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum
from django.utils import timezone
from django.db import transaction
from .models import Income, Expense

from sales.models import POSOrder, Invoice, Quotation
# 🌟 [FIXED] เพิ่มการ Import SolarInvoice เข้ามาเพื่อให้ระบบรู้จัก 🌟
from solar_sales.models import SolarQuotation, SolarInvoice
from purchasing.models import PurchaseOrder
from solar_purchasing.models import SolarPurchaseOrder
from manufacturing.models import LogisticsClaim, BlueprintClaim

@login_required
def accounting_dashboard(request):
    today = timezone.now().date()
    current_month = today.month
    current_year = today.year

    incomes = Income.objects.filter(date__month=current_month, date__year=current_year)
    expenses = Expense.objects.filter(date__month=current_month, date__year=current_year)

    total_income = incomes.aggregate(Sum('amount'))['amount__sum'] or 0
    total_expense = expenses.aggregate(Sum('amount'))['amount__sum'] or 0
    net_balance = total_income - total_expense

    # 🌟 [FIXED] อัปเดตตัวนับเลขให้ไปนับจากสลิปมัดจำ (RVD) ที่ยังไม่ได้ตรวจ
    from sales.models import QuotationDeposit
    pending_deposits_quotation = QuotationDeposit.objects.filter(is_verified=False).count()

    pending_deposits_solar = SolarQuotation.objects.filter(is_deposit_paid=True, is_deposit_verified=False).count()
    pending_deposits = pending_deposits_quotation + pending_deposits_solar

    pending_sales = (
        Invoice.objects.filter(status='PENDING').count() +
        POSOrder.objects.filter(status='PENDING').count() +
        SolarInvoice.objects.filter(status='PENDING_VERIFY').count()
    )

    pending_purchases_normal = PurchaseOrder.objects.filter(status='APPROVED', payment_status__in=['PENDING', 'DEPOSIT']).count()
    pending_purchases_solar = SolarPurchaseOrder.objects.filter(status='APPROVED', payment_status__in=['PENDING', 'DEPOSIT']).count()
    pending_purchases = pending_purchases_normal + pending_purchases_solar

    pending_logistics = LogisticsClaim.objects.filter(status='PENDING').count()
    pending_blueprints = BlueprintClaim.objects.filter(status='PENDING').count()

    # 🌟 [NEW] นับคิวใบคุมเบิกรวม (Master Expense Claim) 🌟
    from manufacturing.models import MasterExpenseClaim
    pending_job_expenses = MasterExpenseClaim.objects.filter(status='PENDING').count()

    total_pending_payments = pending_purchases + pending_logistics + pending_blueprints + pending_job_expenses

    recent_incomes = list(Income.objects.all().order_by('-date', '-id')[:5])
    recent_expenses = list(Expense.objects.all().order_by('-date', '-id')[:5])

    for i in recent_incomes: i.type = 'income'
    for e in recent_expenses: e.type = 'expense'

    recent_transactions = sorted(recent_incomes + recent_expenses, key=lambda x: x.date, reverse=True)[:10]

    context = {
        'total_income': total_income, 'total_expense': total_expense, 'net_balance': net_balance,
        'pending_deposits': pending_deposits, 'pending_sales': pending_sales,
        'pending_purchases_normal': pending_purchases_normal,
        'pending_purchases_solar': pending_purchases_solar,
        'pending_logistics': pending_logistics,
        'pending_blueprints': pending_blueprints,
        'pending_job_expenses': pending_job_expenses, # 🌟 เพิ่มตัวแปรนี้
        'total_pending_payments': total_pending_payments,
        'recent_transactions': recent_transactions,
    }
    return render(request, 'accounting/dashboard.html', context)


# 🌟 ศูนย์รวมการตรวจสอบเอกสาร (ดึงข้อมูลมาจากฝ่ายอื่น รวมโซล่าเซลล์) 🌟
@login_required
def verification_hub(request, task_type):
    is_accounting = False
    if request.user.is_superuser:
        is_accounting = True
    elif hasattr(request.user, 'employee') and request.user.employee:
        dept = request.user.employee.department.name if request.user.employee.department else ''
        if 'บัญชี' in dept or 'Account' in dept: is_accounting = True

    if not is_accounting:
        messages.error(request, "❌ หน้าต่างนี้สงวนสิทธิ์เฉพาะเจ้าหน้าที่ฝ่ายบัญชีเท่านั้น")
        return redirect('dashboard')

    context = {'task_type': task_type}

    if task_type == 'deposits':
        # 🌟 [FIXED] ดึงข้อมูลสลิปมัดจำ (RVD) ที่ยังไม่ได้ตรวจมาแสดงแทน (สำหรับน็อคดาวน์)
        from sales.models import QuotationDeposit
        rvd_list = list(QuotationDeposit.objects.filter(is_verified=False))
        solar_list = list(SolarQuotation.objects.filter(is_deposit_paid=True, is_deposit_verified=False))

        # เพิ่มป้ายกำกับแยกระบบให้บัญชีเห็นชัดเจน
        for item in rvd_list: item.system_type = 'quotation_rvd'
        for item in solar_list: item.system_type = 'solar'

        # สร้าง List รวม โดยดึงเวลาสร้างสลิป (created_at) มาเทียบกับวันในใบเสนอราคา
        combined_list = rvd_list + solar_list
        context['items'] = sorted(combined_list, key=lambda x: getattr(x, 'created_at', timezone.now()), reverse=True)

        context['title'] = 'ตรวจสอบรับเงินมัดจำฝ่ายขาย (น็อคดาวน์ & โซล่าเซลล์)'
        context['icon'] = 'fa-hand-holding-usd text-success'

    elif task_type == 'invoices':
        inv_list = list(Invoice.objects.filter(status='PENDING'))
        pos_list = list(POSOrder.objects.filter(status='PENDING'))
        solar_inv_list = list(SolarInvoice.objects.filter(status='PENDING_VERIFY')) # 🌟 [NEW] โหลดบิลโซล่า

        # แยกประเภทระบบให้บัญชีดูง่าย
        for item in inv_list: item.system_type = 'invoice'
        for item in pos_list: item.system_type = 'pos'
        for item in solar_inv_list: item.system_type = 'solar_invoice'

        # รวมลิสต์และเรียงวันที่
        context['items'] = sorted(inv_list + pos_list + solar_inv_list, key=lambda x: getattr(x, 'created_at', getattr(x, 'date', timezone.now())), reverse=True)
        context['title'] = 'ตรวจสอบรับชำระบิลขาย (Invoices, POS & Solar)'
        context['icon'] = 'fa-file-invoice-dollar text-primary'

    elif task_type == 'po_payments':
        # 🌟 ดึงแค่บิลระบบปกติ (บ้านน็อคดาวน์)
        context['items'] = PurchaseOrder.objects.filter(status='APPROVED', payment_status__in=['PENDING', 'DEPOSIT']).order_by('-created_at')
        context['title'] = 'ทำจ่ายเงินร้านค้า (PO Suppliers) - บ้านน็อคดาวน์'
        context['icon'] = 'fa-shopping-cart text-danger'

    # 🌟 เพิ่มเงื่อนไขสำหรับดึงหน้าจ่ายเงิน Solar PO โดยเฉพาะ 🌟
    elif task_type == 'solar_po_payments':
        context['items'] = SolarPurchaseOrder.objects.filter(status='APPROVED', payment_status__in=['PENDING', 'DEPOSIT']).order_by('-created_at')
        context['title'] = 'ทำจ่ายเงินร้านค้า (Solar PO) - ระบบโซล่าเซลล์'
        context['icon'] = 'fa-solar-panel text-warning'

    # 🌟 [NEW] เพิ่มคิวงานสำหรับตรวจสอบและจ่ายเงินค่าคอมมิชชันโซล่าเซลล์ 🌟
    elif task_type == 'solar_commissions':
        from solar_sales.models import SolarCommissionClaim
        context['items'] = SolarCommissionClaim.objects.filter(status='PENDING').order_by('created_at')
        context['title'] = 'ทำจ่ายค่าคอมมิชชัน - ระบบโซล่าเซลล์'
        context['icon'] = 'fa-hand-holding-usd text-success'

    elif task_type == 'knockdown_commissions':
        from sales.models import CommissionClaim
        items = CommissionClaim.objects.filter(status='PENDING').order_by('created_at')
        title = "ทำจ่ายคอมมิชชัน - ระบบบ้านน็อคดาวน์"
        icon = "fa-hand-holding-usd text-primary"
        context['items'] = items
        context['title'] = title
        context['icon'] = icon

    return render(request, 'accounting/verification_hub.html', context)

# 🌟 ฟังก์ชันกดยืนยันอนุมัติและลงบันทึกบัญชีอัตโนมัติ (รองรับทั้งน็อคดาวน์และโซล่าเซลล์) 🌟
@login_required
def approve_transaction(request, task_type, item_id):
    if request.method == 'POST':
        if task_type == 'deposits':
            doc_system = request.POST.get('doc_system', '').strip()

            if doc_system == 'solar':
                qt = get_object_or_404(SolarQuotation, id=item_id)
                qt.is_deposit_verified = True
                qt.save()

                # 🌟 [NEW] ระบบอัตโนมัติ: สร้างใบคุมสิทธิ์ 2% ส่งไปที่ศูนย์ตั้งเบิกโซล่าเซลล์
                from solar_sales.models import SolarCommissionTicket
                from decimal import Decimal
                base_amount = qt.subtotal - qt.discount + qt.survey_fee
                comm_amount = base_amount * Decimal('0.02')

                SolarCommissionTicket.objects.get_or_create(
                    ticket_type='2%',
                    quotation_ref=qt,
                    defaults={'base_amount': base_amount, 'commission_amount': comm_amount}
                )

                Income.objects.create(title=f"รับมัดจำใบเสนอราคาโซล่า #{qt.code}", amount=qt.deposit_amount, date=timezone.now().date(), note="อนุมัติโดยฝ่ายบัญชี")
                messages.success(request, f"✅ ยืนยันรับมัดจำโซล่า {qt.code} พร้อมสร้างโควตาเบิก 2% สำเร็จ!")
            else:
                # 🌟 [FIXED] อนุมัติสลิป RVD ทีละใบสำหรับน็อคดาวน์
                from sales.models import QuotationDeposit
                dep = get_object_or_404(QuotationDeposit, id=item_id)
                dep.is_verified = True
                dep.save()

                # ไปเช็คว่าถ้าสลิปทุกใบใน Quotation นี้ตรวจหมดแล้ว ให้ปรับแม่เป็นตรวจแล้วด้วย
                qt = dep.quotation
                unverified_count = qt.deposits.filter(is_verified=False).count()
                if unverified_count == 0:
                    qt.is_deposit_verified = True
                    qt.save()

                Income.objects.create(title=f"รับมัดจำ RVD #{dep.code} (อ้างอิง: {qt.code})", amount=dep.amount, date=timezone.now().date(), note="อนุมัติโดยฝ่ายบัญชี")
                messages.success(request, f"✅ ยืนยันรับมัดจำ {dep.code} เข้าสู่ระบบบัญชีเรียบร้อย")

        elif task_type == 'invoices':
            doc_type = request.POST.get('doc_type', '').strip().lower()
            doc_system = request.POST.get('doc_system', '').strip().lower() # 🌟 [NEW] รับค่าว่าระบบไหน
            inv = None
            amount = 0

            # 🌟 [NEW] จัดการอนุมัติรับเงินของบิล Solar
            if doc_system == 'solar_invoice':
                inv = get_object_or_404(SolarInvoice, id=item_id)
                amount = inv.payment_amount

                # ตัดยอดค้างชำระ
                inv.balance_amount -= amount
                if inv.balance_amount <= 0:
                    inv.balance_amount = 0
                    inv.status = 'PAID'

                    # 🌟 [NEW] ระบบอัตโนมัติ: ถ้าจ่ายครบ 100% ให้สร้างคูปอง 13.5% ทันที
                    if inv.quotation_ref:
                        from solar_sales.models import SolarCommissionTicket
                        from decimal import Decimal
                        base_amount = inv.quotation_ref.subtotal - inv.quotation_ref.discount + inv.quotation_ref.survey_fee
                        comm_amount = base_amount * Decimal('0.135')

                        SolarCommissionTicket.objects.get_or_create(
                            ticket_type='13.5%',
                            invoice_ref=inv,
                            defaults={'base_amount': base_amount, 'commission_amount': comm_amount}
                        )
                else:
                    inv.status = 'UNPAID' # ถ้าจ่ายไม่ครบ ให้กลับไปเป็น UNPAID ทวงต่อ

                inv.save()

                # ลงบัญชีรายรับอัตโนมัติ
                Income.objects.create(
                    title=f"รับชำระบิลโซล่าเซลล์ #{inv.code}",
                    amount=amount,
                    date=timezone.now().date(),
                    note=f"ยืนยันรับชำระโดยบัญชี (ช่องทาง: {inv.payment_method})"
                )
                messages.success(request, f"✅ ยืนยันรับชำระเงินบิลโซล่า {inv.code} และอัปเดตสิทธิ์ค่าคอมมิชชันเรียบร้อย")
                return redirect('accounting_verification_hub', task_type=task_type)

            # 🌟 [FIXED] จัดการเงื่อนไขสำหรับระบบน็อคดาวน์ปกติ (Invoice และ POS)
            else:
                if doc_type == 'pos':
                    inv = get_object_or_404(POSOrder, id=item_id)
                else:
                    inv = get_object_or_404(Invoice, id=item_id)

                amount = inv.grand_total # ยอดชำระเต็มจำนวนของระบบเก่า
                inv.status = 'PAID'
                inv.save()

                Income.objects.create(
                    title=f"รับชำระบิลขาย #{inv.code}",
                    amount=amount,
                    date=timezone.now().date(),
                    note="ชำระเต็มจำนวน"
                )
                messages.success(request, f"✅ ยืนยันรับชำระ {inv.code} เข้าสู่ระบบบัญชีเรียบร้อย")

        elif task_type == 'po_payments':
            po = get_object_or_404(PurchaseOrder, id=item_id)
            payments = po.payments.all()
            total_paid = payments.aggregate(Sum('amount'))['amount__sum'] or 0
            balance = float(po.total_amount) - float(total_paid)

            po.payment_status = 'PAID'
            po.save()
            Expense.objects.create(title=f"ทำจ่ายใบสั่งซื้อ #{po.code}", amount=balance, date=timezone.now().date(), note=f"จ่ายให้ร้าน {po.supplier.name if po.supplier else ''}")
            messages.success(request, f"✅ ทำจ่ายบิล {po.code} และลงบันทึกรายจ่ายเรียบร้อย")

        elif task_type == 'solar_po_payments':
            po = get_object_or_404(SolarPurchaseOrder, id=item_id)

            balance = float(po.total_amount)

            po.payment_status = 'PAID'
            po.save()

            supplier_name = po.supplier.name if po.supplier else po.supplier_name_free_text
            Expense.objects.create(
                title=f"ทำจ่ายใบสั่งซื้อโซล่าเซลล์ #{po.code}",
                amount=balance,
                date=timezone.now().date(),
                note=f"จ่ายให้ร้าน {supplier_name}"
            )
            messages.success(request, f"✅ ทำจ่ายบิล {po.code} และลงบันทึกรายจ่ายเข้าระบบเรียบร้อย")

    return redirect('accounting_verification_hub', task_type=task_type)

# ==========================================
# 📊 กระดานกระทบยอดบัญชีราย Job (Commission Reconciliation Board)
# ==========================================
@login_required
def commission_recon_board(request):
    # เช็คสิทธิ์เฉพาะฝ่ายบัญชีหรือผู้บริหาร
    is_accounting = False
    if request.user.is_superuser:
        is_accounting = True
    elif hasattr(request.user, 'employee') and request.user.employee:
        dept = getattr(request.user.employee.department, 'name', '')
        if 'บัญชี' in dept or 'Account' in dept or 'บริหาร' in dept: is_accounting = True

    if not is_accounting:
        messages.error(request, "❌ หน้าต่างนี้สงวนสิทธิ์เฉพาะระดับบริหารและฝ่ายบัญชีเท่านั้น")
        return redirect('dashboard')

    tab = request.GET.get('tab', 'knockdown')
    search_q = request.GET.get('search_q', '').strip()
    status_dep = request.GET.get('status_dep', '')
    status_inv = request.GET.get('status_inv', '')

    # 🌟 [NEW] ดักจับค่าวันที่ 🌟
    date_range = request.GET.get('date_range', '').strip()
    start_date = None
    end_date = None
    if date_range:
        try:
            from datetime import datetime
            d_parts = date_range.split(' - ')
            start_date = datetime.strptime(d_parts[0].strip(), "%d/%m/%Y").date()
            end_date = datetime.strptime(d_parts[1].strip(), "%d/%m/%Y").date()
        except:
            pass

    data_list = []

    if tab == 'knockdown':
        from manufacturing.models import ProductionOrder
        from sales.models import Invoice, CommissionTicket
        from django.db.models import Q

        jobs_query = ProductionOrder.objects.select_related('quotation_ref').order_by('-id')
        if search_q:
            jobs_query = jobs_query.filter(
                Q(code__icontains=search_q) |
                Q(quotation_ref__code__icontains=search_q) |
                Q(quotation_ref__invoice__code__icontains=search_q)
            )

        # 🌟 [NEW] กรองข้อมูลช่วงเวลา (ใช้ start_date ของใบสั่งผลิต) 🌟
        if start_date and end_date:
            jobs_query = jobs_query.filter(start_date__gte=start_date, start_date__lte=end_date)

        jobs = jobs_query[:100]

        for job in jobs:
            # (โค้ดเดิมด้านล่างปล่อยไว้เหมือนเดิมครับ...)
            qt = job.quotation_ref
            inv = Invoice.objects.filter(quotation_ref=qt).first() if qt else None
            t2 = CommissionTicket.objects.filter(quotation_ref=qt, ticket_type='2%').first() if qt else None
            t3 = CommissionTicket.objects.filter(invoice_ref=inv, ticket_type='3%').first() if inv else None

            # 🌟 [FIXED] ลอจิกการกรองสถานะที่แม่นยำขึ้น 🌟
            if status_dep == 'AVAILABLE':
                if not ((t2 and t2.status == 'AVAILABLE') or (not t2 and qt and qt.is_deposit_paid)): continue
            elif status_dep == 'CLAIMING':
                if not (t2 and t2.status == 'CLAIMING'): continue
            elif status_dep == 'PAID':
                if not (t2 and t2.status == 'PAID'): continue
            # หากเลือก HIDDEN ให้ข้ามการกรอง t2 ไปเลย

            if status_inv == 'AVAILABLE':
                if not ((t3 and t3.status == 'AVAILABLE') or (not t3 and inv and inv.status == 'PAID')): continue
            elif status_inv == 'CLAIMING':
                if not (t3 and t3.status == 'CLAIMING'): continue
            elif status_inv == 'PAID':
                if not (t3 and t3.status == 'PAID'): continue
            # หากเลือก HIDDEN ให้ข้ามการกรอง t3 ไปเลย


            # 🌟 [FIXED] ลอจิกสถานะบัญชีรวมแบบ Linear (เช็คจากซ้ายไปขวา) 🌟
            fin_status = 'WAITING_DEPOSIT'
            if qt and qt.is_deposit_paid:
                if not t2 or t2.status != 'PAID':
                    fin_status = 'DEPOSIT_PAID' # ติดล็อกที่ 1: รอจ่ายคอมฯ 2%
                elif not inv or inv.status != 'PAID':
                    fin_status = 'WAITING_INV'  # ผ่าน 2% มาแล้ว -> รอเงินปิดบิล
                elif not t3 or t3.status != 'PAID':
                    fin_status = 'INV_PAID'     # ได้เงินปิดบิลแล้ว -> รอจ่ายคอมฯ ตามใบขาย
                else:
                    fin_status = 'CLEARED'      # จบกระบวนการ 100%

            data_list.append({
                'job_code': job.code,
                'customer_name': job.customer_name or (qt.customer.name if qt and qt.customer else '-'),
                'qt': qt, 'inv': inv, 't2': t2, 't3': t3, 'fin_status': fin_status
            })

    elif tab == 'solar':
        from solar_jobs.models import SolarJob
        from solar_sales.models import SolarInvoice, SolarCommissionTicket
        from django.db.models import Q

        jobs_query = SolarJob.objects.select_related('quotation_ref', 'customer').order_by('-id')
        if search_q:
            jobs_query = jobs_query.filter(
                Q(code__icontains=search_q) |
                Q(quotation_ref__code__icontains=search_q) |
                Q(quotation_ref__solarinvoice__code__icontains=search_q)
            )

        # 🌟 [NEW] กรองข้อมูลช่วงเวลา (ใช้ created_at ของใบงานโซล่า) 🌟
        if start_date and end_date:
            jobs_query = jobs_query.filter(created_at__date__gte=start_date, created_at__date__lte=end_date)

        jobs = jobs_query[:100]

        for job in jobs:
            qt = job.quotation_ref
            inv = SolarInvoice.objects.filter(quotation_ref=qt).first() if qt else None
            t2 = SolarCommissionTicket.objects.filter(quotation_ref=qt, ticket_type='2%').first() if qt else None
            t13 = SolarCommissionTicket.objects.filter(invoice_ref=inv, ticket_type='13.5%').first() if inv else None

            # 🌟 [FIXED] ลอจิกการกรองสถานะที่แม่นยำขึ้น 🌟
            if status_dep == 'AVAILABLE':
                if not ((t2 and t2.status == 'AVAILABLE') or (not t2 and qt and qt.is_deposit_paid)): continue
            elif status_dep == 'CLAIMING':
                if not (t2 and t2.status == 'CLAIMING'): continue
            elif status_dep == 'PAID':
                if not (t2 and t2.status == 'PAID'): continue

            if status_inv == 'AVAILABLE':
                if not ((t13 and t13.status == 'AVAILABLE') or (not t13 and inv and inv.status == 'PAID')): continue
            elif status_inv == 'CLAIMING':
                if not (t13 and t13.status == 'CLAIMING'): continue
            elif status_inv == 'PAID':
                if not (t13 and t13.status == 'PAID'): continue

            # 🌟 [FIXED] ลอจิกสถานะบัญชีรวมแบบ Linear (เช็คจากซ้ายไปขวา) 🌟
            fin_status = 'WAITING_DEPOSIT'
            if qt and qt.is_deposit_paid:
                if not t2 or t2.status != 'PAID':
                    fin_status = 'DEPOSIT_PAID' # ติดล็อกที่ 1: รอจ่ายคอมฯ 2%
                elif not inv or inv.status != 'PAID':
                    fin_status = 'WAITING_INV'  # ผ่าน 2% มาแล้ว -> รอเงินปิดบิล
                elif not t13 or t13.status != 'PAID':
                    fin_status = 'INV_PAID'     # ได้เงินปิดบิลแล้ว -> รอจ่ายคอมฯ ตามใบขาย
                else:
                    fin_status = 'CLEARED'      # จบกระบวนการ 100%

            data_list.append({
                'job_code': job.code,
                'customer_name': job.customer.name if job.customer else '-',
                'qt': qt, 'inv': inv, 't2': t2, 't3': t13, 'fin_status': fin_status
            })

    context = {'tab': tab, 'data_list': data_list}
    return render(request, 'accounting/commission_recon.html', context)

# ==========================================
# 🌟 [UPDATED] ศูนย์รวมทำจ่ายใบคุมรวมค่าใช้จ่ายตามใบงาน (JOB Expenses) 🌟
# ==========================================
from manufacturing.models import MasterExpenseClaim

@login_required
def accounting_job_expense_hub(request):
    # เช็คสิทธิ์บัญชี
    is_accounting = False
    if request.user.is_superuser:
        is_accounting = True
    elif hasattr(request.user, 'employee') and request.user.employee:
        dept = request.user.employee.department.name if request.user.employee.department else ''
        if 'บัญชี' in dept or 'Account' in dept: is_accounting = True

    if not is_accounting:
        messages.error(request, "❌ หน้าต่างนี้สงวนสิทธิ์เฉพาะเจ้าหน้าที่ฝ่ายบัญชีเท่านั้น")
        return redirect('dashboard')

    # 🌟 [NEW] รับพารามิเตอร์ tab เพื่อกรองใบคุม
    tab = request.GET.get('tab', 'pending')

    if tab == 'paid':
        # ดึงประวัติที่จ่ายแล้ว (PAID) เรียงตามวันที่จ่าย
        claims = MasterExpenseClaim.objects.filter(status='PAID').prefetch_related(
            'labor_items', 'aircon_items', 'other_items'
        ).order_by('-paid_at', '-created_at')
    else:
        # ดึงคิวงานปัจจุบัน (PENDING) เรียงตามวันที่ตั้งเบิก
        claims = MasterExpenseClaim.objects.filter(status='PENDING').prefetch_related(
            'labor_items', 'aircon_items', 'other_items'
        ).order_by('created_at')

    return render(request, 'accounting/job_expense_hub.html', {
        'claims': claims,
        'tab': tab
    })

@login_required
@transaction.atomic
def pay_job_expense_claim(request, claim_id):
    claim = get_object_or_404(MasterExpenseClaim, pk=claim_id)

    if request.method == 'POST' and 'transfer_slip' in request.FILES:
        # 1. รับสลิปและอัปเดตใบคุมรวมเป็น PAID
        claim.transfer_slip = request.FILES['transfer_slip']
        claim.status = 'PAID'
        claim.paid_at = timezone.now()
        claim.save()

        # 2. 🌟 ความฉลาดของระบบ: สั่งอัปเดตบิลย่อยทั้งหมดให้กลายเป็น PAID โดยอัตโนมัติ 🌟
        claim.labor_items.update(status='PAID', paid_at=timezone.now())
        claim.aircon_items.update(status='PAID', paid_at=timezone.now())
        claim.other_items.update(status='PAID', paid_at=timezone.now())

        # 3. สร้างรายจ่ายลงบัญชีให้อัตโนมัติ
        emp_name = claim.requester.first_name if claim.requester else "พนักงาน"
        Expense.objects.create(
            title=f"จ่ายค่าเบิกเงินหน้างาน (ใบคุม: {claim.code}) - {emp_name}",
            amount=claim.total_amount,
            date=timezone.now().date(),
            note=f"โอนเข้าบัญชี {claim.get_bank_name_display()} {claim.bank_account_number} ({claim.bank_account_name})"
        )

        messages.success(request, f"✅ บัญชีทำรายการโอนเงินยอด {claim.total_amount:,.2f} บาท สำเร็จ! ระบบอัปเดตป้ายสีเขียวให้ตาราง Master Job Report อัตโนมัติแล้ว")

    return redirect('accounting_job_expense_hub')

@login_required
def accounting_job_expense_detail(request, claim_id):
    # เช็คสิทธิ์บัญชี
    is_accounting = False
    if request.user.is_superuser:
        is_accounting = True
    elif hasattr(request.user, 'employee') and request.user.employee:
        dept = request.user.employee.department.name if request.user.employee.department else ''
        if 'บัญชี' in dept or 'Account' in dept: is_accounting = True

    if not is_accounting:
        messages.error(request, "❌ หน้าต่างนี้สงวนสิทธิ์เฉพาะเจ้าหน้าที่ฝ่ายบัญชีเท่านั้น")
        return redirect('dashboard')

    # ดึงข้อมูลใบคุม พร้อมบิลย่อยทั้งหมด
    claim = get_object_or_404(MasterExpenseClaim.objects.prefetch_related(
        'labor_items', 'aircon_items', 'other_items'
    ), pk=claim_id)

    return render(request, 'accounting/job_expense_detail.html', {
        'claim': claim
    })

# ==========================================
# 🌟 [NEW] ระบบตรวจสอบและทำจ่ายใบสั่งซื้อ (PO Payment Voucher) 🌟
# ==========================================
from purchasing.models import PurchaseOrder, PurchaseOrderPayment
from solar_purchasing.models import SolarPurchaseOrder, SolarPurchaseOrderPayment

@login_required
def accounting_po_payment_detail(request, system_type, po_id):
    # ตรวจสอบสิทธิ์ฝ่ายบัญชี
    is_accounting = False
    if request.user.is_superuser:
        is_accounting = True
    elif hasattr(request.user, 'employee') and request.user.employee:
        dept = request.user.employee.department.name if request.user.employee.department else ''
        if 'บัญชี' in dept or 'Account' in dept: is_accounting = True

    if not is_accounting:
        messages.error(request, "❌ หน้าต่างนี้สงวนสิทธิ์เฉพาะเจ้าหน้าที่ฝ่ายบัญชีเท่านั้น")
        return redirect('dashboard')

    # ดึงข้อมูลใบสั่งซื้อตามระบบที่ระบุ
    if system_type == 'knockdown':
        po = get_object_or_404(PurchaseOrder, id=po_id)
        supplier_name = po.supplier.name if po.supplier else 'ไม่ระบุ'
    elif system_type == 'solar':
        po = get_object_or_404(SolarPurchaseOrder, id=po_id)
        supplier_name = po.supplier.name if po.supplier else getattr(po, 'supplier_name_free_text', 'ไม่ระบุ')
    else:
        messages.error(request, "❌ ไม่พบระบบที่ระบุ")
        return redirect('accounting_dashboard')

    # เช็คยอดเงินที่จ่ายไปแล้ว
    payments = po.payments.all()
    total_paid = payments.aggregate(Sum('amount'))['amount__sum'] or 0
    balance = float(po.total_amount) - float(total_paid)

    context = {
        'po': po,
        'system_type': system_type,
        'supplier_name': supplier_name,
        'payments': payments,
        'total_paid': total_paid,
        'balance': balance,
    }
    return render(request, 'accounting/po_payment_detail.html', context)


@login_required
@transaction.atomic
def accounting_po_payment_submit(request, system_type, po_id):
    if request.method == 'POST':
        # รับค่าจากฟอร์ม
        amount_str = request.POST.get('amount', '0').replace(',', '')
        try: amount = float(amount_str)
        except ValueError: amount = 0

        payment_method = request.POST.get('payment_method', 'โอนเงินผ่านธนาคาร')
        reference_no = request.POST.get('reference_no', '')
        note = request.POST.get('note', '')
        slip_image = request.FILES.get('slip_image')

        if amount <= 0:
            messages.error(request, "❌ ยอดเงินต้องมากกว่า 0 บาท")
            return redirect('accounting_po_payment_detail', system_type=system_type, po_id=po_id)

        # 🌟 แยกระบบบันทึกข้อมูล
        if system_type == 'knockdown':
            po = get_object_or_404(PurchaseOrder, id=po_id)
            supplier_name = po.supplier.name if po.supplier else ''

            # บันทึกประวัติและสร้างใบคุม (PV) ลงตาราง
            payment_record = PurchaseOrderPayment.objects.create(
                po=po, amount=amount, payment_method=payment_method,
                reference_no=reference_no, note=note, slip_image=slip_image
            )

            # อัปเดตสถานะบิล
            total_paid = po.payments.aggregate(Sum('amount'))['amount__sum'] or 0
            if float(total_paid) >= float(po.total_amount):
                po.payment_status = 'PAID'
            else:
                po.payment_status = 'DEPOSIT'
            po.save()

            # ลงบันทึกรายจ่าย (Expense) อัตโนมัติ
            Expense.objects.create(
                title=f"ทำจ่ายใบสั่งซื้อ น็อคดาวน์ #{po.code} (PV: {payment_record.pv_code})",
                amount=amount, date=timezone.now().date(),
                note=f"จ่ายให้ร้าน {supplier_name} - {note}"
            )

            hub_url = 'po_payments'

        elif system_type == 'solar':
            po = get_object_or_404(SolarPurchaseOrder, id=po_id)
            supplier_name = po.supplier.name if po.supplier else getattr(po, 'supplier_name_free_text', '')

            # บันทึกประวัติและสร้างใบคุม (PV) ลงตาราง
            payment_record = SolarPurchaseOrderPayment.objects.create(
                po=po, amount=amount, payment_method=payment_method,
                note=note, slip_image=slip_image
            )

            # อัปเดตสถานะบิล
            total_paid = po.payments.aggregate(Sum('amount'))['amount__sum'] or 0
            if float(total_paid) >= float(po.total_amount):
                po.payment_status = 'PAID'
            else:
                po.payment_status = 'DEPOSIT'
            po.save()

            # ลงบันทึกรายจ่าย (Expense) อัตโนมัติ
            Expense.objects.create(
                title=f"ทำจ่ายใบสั่งซื้อ โซล่าเซลล์ #{po.code} (PV: {payment_record.pv_code})",
                amount=amount, date=timezone.now().date(),
                note=f"จ่ายให้ร้าน {supplier_name} - {note}"
            )

            hub_url = 'solar_po_payments'

        messages.success(request, f"✅ ออกใบคุมจ่ายเลขที่ {payment_record.pv_code} พร้อมโอนเงิน {amount:,.2f} บาท สำเร็จ! (ระบบลงบัญชีรายจ่ายให้อัตโนมัติแล้ว)")
        return redirect('accounting_verification_hub', task_type=hub_url)

    return redirect('accounting_dashboard')

# ==========================================
# 🌟 [NEW] รายงานประวัติการจ่ายเงินค่าวัตถุดิบ (PO Payment Report) 🌟
# ==========================================
@login_required
def accounting_po_payment_report(request):
    # เช็คสิทธิ์บัญชีและผู้บริหาร
    is_authorized = False
    if request.user.is_superuser:
        is_authorized = True
    elif hasattr(request.user, 'employee') and request.user.employee:
        dept = request.user.employee.department.name if request.user.employee.department else ''
        if 'บัญชี' in dept or 'Account' in dept or 'บริหาร' in dept or 'Executive' in dept:
            is_authorized = True

    if not is_authorized:
        messages.error(request, "❌ หน้าต่างนี้สงวนสิทธิ์เฉพาะระดับบริหารและฝ่ายบัญชีเท่านั้น")
        return redirect('dashboard')

    # รับค่า Tab ปัจจุบัน (ค่าเริ่มต้นคือ knockdown)
    tab = request.GET.get('tab', 'knockdown')

    if tab == 'knockdown':
        # ดึงประวัติการจ่ายเงินจากตาราง PurchaseOrderPayment
        payments = PurchaseOrderPayment.objects.select_related('po', 'po__supplier').order_by('-created_at')
    else:
        # ดึงประวัติการจ่ายเงินจากตาราง SolarPurchaseOrderPayment
        payments = SolarPurchaseOrderPayment.objects.select_related('po', 'po__supplier').order_by('-created_at')

    context = {
        'tab': tab,
        'payments': payments,
    }
    return render(request, 'accounting/po_payment_report.html', context)

# ==========================================
# 🌟 [NEW] พิมพ์ใบสำคัญจ่าย (Payment Voucher - A4) 🌟
# ==========================================
from master_data.models import CompanyInfo

@login_required
def accounting_print_pv(request, system_type, pv_id):
    # เช็คสิทธิ์เฉพาะบัญชีหรือผู้บริหาร
    is_authorized = False
    if request.user.is_superuser:
        is_authorized = True
    elif hasattr(request.user, 'employee') and request.user.employee:
        dept = request.user.employee.department.name if request.user.employee.department else ''
        if 'บัญชี' in dept or 'Account' in dept or 'บริหาร' in dept or 'Executive' in dept:
            is_authorized = True

    if not is_authorized:
        messages.error(request, "❌ ไม่มีสิทธิ์เข้าถึงหน้าพิมพ์เอกสาร")
        return redirect('dashboard')

    company = CompanyInfo.objects.first()

    if system_type == 'knockdown':
        payment = get_object_or_404(PurchaseOrderPayment.objects.select_related('po', 'po__supplier', 'po__buyer'), pk=pv_id)
        supplier_name = payment.po.supplier.name if payment.po.supplier else "ไม่ระบุ"
    elif system_type == 'solar':
        payment = get_object_or_404(SolarPurchaseOrderPayment.objects.select_related('po', 'po__supplier', 'po__buyer'), pk=pv_id)
        supplier_name = payment.po.supplier.name if payment.po.supplier else getattr(payment.po, 'supplier_name_free_text', "ไม่ระบุ")
    else:
        messages.error(request, "❌ ไม่พบระบบที่ระบุ")
        return redirect('accounting_po_payment_report')

    context = {
        'company': company,
        'payment': payment,
        'system_type': system_type,
        'supplier_name': supplier_name,
    }
    return render(request, 'accounting/po_payment_pv_print.html', context)