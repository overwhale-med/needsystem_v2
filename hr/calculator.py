from decimal import Decimal
from .models import Employee, CommissionLog  # ✅ เพิ่ม CommissionLog

# ==========================================
# ⚙️ ตั้งค่าแผนการจ่ายผลตอบแทน (Compensation Plan)
# ==========================================
COMMISSION_RATES = {
    0: Decimal('10.0'),  # 👤 ผู้ขาย (10%)
    1: Decimal('5.0'),   # 👑 แม่ทีม (5%)
    2: Decimal('3.0'),   # 👴 ปู่ทีม (3%)
    3: Decimal('1.0'),   # 👴 ทวดทีม (1%)
}

def calculate_network_commission(sale_amount, seller_employee, sale_ref="System-Auto"):
    """
    คำนวณค่าคอมมิชชั่นแบบ Multi-Level และบันทึกลง Database
    """
    results = []
    amount = Decimal(str(sale_amount))
    
    current_emp = seller_employee
    current_level = 0
    
    # 🔄 วนลูปจ่ายเงินตามชั้น
    while current_emp is not None and current_level in COMMISSION_RATES:
        
        rate = COMMISSION_RATES[current_level]
        commission_amt = amount * (rate / 100)
        
        if commission_amt > 0:
            # ✅ บันทึกลง Database
            log = CommissionLog.objects.create(
                recipient=current_emp,
                source_employee=seller_employee,
                level=current_level,
                amount=commission_amt,
                sale_ref_id=sale_ref
            )
            
            results.append(log)

        # ขยับขึ้นไปหา Upline
        current_emp = current_emp.introducer
        current_level += 1
        
    return results