from django.db import models
from django.utils import timezone
from decimal import Decimal
from master_data.models import Customer
from hr.models import Employee
from inventory.models import Product
from PIL import Image
import secrets

class POSOrder(models.Model):
    STATUS_CHOICES = [('PENDING', 'รอชำระเงิน'), ('PAID', 'ชำระเงินแล้ว'), ('CANCELLED', 'ยกเลิก')]
    PAYMENT_CHOICES = [('CASH', 'เงินสด'), ('TRANSFER', 'โอนเงิน'), ('CHECK', 'เช็คธนาคาร')]

    code = models.CharField(max_length=20, unique=True, verbose_name="เลขที่ใบเสร็จ")
    employee = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, verbose_name="พนักงานขาย")
    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="ลูกค้า (สมาชิก)")
    customer_name = models.CharField(max_length=200, blank=True, verbose_name="ชื่อลูกค้า (ระบุเอง)")
    customer_address = models.TextField(blank=True, verbose_name="ที่อยู่")
    customer_tax_id = models.CharField(max_length=20, blank=True, verbose_name="เลขผู้เสียภาษี")
    customer_phone = models.CharField(max_length=20, blank=True, verbose_name="เบอร์โทรศัพท์")
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="ยอดรวม")
    received_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="รับเงินมา")
    change_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="เงินทอน")
    payment_method = models.CharField(max_length=50, choices=PAYMENT_CHOICES, default='CASH', verbose_name="วิธีชำระ")
    transfer_slip = models.ImageField(upload_to='pos_slips/%Y/%m/', null=True, blank=True, verbose_name="สลิปโอนเงิน")
    check_number = models.CharField(max_length=50, blank=True, verbose_name="เลขที่เช็ค")
    check_bank = models.CharField(max_length=100, blank=True, verbose_name="ธนาคารเช็ค")
    check_slip = models.ImageField(upload_to='pos_checks/%Y/%m/', null=True, blank=True, verbose_name="รูปถ่ายเช็ค")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PAID', verbose_name="สถานะ")
    is_commission_calculated = models.BooleanField(default=False, verbose_name="คำนวณคอมฯแล้ว")
    created_at = models.DateTimeField(default=timezone.now, verbose_name="เวลาที่ขาย")

    def __str__(self): 
        return str(self.code) if self.code else "ไม่มีเลขที่"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.transfer_slip:
            try:
                img = Image.open(self.transfer_slip.path)
                if img.height > 800 or img.width > 800:
                    output_size = (800, 800)
                    img.thumbnail(output_size)
                    img.save(self.transfer_slip.path, quality=85, optimize=True)
            except Exception: pass
        if self.check_slip:
            try:
                img = Image.open(self.check_slip.path)
                if img.height > 800 or img.width > 800:
                    output_size = (800, 800)
                    img.thumbnail(output_size)
                    img.save(self.check_slip.path, quality=85, optimize=True)
            except Exception: pass

class POSOrderItem(models.Model):
    order = models.ForeignKey(POSOrder, related_name='items', on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, verbose_name="สินค้า")
    product_name = models.CharField(max_length=200, verbose_name="ชื่อสินค้า (ณ ตอนขาย)", null=True, blank=True)
    quantity = models.IntegerField(default=1, verbose_name="จำนวน")
    price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="ราคาต่อชิ้น")
    total_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="ราคารวม")
    
    def save(self, *args, **kwargs):
        self.total_price = self.quantity * self.price
        if not self.product_name and self.product: self.product_name = self.product.name
        super().save(*args, **kwargs)

class Quotation(models.Model):
    STATUS_CHOICES = [
        ('DRAFT', 'รออนุมัติ'),
        ('APPROVED', 'อนุมัติแล้ว'),
        ('CONVERTED', 'เปิดบิลขายแล้ว'),
        ('REJECTED', 'ไม่อนุมัติ'),
        ('CANCELLED', 'ยกเลิกแล้ว')
    ]
    code = models.CharField(max_length=20, unique=True, verbose_name="เลขที่ใบเสนอราคา")
    date = models.DateField(default=timezone.now, verbose_name="วันที่เอกสาร")
    valid_until = models.DateField(null=True, blank=True, verbose_name="ยืนราคาถึงวันที่")
    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="ลูกค้า (Link)")
    customer_name = models.CharField(max_length=200, verbose_name="ชื่อลูกค้า (ระบุเอง)", blank=True)
    customer_address = models.TextField(verbose_name="ที่อยู่", blank=True)
    customer_tax_id = models.CharField(max_length=20, verbose_name="เลขผู้เสียภาษี", blank=True)
    customer_phone = models.CharField(max_length=50, verbose_name="เบอร์โทร", blank=True)
    employee = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, verbose_name="ผู้ออกใบเสนอราคา")
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="รวมราคาสินค้า")
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="ส่วนลด")

    shipping_origin = models.CharField(max_length=100, blank=True, null=True, verbose_name="สาขาต้นทาง (ผลิต)")
    shipping_province = models.CharField(max_length=100, blank=True, null=True, verbose_name="จังหวัดปลายทาง")
    shipping_is_island = models.BooleanField(default=False, verbose_name="ส่งข้ามเกาะ")
    shipping_is_oversize = models.BooleanField(default=False, verbose_name="ตู้ยาวเกินมาตรฐาน (+1000)")
    shipping_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="ค่าขนส่ง")

    tax_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="ภาษีมูลค่าเพิ่ม")
    grand_total = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="ยอดสุทธิ")

    deposit_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="ยอดมัดจำที่รับแล้ว")
    deposit_date = models.DateField(null=True, blank=True, verbose_name="วันที่รับมัดจำ")
    deposit_method = models.CharField(max_length=50, blank=True, null=True, verbose_name="ช่องทางรับมัดจำ")
    deposit_slip = models.ImageField(upload_to='deposit_slips/%Y/%m/', null=True, blank=True, verbose_name="สลิปมัดจำ")
    is_deposit_paid = models.BooleanField(default=False, verbose_name="รับมัดจำแล้ว")
    is_deposit_verified = models.BooleanField(default=False, verbose_name="บัญชีตรวจสอบมัดจำแล้ว")

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT', verbose_name="สถานะ")

    payment_terms = models.TextField(blank=True, verbose_name="เงื่อนไขการชำระเงิน")
    note = models.TextField(blank=True, verbose_name="หมายเหตุ")

    created_at = models.DateTimeField(auto_now_add=True)
    approved_by = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_quotations', verbose_name="ผู้อนุมัติ")
    approved_at = models.DateTimeField(null=True, blank=True, verbose_name="วันที่อนุมัติ")
    
    # 🌟 ฟิลด์ E-Signature สำหรับใบเสนอราคา
    signature_token = models.CharField(max_length=64, blank=True, null=True, unique=True)
    customer_signature = models.ImageField(upload_to='customer_signatures/%Y/%m/', null=True, blank=True, verbose_name="ลายเซ็นลูกค้า")
    signature_date = models.DateTimeField(null=True, blank=True, verbose_name="เวลาที่ลูกค้าเซ็น")

    # 🌟 [NEW] ฟิลด์ E-Signature สำหรับสัญญามัดจำ 🌟
    deposit_signature_token = models.CharField(max_length=64, blank=True, null=True, unique=True)
    customer_deposit_signature = models.ImageField(upload_to='deposit_signatures_contract/%Y/%m/', null=True, blank=True, verbose_name="ลายเซ็นสัญญามัดจำ")
    deposit_signature_date = models.DateTimeField(null=True, blank=True, verbose_name="เวลาที่เซ็นสัญญามัดจำ")

    def __str__(self): 
        return str(self.code) if self.code else "ไม่มีเลขที่ใบเสนอราคา"

    @property
    def customer_code(self): return self.customer.code if self.customer else None

    @property
    def balance_due(self):
        gt = self.grand_total if self.grand_total else Decimal(0)
        dep = self.deposit_amount if self.deposit_amount else Decimal(0)
        return gt - dep

    def save(self, *args, **kwargs):
        if not self.signature_token:
            self.signature_token = secrets.token_urlsafe(32)
        # 🌟 สร้าง Token สำหรับลิงก์สัญญามัดจำ
        if not self.deposit_signature_token:
            self.deposit_signature_token = secrets.token_urlsafe(32)
            
        super().save(*args, **kwargs)
        
        if self.deposit_slip:
            try:
                img = Image.open(self.deposit_slip.path)
                if img.height > 800 or img.width > 800:
                    output_size = (800, 800)
                    img.thumbnail(output_size)
                    img.save(self.deposit_slip.path, quality=85, optimize=True)
            except Exception: pass    

class QuotationItem(models.Model):
    quotation = models.ForeignKey(Quotation, related_name='items', on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, verbose_name="สินค้า")
    item_name = models.CharField(max_length=200, verbose_name="ชื่อรายการสินค้า")
    description = models.CharField(max_length=255, blank=True, null=True)
    quantity = models.IntegerField(default=1, verbose_name="จำนวน")
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="ราคาต่อหน่วย")
    amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="รวมเงิน")
    
    def save(self, *args, **kwargs):
        self.amount = self.quantity * self.unit_price
        super().save(*args, **kwargs)

class Invoice(models.Model):
    PAYMENT_CHOICES = [('CASH', 'เงินสด'), ('TRANSFER', 'โอนเงิน'), ('CHECK', 'เช็คธนาคาร')]

    code = models.CharField(max_length=20, unique=True, verbose_name="เลขที่ใบกำกับภาษี/ใบเสร็จ")
    quotation_ref = models.OneToOneField(Quotation, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="อ้างอิงใบเสนอราคา")
    date = models.DateField(default=timezone.now, verbose_name="วันที่เอกสาร")
    due_date = models.DateField(null=True, blank=True, verbose_name="ครบกำหนดชำระ")
    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, verbose_name="ลูกค้า")
    employee = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, verbose_name="พนักงานขาย")
    grand_total = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="ยอดสุทธิ")
    deposit_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="หักมัดจำ")
    balance_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="ยอดคงค้างชำระ")

    payment_method = models.CharField(max_length=50, choices=PAYMENT_CHOICES, blank=True, null=True, verbose_name="วิธีชำระเงิน")
    payment_date = models.DateField(null=True, blank=True, verbose_name="วันที่ชำระเงิน")
    transfer_slip = models.ImageField(upload_to='invoice_slips/%Y/%m/', null=True, blank=True, verbose_name="สลิปโอนเงิน")
    check_number = models.CharField(max_length=50, blank=True, verbose_name="เลขที่เช็ค")
    check_bank = models.CharField(max_length=100, blank=True, verbose_name="ธนาคารเช็ค")
    check_slip = models.ImageField(upload_to='invoice_checks/%Y/%m/', null=True, blank=True, verbose_name="รูปถ่ายเช็ค")

    status = models.CharField(max_length=20, choices=[('UNPAID', 'ยังไม่ชำระ'), ('PAID', 'ชำระแล้ว'), ('PENDING', 'รอตรวจสอบ')], default='UNPAID', verbose_name="สถานะ")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self): 
        return str(self.code) if self.code else "ไม่มีเลขที่บิล"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.transfer_slip:
            try:
                img = Image.open(self.transfer_slip.path)
                if img.height > 800 or img.width > 800:
                    output_size = (800, 800)
                    img.thumbnail(output_size)
                    img.save(self.transfer_slip.path, quality=85, optimize=True)
            except Exception: pass
        if self.check_slip:
            try:
                img = Image.open(self.check_slip.path)
                if img.height > 800 or img.width > 800:
                    output_size = (800, 800)
                    img.thumbnail(output_size)
                    img.save(self.check_slip.path, quality=85, optimize=True)
            except Exception: pass

class UpsaleCategory(models.Model):
    name = models.CharField(max_length=100, verbose_name="หมวดหมู่รายการเพิ่มเติม")
    is_active = models.BooleanField(default=True, verbose_name="เปิดใช้งาน")
    def __str__(self): return str(self.name) if self.name else "-"

class UpsaleCatalog(models.Model):
    category = models.ForeignKey(UpsaleCategory, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="หมวดหมู่")
    name = models.CharField(max_length=200, verbose_name="ชื่อรายการปรับเปลี่ยน/เพิ่มเติม")
    default_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="ราคามาตรฐาน")
    unit = models.CharField(max_length=50, blank=True, null=True, default="รายการ", verbose_name="หน่วยนับ")
    is_active = models.BooleanField(default=True, verbose_name="เปิดใช้งาน")
    def __str__(self): return str(self.name) if self.name else "-"

class QuotationUpsale(models.Model):
    quotation = models.ForeignKey(Quotation, related_name='upsales', on_delete=models.CASCADE)
    description = models.CharField(max_length=255, verbose_name="รายการเพิ่มเติม")
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    def save(self, *args, **kwargs):
        self.total_price = self.quantity * self.unit_price
        super().save(*args, **kwargs)

    def __str__(self): return f"{self.description} ({self.quotation.code if self.quotation else ''})"

class InvoicePayment(models.Model):
    invoice = models.ForeignKey(Invoice, related_name='payment_history', on_delete=models.CASCADE, verbose_name="อ้างอิงบิล")
    amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="ยอดชำระ")
    payment_method = models.CharField(max_length=50, choices=Invoice.PAYMENT_CHOICES, verbose_name="วิธีชำระ")
    payment_date = models.DateField(default=timezone.now, verbose_name="วันที่ชำระ")
    transfer_slip = models.ImageField(upload_to='invoice_slips/%Y/%m/', null=True, blank=True, verbose_name="สลิปโอนเงิน")
    check_number = models.CharField(max_length=50, blank=True, verbose_name="เลขที่เช็ค")
    check_bank = models.CharField(max_length=100, blank=True, verbose_name="ธนาคารเช็ค")
    check_slip = models.ImageField(upload_to='invoice_checks/%Y/%m/', null=True, blank=True, verbose_name="รูปถ่ายเช็ค")
    status = models.CharField(max_length=20, choices=[('PENDING', 'รอตรวจสอบ'), ('VERIFIED', 'ตรวจสอบแล้ว')], default='PENDING', verbose_name="สถานะการตรวจ")
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.transfer_slip:
            try:
                img = Image.open(self.transfer_slip.path)
                if img.height > 800 or img.width > 800:
                    img.thumbnail((800, 800))
                    img.save(self.transfer_slip.path, quality=85, optimize=True)
            except Exception: pass
        if self.check_slip:
            try:
                img = Image.open(self.check_slip.path)
                if img.height > 800 or img.width > 800:
                    img.thumbnail((800, 800))
                    img.save(self.check_slip.path, quality=85, optimize=True)
            except Exception: pass

class CustomerLead(models.Model):
    CHANNEL_CHOICES = [
        ('FACEBOOK', '🔵 Facebook'),
        ('LINE', '🟢 LINE / LINE OA'),
        ('PHONE', '📞 โทรศัพท์ติดต่อ'),
        ('WALKIN', '🚶 หน้าร้าน / เข้ามาดูงาน'),
        ('OTHER', '🌐 ช่องทางอื่นๆ')
    ]
    STATUS_CHOICES = [
        ('NEW', 'ติดต่อใหม่ (New)'),
        ('FOLLOW_UP', 'กำลังเจรจา (Follow Up)'),
        ('QUOTED', 'เสนอราคาแล้ว (Quoted)'),
        ('WON', 'ปิดการขายสำเร็จ (Won)'),
        ('LOST', 'ยกเลิก/ไม่สนใจ (Lost)')
    ]

    code = models.CharField(max_length=20, unique=True, verbose_name="รหัสลูกค้า (Lead ID)")
    date = models.DateTimeField(default=timezone.now, verbose_name="วันที่ติดต่อล่าสุด")
    customer_name = models.CharField(max_length=200, verbose_name="ชื่อลูกค้า / โปรไฟล์")
    phone = models.CharField(max_length=50, blank=True, verbose_name="เบอร์ติดต่อ")
    channel = models.CharField(max_length=20, choices=CHANNEL_CHOICES, default='LINE', verbose_name="ช่องทางที่ติดต่อเข้ามา")
    requirements = models.TextField(blank=True, verbose_name="รายละเอียด/ความต้องการของลูกค้า")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='NEW', verbose_name="สถานะลูกค้า")
    employee = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, verbose_name="พนักงานขายผู้ดูแล")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.code or 'No-Code'} - {self.customer_name or 'No-Name'}"

class Appointment(models.Model):
    TYPE_CHOICES = [
        ('PRE_BOOKED', 'นัดหมายล่วงหน้า (Appointment)'),
        ('WALK_IN', 'เข้ามาหน้าร้าน (Walk-in)')
    ]
    STATUS_CHOICES = [
        ('SCHEDULED', '⏳ รอดำเนินการ'),
        ('COMPLETED', '🤝 สำเร็จ / เข้ามาแล้ว'),
        ('CANCELLED', '❌ ยกเลิกนัด'),
        ('NO_SHOW', '👻 ไม่มาตามนัด')
    ]

    lead = models.ForeignKey(CustomerLead, on_delete=models.CASCADE, related_name='appointments', verbose_name="ลูกค้ามุ่งหวัง")
    appointment_date = models.DateTimeField(verbose_name="วัน/เวลาที่นัดหมาย")
    appointment_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='PRE_BOOKED', verbose_name="ประเภทการติดต่อ")
    details = models.TextField(blank=True, verbose_name="รายละเอียด/หมายเหตุ")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='SCHEDULED', verbose_name="สถานะ")
    employee = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, verbose_name="พนักงานผู้รับผิดชอบ")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        lead_name = self.lead.customer_name if self.lead else "ไม่ระบุลูกค้า"
        return f"นัดหมาย {lead_name} ({self.appointment_date.strftime('%d/%m/%Y %H:%M')})"