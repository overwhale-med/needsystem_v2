import math
import datetime
from decimal import Decimal, ROUND_DOWN
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.db.models import Max, Sum, Q

from sales.models import Invoice, POSOrder
from hr.models import CompanySalesTarget, SalesGroup, Employee, CommissionLog, FundTransaction
from manufacturing.models import ProductionOrder
from master_data.models import CompanyInfo

def parse_thai_date(date_str):
    if not date_str: return None
    try: return parse_date(date_str)
    except: pass
    try:
        day, month, year = map(int, date_str.split('/'))
        return datetime.date(year, month, day)
    except: return None

def process_commission_logic(sale_amount, seller, sale_ref_id):
    now = timezone.now()
    sale_amount = Decimal(str(sale_amount))
    target, _ = CompanySalesTarget.objects.get_or_create(year=now.year, month=now.month)
    target.current_sales += sale_amount
    if target.current_sales >= target.target_amount:
        target.is_unlocked = True
    target.save()

    exec_group = SalesGroup.objects.filter(group_type='EXECUTIVE').first()
    if exec_group:
        exec_pool_amount = sale_amount * (exec_group.commission_rate / Decimal('100'))
        executives = Employee.objects.filter(sales_group=exec_group)
        if executives.exists():
            exact_share = exec_pool_amount / Decimal(str(executives.count()))
            share_per_head = exact_share.quantize(Decimal('0.00'), rounding=ROUND_DOWN)
            remainder = exec_pool_amount - (share_per_head * Decimal(str(executives.count())))
            for ex in executives:
                CommissionLog.objects.create(recipient=ex, source_employee=seller, level=1, amount=share_per_head, sale_ref_id=sale_ref_id)
            if remainder > 0:
                exec_group.fund_balance += remainder
                exec_group.save()
                FundTransaction.objects.create(group=exec_group, transaction_type='IN', amount=remainder, description=f"ปัดเศษเข้าสำรองบริหาร จากบิล {sale_ref_id}")

    if not seller or not seller.sales_group: return
    group = seller.sales_group

    total_group_comm = sale_amount * (group.commission_rate / Decimal('100'))
    fund_to_add = Decimal('0.00')

    if group.group_type == 'TEAM':
        exact_leader_share = total_group_comm * (group.share_leader / Decimal('100'))
        leader_share = exact_leader_share.quantize(Decimal('0.00'), rounding=ROUND_DOWN)
        fund_to_add += (exact_leader_share - leader_share)
        leader = Employee.objects.filter(sales_group=group, group_role='LEADER').first()
        if leader:
            CommissionLog.objects.create(recipient=leader, source_employee=seller, level=1, amount=leader_share, sale_ref_id=sale_ref_id)
        else:
            fund_to_add += leader_share

        exact_l1_share = total_group_comm * (group.share_level1 / Decimal('100'))
        l1_members = Employee.objects.filter(sales_group=group, group_role='LEVEL1')
        if l1_members.exists():
            exact_split = exact_l1_share / Decimal(str(l1_members.count()))
            split = exact_split.quantize(Decimal('0.00'), rounding=ROUND_DOWN)
            remainder = exact_l1_share - (split * Decimal(str(l1_members.count())))
            fund_to_add += remainder
            for m in l1_members:
                CommissionLog.objects.create(recipient=m, source_employee=seller, level=2, amount=split, sale_ref_id=sale_ref_id)
        else:
            fund_to_add += exact_l1_share

        exact_l2_share = total_group_comm * (group.share_level2 / Decimal('100'))
        l2_members = Employee.objects.filter(sales_group=group, group_role='LEVEL2')
        if l2_members.exists():
            exact_split = exact_l2_share / Decimal(str(l2_members.count()))
            split = exact_split.quantize(Decimal('0.00'), rounding=ROUND_DOWN)
            remainder = exact_l2_share - (split * Decimal(str(l2_members.count())))
            fund_to_add += remainder
            for m in l2_members:
                CommissionLog.objects.create(recipient=m, source_employee=seller, level=3, amount=split, sale_ref_id=sale_ref_id)
        else:
            fund_to_add += exact_l2_share

        exact_fixed_fund_share = total_group_comm * (group.share_fund / Decimal('100'))
        fund_to_add += exact_fixed_fund_share

    elif group.group_type == 'INDEPENDENT':
        exact_fund_share = total_group_comm * (group.share_fund / Decimal('100'))
        exact_personal_share = total_group_comm - exact_fund_share
        personal_share = exact_personal_share.quantize(Decimal('0.00'), rounding=ROUND_DOWN)
        fund_to_add = exact_fund_share + (exact_personal_share - personal_share)
        CommissionLog.objects.create(recipient=seller, source_employee=seller, level=1, amount=personal_share, sale_ref_id=sale_ref_id)

    if fund_to_add > 0:
        group.fund_balance += fund_to_add
        group.save()
        FundTransaction.objects.create(group=group, transaction_type='IN', amount=fund_to_add, description=f"รับคอมฯและปัดเศษสตางค์ จากบิล {sale_ref_id}")

def get_next_document_number():
    now = timezone.now()
    thai_year = (now.year + 543) % 100
    prefix = f"DLN-{thai_year:02d}{now.strftime('%m')}"
    last_inv = Invoice.objects.filter(code__startswith=prefix).aggregate(Max('code'))['code__max']
    last_pos = POSOrder.objects.filter(code__startswith=prefix).aggregate(Max('code'))['code__max']
    max_seq = 0
    if last_inv:
        try: max_seq = max(max_seq, int(last_inv.split('-')[-1]))
        except: pass
    if last_pos:
        try: max_seq = max(max_seq, int(last_pos.split('-')[-1]))
        except: pass
    return f"{prefix}-{max_seq + 1:03d}"

def get_auto_delivery_date(qt):
    first_item = qt.items.first()
    total_qty = first_item.quantity if first_item else 1
    company_info = CompanyInfo.objects.first()
    max_quota = company_info.weekly_job_quota if company_info and company_info.weekly_job_quota else 25

    deposit_date = qt.deposit_date if qt.deposit_date else timezone.now().date()
    current_check_date = deposit_date
    weeks_pushed = 0

    while True:
        iso_year, iso_week, _ = current_check_date.isocalendar()
        check_cohort = f"{iso_year}-W{iso_week:02d}"
        total_qty_in_week = ProductionOrder.objects.filter(cohort_week=check_cohort, is_closed=False).aggregate(Sum('quantity'))['quantity__sum'] or 0

        if total_qty_in_week + total_qty <= max_quota:
            break
        weeks_pushed += 1
        current_check_date += datetime.timedelta(days=7)

    base_lead_time = 14 + (weeks_pushed * 7)
    delivery_start_date = deposit_date + datetime.timedelta(days=base_lead_time)
    days_to_monday = delivery_start_date.weekday()
    monday_of_delivery_week = delivery_start_date - datetime.timedelta(days=days_to_monday)

    return monday_of_delivery_week + datetime.timedelta(days=4)

def get_thai_baht_text(number):
    if number == 0: return "ศูนย์บาทถ้วน"
    number = round(float(number), 2)
    baht = math.floor(number)
    satang = int(round((number - baht) * 100))

    def read_num(n):
        if n == 0: return ""
        numbers = ["", "หนึ่ง", "สอง", "สาม", "สี่", "ห้า", "หก", "เจ็ด", "แปด", "เก้า"]
        positions = ["", "สิบ", "ร้อย", "พัน", "หมื่น", "แสน", "ล้าน"]
        s = str(n)
        length = len(s)
        res = ""
        for i, digit in enumerate(s):
            val = int(digit)
            pos = length - i - 1
            if val == 0: continue
            if pos == 0 and val == 1 and length > 1: res += "เอ็ด"
            elif pos == 1 and val == 1: res += "สิบ"
            elif pos == 1 and val == 2: res += "ยี่สิบ"
            else: res += numbers[val] + positions[pos]
        return res

    res = ""
    if baht > 0: res += read_num(baht) + "บาท"
    if satang > 0: res += read_num(satang) + "สตางค์"
    else: res += "ถ้วน"
    return res

def get_target_employees(user):
    current_emp = getattr(user, 'employee', None)
    user_groups = list(user.groups.values_list('name', flat=True))

    if user.is_superuser: return Employee.objects.all(), "Admin View"
    elif current_emp:
        # 🌟 เช็กสิทธิ์บัญชี และผู้บริหาร จากสวิตช์ (Group) โดยตรง
        if 'Accounting_Team' in user_groups: return Employee.objects.all(), "Accounting View"
        if 'Manager_Team' in user_groups or 'Executive' in user_groups or 'Executive_Team' in user_groups: return Employee.objects.all(), "Manager View"

        # 🌟 [NEW] เลิกเดาคำ! เช็กสิทธิ์หัวหน้าสาขา จากสวิตช์ Supervisor_Team โดยตรง
        if 'Supervisor_Team' in user_groups:
            if current_emp.department: return Employee.objects.filter(department=current_emp.department), f"Team {current_emp.department.name}"
            else: return Employee.objects.filter(Q(id=current_emp.id) | Q(introducer=current_emp)), "Direct Team"
        else: return Employee.objects.filter(id=current_emp.id), "Self View"
    return Employee.objects.none(), "-"


def get_sales_queryset(model_class, user, target_employees):
    if user.is_superuser: return model_class.objects.all()
    user_groups = list(user.groups.values_list('name', flat=True))

    # 🌟 ถ้ามีสวิตช์ระดับบริหาร ให้ดึงข้อมูลทั้งหมดของแผนกขายมาแสดงได้
    if 'Accounting_Team' in user_groups or 'Manager_Team' in user_groups or 'Executive' in user_groups or 'Executive_Team' in user_groups:
        return model_class.objects.all()

    emp_ids = list(target_employees.values_list('id', flat=True))
    return model_class.objects.filter(employee_id__in=emp_ids)


def is_sales_authorized(user):
    if user.is_superuser: return True
    user_groups = list(user.groups.values_list('name', flat=True))
    # 🌟 [NEW] เพิ่ม Supervisor_Team และ Executive_Team เข้าไปในรายชื่อกลุ่มที่ได้รับอนุญาตให้เข้าระบบขายได้
    allowed_groups = ['Manager_Team', 'Executive', 'Executive_Team', 'Supervisor_Team', 'Knockdown_Sales_Team', 'Solar_Sales_Team', 'Accounting_Team', 'Control_Team']
    if any(group in user_groups for group in allowed_groups): return True
    return False