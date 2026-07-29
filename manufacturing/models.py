from django.db import models
from django.utils import timezone
from inventory.models import Product
from hr.models import Employee
import datetime

# ==========================================
# 🌟 ตารางสำหรับเก็บข้อมูลหน้าร้าน (Sales Team) 🌟
# ==========================================
class Branch(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name="ชื่อสาขา (หน้าร้าน)")
    def __str__(self): return self.name

class Salesperson(models.Model):
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='salespersons', verbose_name="สาขาหน้าร้าน")
    name = models.CharField(max_length=100, verbose_name="ชื่อพนักงานขาย")
    def __str__(self): return f"{self.name} ({self.branch.name})"

# ==========================================
# 🌟 ตารางใหม่: สำหรับสถานที่ผลิต (โรงงาน / Factory) 🌟
# ==========================================
class MfgBranch(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name="ชื่อโรงงาน / สถานที่ผลิต")
    weekly_quota = models.IntegerField(default=10, verbose_name="โควตาการผลิต (หลัง/สัปดาห์)")

    class Meta:
        verbose_name = "โรงงาน / สถานที่ผลิต"
        verbose_name_plural = "ตั้งค่าโรงงานผลิต"
    def __str__(self): return self.name

# ==========================================
# 🌟 ตาราง: สำหรับระบบกระดานติดตามงาน 🌟
# ==========================================
class ProductionStatus(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name="สถานะการผลิตหน้างาน (แผนก)")
    sequence = models.IntegerField(default=99, verbose_name="ลำดับการแสดงผล")
    class Meta:
        ordering = ['sequence', 'id']
        verbose_name = "สถานะการผลิต"
        verbose_name_plural = "สถานะการผลิต"
    def __str__(self): return self.name

class ProductionTeam(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name="ชื่อทีมช่าง")
    class Meta:
        verbose_name = "ทีมช่างผลิต"
        verbose_name_plural = "ทีมช่างผลิต"
    def __str__(self): return self.name

class DeliveryStatus(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name="สถานะการจัดส่ง")
    class Meta:
        verbose_name = "สถานะการจัดส่ง"
        verbose_name_plural = "สถานะการจัดส่ง"
    def __str__(self): return self.name

class Transporter(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name="ทีมขนส่ง / บริษัทขนส่ง")
    driver_name = models.CharField(max_length=100, blank=True, verbose_name="ชื่อคนขับหลัก")
    vehicle_plate = models.CharField(max_length=50, blank=True, verbose_name="ทะเบียนรถ")

    # 🌟 ข้อมูลสำหรับการโอนเงินและเอกสาร 🌟
    address = models.TextField(blank=True, verbose_name="ที่อยู่บริษัท / คนขับ")
    bank_account = models.CharField(max_length=200, blank=True, verbose_name="เลขที่บัญชีธนาคาร (ระบุชื่อธนาคารด้วย)")
    id_card_image = models.ImageField(upload_to='transporter_docs/', null=True, blank=True, verbose_name="เอกสารใบขับขี่ / บัตรประชาชน")

    delivery_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, verbose_name="ค่าตอบแทนพื้นฐาน")

    class Meta:
        verbose_name = "ทีมขนส่ง"
        verbose_name_plural = "ทีมขนส่ง"

    def __str__(self): return self.name

# ==========================================
# 🌟 [NEW] ตาราง: ระบบตั้งเบิกค่ารถขนส่ง 🌟
# ==========================================
class LogisticsClaim(models.Model):
    code = models.CharField(max_length=20, unique=True, verbose_name="เลขที่ใบเบิก")
    transporter = models.ForeignKey(Transporter, on_delete=models.CASCADE, verbose_name="ทีมขนส่ง")
    total_jobs = models.IntegerField(default=0, verbose_name="จำนวนงานที่เบิก")
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="ยอดเงินรวม")
    status = models.CharField(max_length=20, choices=[('PENDING', 'รออนุมัติจ่าย'), ('PAID', 'จ่ายเงินแล้ว'), ('REJECTED', 'ไม่อนุมัติ')], default='PENDING', verbose_name="สถานะ")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="วันที่ตั้งเบิก")
    paid_at = models.DateTimeField(null=True, blank=True, verbose_name="วันที่จ่ายเงิน")

    class Meta:
        verbose_name = "ใบตั้งเบิกค่าขนส่ง"
        verbose_name_plural = "ใบตั้งเบิกค่าขนส่ง"

    def __str__(self): return self.code

    def save(self, *args, **kwargs):
        if not self.code:
            now = timezone.now()
            thai_year = (now.year + 543) % 100
            prefix = f"LC-{thai_year:02d}{now.strftime('%m')}"
            last = LogisticsClaim.objects.filter(code__startswith=prefix).order_by('code').last()
            seq = int(last.code.split('-')[-1]) + 1 if last else 1
            self.code = f"{prefix}-{seq:04d}"
        super().save(*args, **kwargs)

# ==========================================
# 🌟 [NEW] ตาราง: ระบบตั้งเบิกผลงานตรวจแบบแปลน 🌟
# ==========================================
class BlueprintClaim(models.Model):
    code = models.CharField(max_length=20, unique=True, verbose_name="เลขที่ใบตั้งเบิก")
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, verbose_name="พนักงานผู้ขอเบิก")
    total_jobs = models.IntegerField(default=0, verbose_name="จำนวนงานที่เบิก")
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="ยอดเงินรวม")
    status = models.CharField(max_length=20, choices=[('PENDING', 'รออนุมัติจ่าย'), ('PAID', 'จ่ายเงินแล้ว'), ('REJECTED', 'ไม่อนุมัติ')], default='PENDING', verbose_name="สถานะ")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="วันที่ตั้งเบิก")
    paid_at = models.DateTimeField(null=True, blank=True, verbose_name="วันที่จ่ายเงิน")

    class Meta:
        verbose_name = "ใบตั้งเบิกผลงานตรวจแบบ"
        verbose_name_plural = "ใบตั้งเบิกผลงานตรวจแบบ"

    def __str__(self): return self.code

    def save(self, *args, **kwargs):
        if not self.code:
            now = timezone.now()
            thai_year = (now.year + 543) % 100
            prefix = f"BC-{thai_year:02d}{now.strftime('%m')}"
            last = BlueprintClaim.objects.filter(code__startswith=prefix).order_by('code').last()
            seq = int(last.code.split('-')[-1]) + 1 if last else 1
            self.code = f"{prefix}-{seq:04d}"
        super().save(*args, **kwargs)

class BlueprintClaimSplit(models.Model):
    claim = models.ForeignKey(BlueprintClaim, on_delete=models.CASCADE, related_name='splits')
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, verbose_name="ผู้รับเงินส่วนแบ่ง")
    role_name = models.CharField(max_length=50, verbose_name="ตำแหน่งในทีม (ตอนเบิก)")
    percentage = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="เปอร์เซ็นต์ที่ได้")
    amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="ยอดเงินสุทธิ")

    class Meta:
        verbose_name = "ส่วนแบ่งใบเบิก"
        verbose_name_plural = "ส่วนแบ่งใบเบิก"

# ==========================================
# 1. สูตรการผลิต (Bill of Materials - BOM)
# ==========================================
class BOM(models.Model):
    product = models.OneToOneField(Product, on_delete=models.CASCADE, verbose_name="สินค้าสำเร็จรูป (FG)")
    name = models.CharField(max_length=200, verbose_name="ชื่อสูตร (เช่น สูตรมาตรฐาน)")
    labor_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, verbose_name="ค่าแรงประกอบ") # 🌟 [NEW] เพิ่มฟิลด์เก็บค่าแรงประกอบตามความต้องการผู้ใช้
    note = models.TextField(blank=True, verbose_name="หมายเหตุ")
    
    def __str__(self): return f"สูตรผลิต: {self.product.name}"

    class Meta:
        verbose_name = "1. สูตรการผลิต (BOM)"
        verbose_name_plural = "1. จัดการสูตรผลิต"

class BOMItem(models.Model):
    bom = models.ForeignKey(BOM, related_name='items', on_delete=models.CASCADE)
    raw_material = models.ForeignKey(Product, related_name='used_in_boms', on_delete=models.CASCADE, verbose_name="วัตถุดิบ (Raw Mat)")
    quantity = models.DecimalField(max_digits=10, decimal_places=4, verbose_name="จำนวนที่ใช้ (ต่อ 1 หน่วยผลิต)")
    def __str__(self): return f"{self.raw_material.name} ({self.quantity})"

# ==========================================
# 2. ใบสั่งผลิต (Production Order - JOB)
# ==========================================
class ProductionOrder(models.Model):
    STATUS_CHOICES = [
        ('NEW_JOB', '1. รอจ่ายงาน (New JOB)'),
        ('WAITING_BLUEPRINT', 'รอตรวจสอบแบบแปลน'),
        ('PLANNED', '2. ตรวจแบบแปลน / ดึงสูตร'),
        ('WAITING_MATERIALS', '3. รอสั่งซื้อวัตถุดิบ'),
        ('WAITING_INVENTORY', '4. รอเบิกวัตถุดิบ'),
        ('IN_PROGRESS', '5. กำลังผลิต'),
        ('WAITING_QC', 'รอตรวจสอบคุณภาพ (QC)'),
        ('REWORK', 'รอแก้ไขงาน (Rework)'),
        ('COMPLETED', '6. พร้อมจัดส่ง / เสร็จแล้ว (เข้าสต็อก)'),
        ('CANCELLED', 'ยกเลิก')
    ]

    DATE_APPROVAL_CHOICES = [
        ('NOT_REQUIRED', 'ไม่ต้องอนุมัติ'),
        ('PENDING', 'รออนุมัติวัน'),
        ('APPROVED', 'อนุมัติวันแล้ว'),
        ('REJECTED', 'ไม่อนุมัติ (ยึดตามระบบ)')
    ]

    code = models.CharField(max_length=20, unique=True, blank=True, verbose_name="เลขที่ใบสั่งผลิต (JOB)")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, verbose_name="สินค้าที่จะผลิต")
    quantity = models.IntegerField(default=1, verbose_name="จำนวนที่ผลิต (ตามใบเสนอราคา)")
    quotation_ref = models.ForeignKey('sales.Quotation', on_delete=models.SET_NULL, null=True, blank=True, related_name='production_orders', verbose_name="อ้างอิงใบเสนอราคา/มัดจำ")
    blueprint_file = models.FileField(upload_to='blueprints/%Y/%m/', null=True, blank=True, verbose_name="ไฟล์แบบแปลน (PDF/รูปภาพ)")

    start_date = models.DateField(default=timezone.now, verbose_name="วันที่เริ่มผลิต")
    finish_date = models.DateField(null=True, blank=True, verbose_name="วันที่เสร็จ (เข้าคลัง)")
    delivery_date = models.DateField(null=True, blank=True, verbose_name="กำหนดจัดส่งสินค้า")

    cohort_week = models.CharField(max_length=15, blank=True, null=True, verbose_name="สัปดาห์คิวผลิต (Cohort)")
    deadline_date = models.DateField(null=True, blank=True, verbose_name="เส้นตายจัดส่ง (SLA)")

    auto_calculated_date = models.DateField(null=True, blank=True, verbose_name="วันที่ระบบคำนวณ (Safe Date)")
    requested_date = models.DateField(null=True, blank=True, verbose_name="วันที่เซลส์ขอ (Requested Date)")
    date_approval_status = models.CharField(max_length=20, choices=DATE_APPROVAL_CHOICES, default='NOT_REQUIRED', verbose_name="สถานะการอนุมัติวัน")

    branch = models.ForeignKey(MfgBranch, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="สถานที่ผลิต / โรงงาน")
    salesperson = models.ForeignKey(Salesperson, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="พนักงานขาย")

    customer_name = models.CharField(max_length=200, blank=True, verbose_name="ชื่อลูกค้า / สถานที่ส่ง")
    completed_departments = models.ManyToManyField(ProductionStatus, blank=True, verbose_name="แผนกที่ดำเนินการเสร็จแล้ว")
    production_team = models.ForeignKey(ProductionTeam, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="ทีมช่างผลิต")
    delivery_status = models.ForeignKey(DeliveryStatus, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="สถานะจัดส่ง")
    transporter = models.ForeignKey(Transporter, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="ทีมขนส่ง")

    responsible_person = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, verbose_name="ผู้ควบคุมการผลิต")

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='NEW_JOB', verbose_name="สถานะระบบ")
    is_materials_ordered = models.BooleanField(default=False, verbose_name="สั่งซื้อวัตถุดิบแล้ว")

    blueprint_approved_by = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_blueprints', verbose_name="ผู้อนุมัติแบบแปลน")
    blueprint_approved_at = models.DateTimeField(null=True, blank=True, verbose_name="เวลาที่อนุมัติแบบแปลน")
    blueprint_claim = models.ForeignKey(BlueprintClaim, on_delete=models.SET_NULL, null=True, blank=True, related_name='production_orders', verbose_name="ใบตั้งเบิกผลงาน")

    rework_count = models.IntegerField(default=0, verbose_name="จำนวนครั้งที่ถูกตีกลับ (Rework)")

    qc_paint = models.BooleanField(default=False, verbose_name="1. งานเก็บสี")
    qc_internal = models.BooleanField(default=False, verbose_name="2. งานตรวจภายใน")
    qc_external = models.BooleanField(default=False, verbose_name="3. งานตรวจภายนอก")
    qc_electrical = models.BooleanField(default=False, verbose_name="4. งานเช็คระบบไฟฟ้า")
    qc_plumbing = models.BooleanField(default=False, verbose_name="5. งานเช็คระบบน้ำประปา")
    qc_aircon = models.BooleanField(default=False, verbose_name="6. งานเช็คระบบแอร์")

    is_qc_passed = models.BooleanField(default=False, verbose_name="ผ่าน QC แล้ว")
    note = models.TextField(blank=True, verbose_name="หมายเหตุ")
    is_closed = models.BooleanField(default=False, verbose_name="ปิดจ๊อบแล้ว (งานเสร็จสมบูรณ์)")
    is_onsite = models.BooleanField(default=False, verbose_name="งานประกอบหน้างาน (On-site)")
    
    delivery_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, verbose_name="ค่าจ้างขนส่ง (สำหรับงานนี้)")
    proof_of_delivery = models.ImageField(upload_to='delivery_proofs/%Y/%m/', null=True, blank=True, verbose_name="รูปถ่ายใบส่งมอบสินค้า")
    logistics_claim = models.ForeignKey('LogisticsClaim', on_delete=models.SET_NULL, null=True, blank=True, related_name='production_orders', verbose_name="ใบตั้งเบิกค่ารถขนส่ง")

    class Meta:
        verbose_name = "2. ใบสั่งผลิต"
        verbose_name_plural = "2. จัดการการผลิต"

    def __str__(self): return f"{self.code} - {self.product.name}"

    def save(self, *args, **kwargs):
        if not self.code:
            today = datetime.date.today()
            thai_year = (today.year + 543) % 100
            prefix = f"JOB{thai_year:02d}{today.strftime('%m')}"
            last_order = ProductionOrder.objects.filter(code__startswith=prefix).order_by('code').last()
            if last_order:
                try: seq = int(last_order.code.replace(prefix, '')) + 1
                except: seq = 1
            else: seq = 1
            self.code = f"{prefix}{seq:03d}"
        super().save(*args, **kwargs)

    @property
    def progress_percentage(self):
        total_depts = ProductionStatus.objects.count()
        if total_depts == 0: return 0
        return int((self.completed_departments.count() / total_depts) * 100)

    @property
    def days_remaining(self):
        if not self.deadline_date or self.is_closed: return 0
        return (self.deadline_date - datetime.date.today()).days

    @property
    def sla_status_color(self):
        if self.is_closed: return "success"
        rem = self.days_remaining
        if rem < 0: return "danger"
        if rem <= 5: return "warning"
        return "primary"

# ==========================================
# 🌟 [NEW] ตารางประวัติการตรวจสอบแบบ (Blueprint Log) 🌟
# ==========================================
class BlueprintLog(models.Model):
    production_order = models.ForeignKey(ProductionOrder, on_delete=models.CASCADE, related_name='blueprint_logs')
    action = models.CharField(max_length=255, verbose_name="รายละเอียดการอัปเดต")
    employee = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, verbose_name="ผู้ดำเนินการ")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="เวลาที่ดำเนินการ")

    class Meta:
        ordering = ['-created_at']

# ==========================================
# 🌟 ตารางประวัติการตรวจ QC (QC Inspection Log) 🌟
# ==========================================
class QCInspectionLog(models.Model):
    production_order = models.ForeignKey(ProductionOrder, related_name='qc_logs', on_delete=models.CASCADE, verbose_name="ใบสั่งผลิต")
    round_number = models.IntegerField(default=1, verbose_name="ตรวจครั้งที่")
    inspector = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, verbose_name="ผู้ตรวจสอบ (QC)")
    inspected_at = models.DateTimeField(auto_now_add=True, verbose_name="เวลาที่ตรวจ")
    status = models.CharField(max_length=20, choices=[('PASSED', 'ผ่าน'), ('FAILED', 'ไม่ผ่าน/ตีกลับ')], default='FAILED', verbose_name="ผลการตรวจ")
    comments = models.TextField(blank=True, verbose_name="คอมเมนต์/จุดที่ต้องแก้ไข")

    defect_image_1 = models.ImageField(upload_to='qc_defects/%Y/%m/', null=True, blank=True, verbose_name="รูปภาพประกอบ 1")
    defect_image_2 = models.ImageField(upload_to='qc_defects/%Y/%m/', null=True, blank=True, verbose_name="รูปภาพประกอบ 2")

    def __str__(self):
        return f"QC รอบที่ {self.round_number} - {self.production_order.code}"

# ==========================================
# 3. รายการวัตถุดิบที่ใช้จริงต่อ 1 งาน (Job Material List)
# ==========================================
class ProductionOrderMaterial(models.Model):
    production_order = models.ForeignKey(ProductionOrder, related_name='materials', on_delete=models.CASCADE)
    raw_material = models.ForeignKey(Product, on_delete=models.CASCADE, verbose_name="วัตถุดิบ")
    quantity = models.DecimalField(max_digits=10, decimal_places=4, verbose_name="จำนวนที่ต้องใช้")
    is_additional = models.BooleanField(default=False, verbose_name="เป็นรายการสั่งเพิ่มพิเศษ (ไม่อยู่ใน BOM)")

    def __str__(self): return f"{self.production_order.code} - {self.raw_material.name}"
    class Meta:
        verbose_name = "3. วัตถุดิบในใบสั่งผลิต"
        verbose_name_plural = "3. จัดการวัตถุดิบในงานผลิต"