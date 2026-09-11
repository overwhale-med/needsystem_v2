from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum
from django.utils import timezone
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

    # 1. คำนวณรายรับ-รายจ่าย เฉพาะเดือนปัจจุบัน
    incomes = Income.objects.filter(date__month=current_month, date__year=current_year)
    expenses = Expense.objects.filter(date__month=current_month, date__year=current_year)

    total_income = incomes.aggregate(Sum('amount'))['amount__sum'] or 0
    total_expense = expenses.aggregate(Sum('amount'))['amount__sum'] or 0
    net_balance = total_income - total_expense

    # 2. นับจำนวนงานด่วนข้ามแผนก (รวมมัดจำทั้งบ้านน็อคดาวน์และโซล่าเซลล์)
    pending_deposits_quotation = Quotation.objects.filter(is_deposit_paid=True, is_deposit_verified=False).count()
    pending_deposits_solar = SolarQuotation.objects.filter(is_deposit_paid=True, is_deposit_verified=False).count()
    pending_deposits = pending_deposits_quotation + pending_deposits_solar

    pending_sales = (
        Invoice.objects.filter(status='PENDING').count() +
        POSOrder.objects.filter(status='PENDING').count() +
        SolarInvoice.objects.filter(status='PENDING_VERIFY').count() # 🌟 [NEW] นับบิลโซล่าที่รอบัญชีตรวจ
    )

    # 🌟 [FIXED] แยกนับบิล PO น็อคดาวน์และโซล่าเซลล์ 🌟
    pending_purchases_normal = PurchaseOrder.objects.filter(status='APPROVED', payment_status__in=['PENDING', 'DEPOSIT']).count()
    pending_purchases_solar = SolarPurchaseOrder.objects.filter(status='APPROVED', payment_status__in=['PENDING', 'DEPOSIT']).count()
    pending_purchases = pending_purchases_normal + pending_purchases_solar

    pending_logistics = LogisticsClaim.objects.filter(status='PENDING').count()
    pending_blueprints = BlueprintClaim.objects.filter(status='PENDING').count()

    total_pending_payments = pending_purchases + pending_logistics + pending_blueprints

    # 3. ดึงรายการเคลื่อนไหวล่าสุด 10 รายการ
    recent_incomes = list(Income.objects.all().order_by('-date', '-id')[:5])
    recent_expenses = list(Expense.objects.all().order_by('-date', '-id')[:5])

    for i in recent_incomes: i.type = 'income'
    for e in recent_expenses: e.type = 'expense'

    recent_transactions = sorted(recent_incomes + recent_expenses, key=lambda x: x.date, reverse=True)[:10]

    context = {
        'total_income': total_income, 'total_expense': total_expense, 'net_balance': net_balance,
        'pending_deposits': pending_deposits, 'pending_sales': pending_sales,

        # 🌟 [FIXED] ส่งตัวแปรแยกกันไปแสดงผลที่หน้าเว็บ 🌟
        'pending_purchases_normal': pending_purchases_normal,
        'pending_purchases_solar': pending_purchases_solar,

        'pending_logistics': pending_logistics,
        'pending_blueprints': pending_blueprints, 'total_pending_payments': total_pending_payments,
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
        # ดึงมัดจำทั้ง 2 ระบบมารวมกันในหน้าตรวจสอบของบัญชี
        q_list = list(Quotation.objects.filter(is_deposit_paid=True, is_deposit_verified=False))
        solar_list = list(SolarQuotation.objects.filter(is_deposit_paid=True, is_deposit_verified=False))

        # เพิ่มป้ายกำกับแยกระบบให้บัญชีเห็นชัดเจน
        for item in q_list: item.system_type = 'quotation'
        for item in solar_list: item.system_type = 'solar'

        context['items'] = sorted(q_list + solar_list, key=lambda x: x.date, reverse=True)
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
                Income.objects.create(title=f"รับมัดจำใบเสนอราคาโซล่า #{qt.code}", amount=qt.deposit_amount, date=timezone.now().date(), note="อนุมัติโดยฝ่ายบัญชี")
                messages.success(request, f"✅ ยืนยันรับมัดจำโซล่า {qt.code} เข้าสู่ระบบบัญชีเรียบร้อย")
            else:
                qt = get_object_or_404(Quotation, id=item_id)
                qt.is_deposit_verified = True
                qt.save()
                Income.objects.create(title=f"รับมัดจำใบเสนอราคา #{qt.code}", amount=qt.deposit_amount, date=timezone.now().date(), note="อนุมัติโดยฝ่ายบัญชี")
                messages.success(request, f"✅ ยืนยันรับมัดจำ {qt.code} เข้าสู่ระบบบัญชีเรียบร้อย")

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
                messages.success(request, f"✅ ยืนยันรับชำระเงินบิลโซล่า {inv.code} และลงบันทึกรายรับเรียบร้อย")
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