from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User
from decimal import Decimal
import datetime
import secrets
from solar_inventory.models import SolarProduct
from master_data.models import Supplier
from hr.models import Employee

# ==========================================
# 📝 1. ฐานข้อมูลลูกค้าโซล่าเซลล์ (แยกจากน็อคดาวน์)
# ==========================================
class SolarCustomer(models.Model):
    name = models.CharField(max_length=200, verbose_name="ชื่อ-นามสกุล / ชื่อบริษัท")
    code = models.CharField(max_length=50, unique=True, blank=True, verbose_name="รหัสลูกค้า")
    branch = models.CharField(max_length=100, blank=True, null=True, verbose_name="สาขา")
    tax_id = models.CharField(max_length=20, blank=True, null=True, verbose_name="เลขประจำตัวผู้เสียภาษี")
    phone = models.CharField(max_length=50, blank=True, null=True, verbose_name="เบอร์โทรศัพท์")
    email = models.EmailField(blank=True, null=True, verbose_name="อีเมล")

    address = models.TextField(blank=True, null=True, verbose_name="ที่อยู่ (เลขที่/หมู่บ้าน/ถนน)")
    province = models.CharField(max_length=100, blank=True, null=True, verbose_name="จังหวัด")
    district = models.CharField(max_length=100, blank=True, null=True, verbose_name="อำเภอ/เขต")
    sub_district = models.CharField(max_length=100, blank=True, null=True, verbose_name="ตำบล/แขวง")
    zip_code = models.CharField(max_length=10, blank=True, null=True, verbose_name="รหัสไปรษณีย์")
    location = models.URLField(max_length=500, blank=True, null=True, verbose_name="พิกัด GPS")
    is_active = models.BooleanField(default=True, verbose_name="สถานะใช้งาน")

    contact_person = models.CharField(max_length=100, blank=True, null=True, verbose_name="ชื่อผู้ติดต่อประสานงาน")
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.code:
            today = datetime.date.today()
            thai_year = (today.year + 543) % 100
            prefix = f"CUS-SOL-{thai_year:02d}{today.strftime('%m')}-"
            last_customer = SolarCustomer.objects.filter(code__startswith=prefix).order_by('code').last()
            seq = int(last_customer.code.split('-')[-1]) + 1 if last_customer else 1
            self.code = f"{prefix}{seq:03d}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.code} - {self.name}"

    class Meta:
        verbose_name = "รายชื่อลูกค้า (โซล่าเซลล์)"
        verbose_name_plural = "รายชื่อลูกค้า (โซล่าเซลล์)"

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
        ('INCLUDE', 'รวม VAT 7%')
    ]

    code = models.CharField(max_length=20, unique=True, verbose_name="เลขที่ใบเสนอราคาโซล่า")
    date = models.DateField(default=timezone.now, verbose_name="วันที่เอกสาร (dd/mm/yyyy)")

    valid_until = models.DateField(null=True, blank=True, verbose_name="ยืนยันราคาถึงวันที่ (dd/mm/yyyy)")

    customer = models.ForeignKey(SolarCustomer, on_delete=models.SET_NULL, null=True, blank=True)
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
        if not self.signature_token:
            self.signature_token = secrets.token_urlsafe(32)
        if not self.deposit_signature_token:
            self.deposit_signature_token = secrets.token_urlsafe(32)

        # 🌟 [FIXED] ระบบ Auto-Sync: ถ้าบัญชีตรวจผ่าน ให้สลิปค่างวดทุกใบผ่านด้วยอัตโนมัติ
        if self.pk and self.is_deposit_verified:
            self.solar_deposits.filter(is_verified=False).update(is_verified=True)

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

    @property
    def active_installments(self):
        # 🌟 [FIXED] กรองสลิปค่างวดทั้งหมด โดยตัดสลิปก้อนแรกสุดออกอย่างแม่นยำ
        return self.solar_deposits.exclude(code=self.deposit_code)

class SolarQuotationItem(models.Model):
    quotation = models.ForeignKey(SolarQuotation, related_name='items', on_delete=models.CASCADE)
    product = models.ForeignKey(SolarProduct, on_delete=models.SET_NULL, null=True, blank=True)

    item_name = models.CharField(max_length=255, blank=True, null=True, verbose_name="ชื่อที่จะแสดงในบิล")

    quantity = models.IntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    amount = models.DecimalField(max_digits=10, decimal_places=2)

# ==========================================
# 💰 ระบบจัดการใบรับเงินมัดจำ โซล่าเซลล์ (Separated Deposit Model)
# ==========================================
class SolarQuotationDeposit(models.Model):
    PAYMENT_CHOICES = [
        ('CASH', 'เงินสด'),
        ('TRANSFER', 'โอนเงิน'),
        ('CHECK', 'เช็คธนาคาร')
    ]

    code = models.CharField(max_length=20, unique=True, verbose_name="เลขที่ใบรับมัดจำโซล่า (RVD-SOL)")

    # 🌟 เชื่อมโยงกลับไปที่ SolarQuotation แบบ 1-to-Many
    # ใช้ related_name='solar_deposits' เพื่อไม่ให้ซ้ำกับของระบบน็อคดาวน์
    quotation = models.ForeignKey('SolarQuotation', on_delete=models.CASCADE, related_name='solar_deposits', verbose_name="อ้างอิงใบเสนอราคาโซล่า")

    amount = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="ยอดมัดจำที่รับ")
    deposit_date = models.DateField(default=timezone.now, verbose_name="วันที่รับมัดจำ")
    payment_method = models.CharField(max_length=50, choices=PAYMENT_CHOICES, blank=True, null=True, verbose_name="ช่องทางรับมัดจำ")
    deposit_slip = models.ImageField(upload_to='solar_deposit_slips_v2/%Y/%m/', null=True, blank=True, verbose_name="สลิปมัดจำ")

    is_verified = models.BooleanField(default=False, verbose_name="บัญชีตรวจสอบมัดจำแล้ว")
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # ฟังก์ชันย่อขนาดรูปสลิปอัตโนมัติ
        if self.deposit_slip:
            try:
                from PIL import Image
                img = Image.open(self.deposit_slip.path)
                if img.height > 800 or img.width > 800:
                    output_size = (800, 800)
                    img.thumbnail(output_size)
                    img.save(self.deposit_slip.path, quality=85, optimize=True)
            except Exception:
                pass

    def __str__(self):
        return str(self.code)

class SolarInvoice(models.Model):
    # 🌟 [FIXED] เพิ่มสถานะ 'PENDING_VERIFY' เข้าไปในตัวเลือก
    STATUS_CHOICES = [
        ('UNPAID', 'ยังไม่ชำระ'),
        ('PENDING', 'รอวางบิล'), # เผื่อกรณีสร้างแล้วยังไม่ได้วางบิล
        ('PENDING_VERIFY', 'รอบัญชีตรวจสอบ'),
        ('PAID', 'ชำระแล้ว')
    ]

    code = models.CharField(max_length=20, unique=True, verbose_name="เลขที่ใบเสร็จโซล่า")
    quotation_ref = models.OneToOneField(SolarQuotation, on_delete=models.SET_NULL, null=True, blank=True)
    date = models.DateField(default=timezone.now, verbose_name="วันที่เอกสาร (dd/mm/yyyy)")
    customer = models.ForeignKey(SolarCustomer, on_delete=models.SET_NULL, null=True)
    grand_total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    balance_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='UNPAID')

    # 🌟 [NEW] เพิ่มช่องเก็บหลักฐานการชำระเงินของบิลขายใบนี้
    payment_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="ยอดรับชำระล่าสุด")
    payment_date = models.DateField(null=True, blank=True, verbose_name="วันที่รับชำระล่าสุด")
    payment_method = models.CharField(max_length=20, blank=True, null=True, verbose_name="ช่องทางชำระล่าสุด")
    payment_slip = models.ImageField(upload_to='solar_invoice_payments/', null=True, blank=True, verbose_name="สลิปรับชำระเงินล่าสุด")

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
    customer = models.ForeignKey(SolarCustomer, on_delete=models.CASCADE, null=True, blank=True, verbose_name="ลูกค้า")

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

# ==========================================
# 💸 4. ระบบเบิกผลตอบแทนโซล่าเซลล์ (Incentive & Commission)
# ==========================================
class SolarCommissionClaim(models.Model):
    # 🌟 [FIXED] เปลี่ยนประเภทการเบิกเป็น 4 ส่วนใหม่
    CLAIM_TYPES = [
        ('1.5%', '1.5% (Admin)'),
        ('2.5%', '2.5% (Executive)'),
        ('4%', '4% (Sales)'),
        ('7.5%', '7.5% (Tech)')
    ]
    STATUS_CHOICES = [('PENDING', 'รอโอนเงิน'), ('PAID', 'โอนเงินแล้ว')]

    code = models.CharField(max_length=20, unique=True, verbose_name="เลขที่ใบเบิกผลตอบแทน")
    claim_type = models.CharField(max_length=10, choices=CLAIM_TYPES, verbose_name="ประเภทการเบิก")
    requester = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, verbose_name="ผู้ทำรายการเบิก")
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="ยอดเงินรวม")
    # 🌟 [NEW] เพิ่ม 2 บรรทัดนี้ เพื่อเก็บข้อมูลธนาคารของใบเบิกแต่ละใบ 🌟
    bank_name = models.CharField(max_length=100, blank=True, null=True, verbose_name="ธนาคารที่รับเงิน")
    bank_account = models.CharField(max_length=50, blank=True, null=True, verbose_name="เลขที่บัญชี")
    account_name = models.CharField(max_length=150, blank=True, null=True, verbose_name="ชื่อบัญชีธนาคาร")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING', verbose_name="สถานะ")

    transfer_slip = models.ImageField(upload_to='solar_commissions/', null=True, blank=True, verbose_name="สลิปโอนเงิน")
    paid_at = models.DateTimeField(null=True, blank=True, verbose_name="วันที่โอนเงิน")
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.code:
            now = timezone.now()
            thai_year = (now.year + 543) % 100
            # 🌟 [FIXED] แยกรหัส Prefix ตามประเภทใหม่
            if self.claim_type == '1.5%': prefix = f"R15-SOL-{thai_year:02d}{now.strftime('%m')}"
            elif self.claim_type == '2.5%': prefix = f"R25-SOL-{thai_year:02d}{now.strftime('%m')}"
            elif self.claim_type == '4%': prefix = f"R4-SOL-{thai_year:02d}{now.strftime('%m')}"
            else: prefix = f"R75-SOL-{thai_year:02d}{now.strftime('%m')}"

            last = SolarCommissionClaim.objects.filter(code__startswith=prefix).order_by('code').last()
            seq = int(last.code.split('-')[-1]) + 1 if last else 1
            self.code = f"{prefix}-{seq:03d}"
        super().save(*args, **kwargs)

    def __str__(self):
        return self.code

class SolarCommissionTicket(models.Model):
    # 🌟 [FIXED] เปลี่ยนประเภทสิทธิ์เป็น 4 ส่วนใหม่
    TICKET_TYPES = [
        ('1.5%', '1.5% (Admin)'),
        ('2.5%', '2.5% (Executive)'),
        ('4%', '4% (Sales)'),
        ('7.5%', '7.5% (Tech)')
    ]
    STATUS_CHOICES = [('AVAILABLE', 'พร้อมเบิก'), ('CLAIMING', 'กำลังตั้งเบิก'), ('PAID', 'จ่ายแล้ว')]

    code = models.CharField(max_length=20, unique=True, verbose_name="เลขที่ใบคุมสิทธิ์")
    ticket_type = models.CharField(max_length=10, choices=TICKET_TYPES, verbose_name="ประเภทสิทธิ์")

    quotation_ref = models.ForeignKey('SolarQuotation', on_delete=models.CASCADE, null=True, blank=True, verbose_name="อ้างอิงใบเสนอราคา")
    invoice_ref = models.ForeignKey('SolarInvoice', on_delete=models.CASCADE, null=True, blank=True, verbose_name="อ้างอิงใบแจ้งหนี้")

    base_amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="ยอดฐานคำนวณ (ก่อน VAT)")
    commission_amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="ยอดผลตอบแทน")

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='AVAILABLE', verbose_name="สถานะสิทธิ์")
    claim_ref = models.ForeignKey(SolarCommissionClaim, on_delete=models.SET_NULL, null=True, blank=True, related_name='tickets', verbose_name="รวมอยู่ในใบเบิกเลขที่")

    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.code:
            now = timezone.now()
            thai_year = (now.year + 543) % 100
            # 🌟 [FIXED] แยกรหัส Prefix ตามประเภทใหม่
            if self.ticket_type == '1.5%': prefix = f"C15-SOL-{thai_year:02d}{now.strftime('%m')}"
            elif self.ticket_type == '2.5%': prefix = f"C25-SOL-{thai_year:02d}{now.strftime('%m')}"
            elif self.ticket_type == '4%': prefix = f"C4-SOL-{thai_year:02d}{now.strftime('%m')}"
            else: prefix = f"C75-SOL-{thai_year:02d}{now.strftime('%m')}"

            last = SolarCommissionTicket.objects.filter(code__startswith=prefix).order_by('code').last()
            seq = int(last.code.split('-')[-1]) + 1 if last else 1
            self.code = f"{prefix}-{seq:03d}"
        super().save(*args, **kwargs)

    def __str__(self):
        return self.code