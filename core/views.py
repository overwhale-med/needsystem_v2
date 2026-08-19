from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, F
import datetime

# Import เพื่อนบ้าน
from sales.models import POSOrder
from inventory.models import Product
from purchasing.models import PurchaseOrder
from accounting.models import Income, Expense

# 🌟 [FIXED] แก้ชื่อ Model เป็น SolarSurveyJob ให้ตรงกับในฐานข้อมูล
from solar_sales.models import SolarSurveyJob 

@login_required
def dashboard(request):
    today = datetime.date.today()
    
    # 1. ยอดขายวันนี้
    sales_today = POSOrder.objects.filter(created_at__date=today).aggregate(Sum('total_amount'))['total_amount__sum'] or 0
    
    # 2. สินค้าใกล้หมด
    low_stock_count = Product.objects.filter(stock_qty__lte=F('min_level'), is_active=True).count()
    
    # 3. PO รอรับของ
    pending_po_count = PurchaseOrder.objects.filter(status='ORDERED').count()
    
    # 4. การเงินเดือนนี้
    current_month = today.month
    current_year = today.year
    income_month = Income.objects.filter(date__month=current_month, date__year=current_year).aggregate(Sum('amount'))['amount__sum'] or 0
    expense_month = Expense.objects.filter(date__month=current_month, date__year=current_year).aggregate(Sum('amount'))['amount__sum'] or 0
    profit_month = income_month - expense_month

    user_groups = list(request.user.groups.values_list('name', flat=True))

    # 🌟 5. Logic เช็กสิทธิ์ฝ่ายบัญชี (อ่านจากโปรไฟล์พนักงาน) 🌟
    is_accounting = False
    is_accounting_manager = False
    
    # ตัวแปรเก็บจำนวนใบงานของช่างโซล่า
    pending_solar_surveys = 0 
    
    if hasattr(request.user, 'employee') and request.user.employee:
        emp = request.user.employee
        dept_name = emp.department.name if emp.department else ''
        rank = emp.business_rank if emp.business_rank else ''
        
        # เช็กว่าเป็นพนักงานบัญชีหรือไม่
        if 'บัญชี' in dept_name or 'Accounting' in dept_name:
            is_accounting = True
            # เช็กว่าเป็นระดับหัวหน้าหรือไม่
            if rank in ['Manager', 'Executive', 'Director', 'ผู้จัดการ']:
                is_accounting_manager = True
                
        # 🌟 [FIXED] เช็กว่าเป็นทีมช่างโซล่า และดึงงานด้วย Model ที่ถูกต้อง (สถานะ COMPLETED)
        if 'ช่าง' in dept_name or 'ผลิต' in dept_name or 'โซล่า' in dept_name:
            pending_solar_surveys = SolarSurveyJob.objects.filter(surveyor=emp).exclude(status='COMPLETED').count()

    context = {
        'sales_today': sales_today,
        'low_stock_count': low_stock_count,
        'pending_po_count': pending_po_count,
        'income_month': income_month,
        'expense_month': expense_month,
        'profit_month': profit_month,
        'user_groups': user_groups,
        'is_accounting': is_accounting,
        'is_accounting_manager': is_accounting_manager,
        'pending_solar_surveys': pending_solar_surveys,
    }
    return render(request, 'core/dashboard.html', context)