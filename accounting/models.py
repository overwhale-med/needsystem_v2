from django.db import models
from django.utils import timezone

# ==========================================
# 1. หมวดหมู่ค่าใช้จ่าย (Expense Category)
# ==========================================
class ExpenseCategory(models.Model):
    name = models.CharField(max_length=100, verbose_name="ชื่อหมวดหมู่")
    
    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "1. หมวดหมู่ค่าใช้จ่าย"
        verbose_name_plural = "1. ตั้งค่าหมวดหมู่จ่าย"

# ==========================================
# 2. บันทึกรายจ่าย (Expense)
# ==========================================
class Expense(models.Model):
    title = models.CharField(max_length=200, verbose_name="รายการ")
    amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="จำนวนเงิน")
    category = models.ForeignKey(ExpenseCategory, on_delete=models.SET_NULL, null=True, verbose_name="หมวดหมู่")
    date = models.DateField(default=timezone.now, verbose_name="วันที่จ่าย")
    
    # อัปโหลดสลิป/บิล
    slip_image = models.ImageField(upload_to='expenses/', blank=True, null=True, verbose_name="รูปสลิป/ใบเสร็จ")
    note = models.TextField(blank=True, verbose_name="หมายเหตุ")

    class Meta:
        verbose_name = "2. บันทึกรายจ่าย"
        verbose_name_plural = "2. รายการรายจ่าย (Expenses)"

    def __str__(self):
        return f"{self.title} - {self.amount:,.2f}"

# ==========================================
# 3. บันทึกรายรับ (Income)
# ==========================================
class Income(models.Model):
    title = models.CharField(max_length=200, verbose_name="รายการ")
    amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="จำนวนเงิน")
    date = models.DateField(default=timezone.now, verbose_name="วันที่รับ")
    
    # เชื่อมโยงกับบิลขาย (Optional: เผื่ออยากรู้ว่ามาจากบิลไหน)
    from sales.models import POSOrder
    pos_order = models.ForeignKey(POSOrder, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="มาจากบิล POS")
    
    note = models.TextField(blank=True, verbose_name="หมายเหตุ")

    class Meta:
        verbose_name = "3. บันทึกรายรับ"
        verbose_name_plural = "3. รายการรายรับ (Incomes)"

    def __str__(self):
        return f"{self.title} - {self.amount:,.2f}"