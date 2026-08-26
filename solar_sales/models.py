from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User
from decimal import Decimal
import datetime
import secrets
from solar_inventory.models import SolarProduct
from master_data.models import Customer, Supplier
from hr.models import Employee

# ==========================================
# 📝 2. ระบบขายโซล่าเซลล์ (Solar Sales)
# ==========================================
class SolarQuotation(models.Model):
    STATUS_CHOICES = [
        ('DRAFT', 'รออนุมัติ'),
        ('APPROVED', 'อนุมัติแล้ว'),
        ('PROCESSING', 'ช่างกำลังติดตั้ง'),
        ('READY', 'พร้อมเปิดบิล'),
        ('CONVERTED', 'เปิดบิลขายแล้ว'),
        ('CANCELLED', 'ยกเลิกแล้ว')
    ]
    VAT_CHOICES = [
        ('NONE', 'ไม่มี VAT'),
        ('EXCLUDE', 'แยก VAT 7%'),
        ('INCLUDE', 'รวม VAT 7%')
    ]

    code = models.CharField(max_length=20, unique=True, verbose_name="เลขที่ใบเสนอราคาโซล่า")
    date = models.DateField(default=timezone.now, verbose_name="วันที่เอกสาร (dd/mm/yyyy)")

    valid_until = models.DateField(null=True, blank=True, verbose_name="ยืนยันราคาถึงวันที่ (dd/mm/yyyy)")

    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, blank=True)
    employee = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, verbose_name="พนักงานขาย")

    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="รวมราคาสินค้า")
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="หักส่วนลด")
    survey_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="ค่าสำรวจหน้างาน / ค่าจัดส่ง")

    # 🌟 [FIXED] เปลี่ยน default เป็น 'INCLUDE' เพื่อให้ถอด VAT 7% อัตโนมัติ 🌟
    vat_type = models.CharField(max_length=10, choices=VAT_CHOICES, default='INCLUDE', verbose_name="ประเภทภาษี")
    vat_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="ยอด VAT 7%")
    grand_total = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="ยอดสุทธิ (Grand Total)")

    payment_terms = models.TextField(
        default="- ชำระเงินมัดจำ 50% ของยอดรวมเพื่อยืนยันการสั่งซื้อ\n- ส่วนที่เหลือชำระก่อนการติดตั้ง",
        verbose_name="เงื่อนไขการชำระเงิน (Payment Terms)"
    )

    deposit_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="มัดจำ")
    deposit_code = models.CharField(max_length=20, blank=True, null=True, verbose_name="เลขใบรับเงินมัดจำ")
    deposit_method = models.CharField(max_length=20, default='TRANSFER', verbose_name="ช่องทางรับเงิน")
    deposit_date = models.DateField(null=True, blank=True, verbose_name="วันที่รับเงินมัดจำ")
    deposit_slip = models.ImageField(upload_to='solar_deposits/', null=True, blank=True, verbose_name="สลิปโอนเงิน")
    is_deposit_paid = models.BooleanField(default=False)
    is_deposit_verified = models.BooleanField(default=False, verbose_name="บัญชีตรวจสอบแล้ว")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT')
    note = models.TextField(blank=True, verbose_name="หมายเหตุ")

    # 🌟 [NEW] เพิ่มฟิลด์สำหรับระบบเซ็นออนไลน์ (เลียนแบบบ้านน็อคดาวน์) 🌟
    signature_token = models.CharField(max_length=64, blank=True, null=True, unique=True)
    customer_signature = models.ImageField(upload_to='solar_customer_signatures/%Y/%m/', null=True, blank=True, verbose_name="ลายเซ็นลูกค้า")
    signature_date = models.DateTimeField(null=True, blank=True, verbose_name="เวลาที่ลูกค้าเซ็น")

    deposit_signature_token = models.CharField(max_length=64, blank=True, null=True, unique=True)
    customer_deposit_signature = models.ImageField(upload_to='solar_deposit_signatures/%Y/%m/', null=True, blank=True, verbose_name="ลายเซ็นสัญญามัดจำ")
    deposit_signature_date = models.DateTimeField(null=True, blank=True, verbose_name="เวลาที่เซ็นสัญญามัดจำ")

    @property
    def balance_due(self):
        if hasattr(self, 'solarinvoice'):
            return self.solarinvoice.balance_amount
        return self.grand_total - self.deposit_amount

    def save(self, *args, **kwargs):
        # 🌟 [NEW] สร้าง Token อัตโนมัติเมื่อกดบันทึก 🌟
        if not self.signature_token:
            self.signature_token = secrets.token_urlsafe(32)
        if not self.deposit_signature_token:
            self.deposit_signature_token = secrets.token_urlsafe(32)

        if not self.code:
            now = timezone.now()
            thai_year = (now.year + 543) % 100
            prefix = f"QT-SOL-{thai_year:02d}{now.strftime('%m')}"
            last = SolarQuotation.objects.filter(code__startswith=prefix).order_by('code').last()
            seq = int(last.code.split('-')[-1]) + 1 if last else 1
            self.code = f"{prefix}-{seq:03d}"

            if not self.valid_until:
                self.valid_until = self.date + datetime.timedelta(days=15)

        super().save(*args, **kwargs)

class SolarQuotationItem(models.Model):
    quotation = models.ForeignKey(SolarQuotation, related_name='items', on_delete=models.CASCADE)
    product = models.ForeignKey(SolarProduct, on_delete=models.SET_NULL, null=True, blank=True)

    item_name = models.CharField(max_length=255, blank=True, null=True, verbose_name="ชื่อที่จะแสดงในบิล")

    quantity = models.IntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    amount = models.DecimalField(max_digits=10, decimal_places=2)

class SolarInvoice(models.Model):
    code = models.CharField(max_length=20, unique=True, verbose_name="เลขที่ใบเสร็จโซล่า")
    quotation_ref = models.OneToOneField(SolarQuotation, on_delete=models.SET_NULL, null=True, blank=True)
    date = models.DateField(default=timezone.now, verbose_name="วันที่เอกสาร (dd/mm/yyyy)")
    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True)
    grand_total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    balance_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=[('UNPAID', 'ยังไม่ชำระ'), ('PAID', 'ชำระแล้ว')], default='UNPAID')

    def save(self, *args, **kwargs):
        if not self.code:
            now = timezone.now()
            thai_year = (now.year + 543) % 100
            prefix = f"INV-SOL-{thai_year:02d}{now.strftime('%m')}"
            last = SolarInvoice.objects.filter(code__startswith=prefix).order_by('code').last()
            seq = int(last.code.split('-')[-1]) + 1 if last else 1
            self.code = f"{prefix}-{seq:03d}"
        super().save(*args, **kwargs)

# ==========================================
# 👷‍♂️ 3. ระบบสำรวจหน้างานและเบิกจ่าย (Solar Survey & Expense)
# ==========================================
class SolarSurveyJob(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'รอลงพื้นที่'),
        ('IN_PROGRESS', 'กำลังดำเนินการ'),
        ('COMPLETED', 'สำรวจเสร็จสิ้น'),
        ('CANCELLED', 'ยกเลิก')
    ]
    code = models.CharField(max_length=20, unique=True, verbose_name="เลขที่ใบงานสำรวจ")

    # 🌟 [FIXED] เปลี่ยนให้ลูกค้าระบบเป็นค่าว่างได้ เผื่อกรณีพิมพ์ชื่อเอง (Walk-in) 🌟
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, null=True, blank=True, verbose_name="ลูกค้า")

    # 🌟 [NEW] เพิ่ม 2 ฟิลด์ใหม่สำหรับเก็บข้อมูลลูกค้า Walk-in 🌟
    walkin_name = models.CharField(max_length=200, blank=True, null=True, verbose_name="ชื่อลูกค้า (Walk-in)")
    walkin_phone = models.CharField(max_length=50, blank=True, null=True, verbose_name="เบอร์ติดต่อ (Walk-in)")

    appointment_date = models.DateTimeField(verbose_name="วันเวลานัดหมาย")
    assigned_by = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, related_name='solar_survey_assigned', verbose_name="ผู้มอบหมาย (Admin)")
    surveyor = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, related_name='solar_survey_tasks', verbose_name="ผู้สำรวจ (ช่าง)")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING', verbose_name="สถานะงาน")
    note = models.TextField(blank=True, null=True, verbose_name="รายละเอียด/หมายเหตุ")
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.code:
            now = timezone.now()
            thai_year = (now.year + 543) % 100
            prefix = f"SV-SOL-{thai_year:02d}{now.strftime('%m')}"
            last = SolarSurveyJob.objects.filter(code__startswith=prefix).order_by('code').last()
            seq = int(last.code.split('-')[-1]) + 1 if last else 1
            self.code = f"{prefix}-{seq:03d}"
        super().save(*args, **kwargs)

    def __str__(self):
        return self.code

class SolarSurveyItem(models.Model):
    job = models.ForeignKey(SolarSurveyJob, related_name='items', on_delete=models.CASCADE)
    item_name = models.CharField(max_length=255, verbose_name="รายการวัสดุ/สเปค")
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=1, verbose_name="จำนวน")
    unit = models.CharField(max_length=50, blank=True, null=True, verbose_name="หน่วยนับ")

class SolarExpenseClaim(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'รอหัวหน้าอนุมัติ'),
        ('APPROVED', 'อนุมัติแล้ว (รอบัญชีจ่าย)'),
        ('PAID', 'จ่ายเงินแล้ว'),
        ('REJECTED', 'ไม่อนุมัติ')
    ]
    code = models.CharField(max_length=20, unique=True, verbose_name="เลขที่ใบเบิก")
    survey_job = models.ForeignKey(SolarSurveyJob, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="อ้างอิงใบงานสำรวจ")
    requester = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='solar_expenses_requested', verbose_name="ผู้ขอเบิก")
    amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="ยอดเงินเบิก")
    description = models.TextField(verbose_name="รายละเอียดค่าใช้จ่าย")
    slip_image = models.ImageField(upload_to='solar_expenses/', null=True, blank=True, verbose_name="รูปสลิป/ใบเสร็จ")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING', verbose_name="สถานะ")
    approver = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, blank=True, related_name='solar_expenses_approved', verbose_name="ผู้อนุมัติ (หัวหน้า/บัญชี)")
    transfer_slip = models.ImageField(upload_to='solar_expenses/transfers/', null=True, blank=True, verbose_name="สลิปโอนเงินให้ช่าง")
    paid_at = models.DateTimeField(null=True, blank=True, verbose_name="วันที่โอนเงิน")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if not self.code:
            now = timezone.now()
            thai_year = (now.year + 543) % 100
            prefix = f"EXP-SOL-{thai_year:02d}{now.strftime('%m')}"
            last = SolarExpenseClaim.objects.filter(code__startswith=prefix).order_by('code').last()
            seq = int(last.code.split('-')[-1]) + 1 if last else 1
            self.code = f"{prefix}-{seq:03d}"
        super().save(*args, **kwargs)

    def __str__(self):
        return self.code

# 🌟 [NEW] สร้างตารางใหม่สำหรับเก็บรูปสลิป/ใบเสร็จ (รองรับการแนบหลายรูป) 🌟
class SolarExpenseSlip(models.Model):
    expense = models.ForeignKey(SolarExpenseClaim, related_name='slips', on_delete=models.CASCADE)
    image = models.ImageField(upload_to='solar_expenses/slips/', verbose_name="รูปสลิป/ใบเสร็จ")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Slip for {self.expense.code}"