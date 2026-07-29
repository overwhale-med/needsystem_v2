from django.db import models
from django.utils import timezone
import datetime

from master_data.models import Customer
from hr.models import Employee
from solar_sales.models import SolarProduct

# 🌟 [FIXED] สร้างฐานข้อมูล "ทีมช่างรับเหมาติดตั้ง" (ช่างนอก)
class SubcontractorTeam(models.Model):
    name = models.CharField(max_length=150, unique=True, verbose_name="ชื่อทีมรับเหมา / ชื่อบริษัท")
    leader_name = models.CharField(max_length=100, blank=True, null=True, verbose_name="ชื่อหัวหน้าช่าง")
    phone = models.CharField(max_length=20, blank=True, null=True, verbose_name="เบอร์ติดต่อ")
    is_active = models.BooleanField(default=True, verbose_name="สถานะรับงาน")
    note = models.TextField(blank=True, verbose_name="หมายเหตุ / ความเชี่ยวชาญ")
    
    class Meta:
        verbose_name = "ทีมช่างรับเหมาโซล่า"
        verbose_name_plural = "ฐานข้อมูลทีมช่างรับเหมา"
        
    def __str__(self):
        return f"{self.name} (หัวหน้า: {self.leader_name or '-'})"

class SolarJob(models.Model):
    STATUS_CHOICES = [
        ('DRAFT', 'ร่าง (รอรับงาน)'),
        ('PREPARING', 'Center กำลังเตรียมของ/จัดช่าง'),
        ('IN_PROGRESS', 'กำลังดำเนินการติดตั้ง'),
        ('COMPLETED', 'ติดตั้งเสร็จสมบูรณ์'),
        ('CANCELLED', 'ยกเลิก')
    ]

    code = models.CharField(max_length=20, unique=True, verbose_name="เลขที่ใบสั่งงาน (Solar Job)")
    
    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, verbose_name="ลูกค้า")
    salesperson = models.ForeignKey(Employee, related_name='solar_sales_jobs', on_delete=models.SET_NULL, null=True, verbose_name="พนักงานขาย")
    package_sold = models.ForeignKey(SolarProduct, on_delete=models.SET_NULL, null=True, related_name='solar_jobs', verbose_name="แพ็กเกจที่ขาย (FG)")
    
    # 🌟 [FIXED] เปลี่ยนจาก Department เป็น SubcontractorTeam
    technician_team = models.ForeignKey(SubcontractorTeam, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="ทีมช่างติดตั้ง")
    labor_cost_budget = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="งบประมาณค่าช่าง (ที่ Center กำหนด)")
    
    start_date = models.DateField(null=True, blank=True, verbose_name="วันที่เริ่มงาน (dd/mm/yyyy)")
    expected_finish_date = models.DateField(null=True, blank=True, verbose_name="กำหนดเสร็จ (dd/mm/yyyy)")
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT', verbose_name="สถานะงาน")
    note = models.TextField(blank=True, verbose_name="รายละเอียด/หมายเหตุ")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "ใบสั่งงานโซล่า (Solar Job)"
        verbose_name_plural = "1. จัดการใบสั่งงานโซล่า"

    def __str__(self):
        return str(self.code)

    def save(self, *args, **kwargs):
        if not self.code:
            today = datetime.date.today()
            thai_year = (today.year + 543) % 100
            prefix = f"SOL-{thai_year:02d}{today.strftime('%m')}-"
            
            last_job = SolarJob.objects.filter(code__startswith=prefix).order_by('code').last()
            if last_job:
                try: seq = int(last_job.code.split('-')[-1]) + 1
                except ValueError: seq = 1
            else:
                seq = 1
            self.code = f"{prefix}{seq:03d}"
        super().save(*args, **kwargs)

    @property
    def total_material_cost(self):
        return sum(item.total_cost for item in self.materials.all())

    @property
    def total_job_cost(self):
        return self.total_material_cost + self.labor_cost_budget


class SolarJobMaterial(models.Model):
    job = models.ForeignKey(SolarJob, related_name='materials', on_delete=models.CASCADE)
    product = models.ForeignKey(SolarProduct, on_delete=models.PROTECT, verbose_name="วัตถุดิบ (RM)")
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=1, verbose_name="จำนวนที่เบิก")
    unit_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="ต้นทุนต่อหน่วย (ณ วันที่เบิก)")

    @property
    def total_cost(self):
        return self.quantity * self.unit_cost

    class Meta:
        verbose_name = "รายการเบิกวัตถุดิบโซล่า"
        verbose_name_plural = "รายการเบิกวัตถุดิบโซล่า"


class SolarExpense(models.Model):
    EXPENSE_TYPES = [
        ('SALES_TRAVEL', 'ค่าเดินทางสำรวจหน้างาน (เซลส์)'),
        ('TECH_TRAVEL', 'ค่าเดินทางติดตั้ง (ช่าง)'),
        ('TECH_LABOR', 'ค่าเบิกจ่ายค่าแรงติดตั้ง (ช่าง)'),
        ('OTHER', 'ค่าใช้จ่ายอื่นๆ')
    ]
    
    STATUS_CHOICES = [
        ('PENDING', 'รอตรวจสอบ'),
        ('APPROVED', 'บัญชีอนุมัติแล้ว'),
        ('REJECTED', 'ไม่อนุมัติ')
    ]

    job = models.ForeignKey(SolarJob, related_name='expenses', on_delete=models.CASCADE, verbose_name="อ้างอิงใบสั่งงาน (SOL)")
    requester = models.ForeignKey(Employee, on_delete=models.CASCADE, verbose_name="ผู้ตั้งเบิก")
    expense_type = models.CharField(max_length=20, choices=EXPENSE_TYPES, verbose_name="ประเภทค่าใช้จ่าย")
    
    description = models.CharField(max_length=255, verbose_name="รายละเอียดเพิ่มเติม")
    amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="จำนวนเงินที่เบิก")
    receipt_image = models.ImageField(upload_to='solar_expenses/%Y/%m/', null=True, blank=True, verbose_name="รูปสลิป/ใบเสร็จ")
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING', verbose_name="สถานะการอนุมัติ")
    approved_by = models.ForeignKey(Employee, related_name='approved_solar_expenses', on_delete=models.SET_NULL, null=True, blank=True, verbose_name="ผู้อนุมัติ (บัญชี)")
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "รายการตั้งเบิกโซล่า"
        verbose_name_plural = "2. รายการตั้งเบิกค่าใช้จ่าย"

    def __str__(self):
        return f"{self.job.code} - {self.get_expense_type_display()} ({self.amount} บาท)"