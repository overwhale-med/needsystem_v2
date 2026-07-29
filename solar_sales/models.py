from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User
from decimal import Decimal
import datetime

from master_data.models import Customer, Supplier
from hr.models import Employee

# ==========================================
# 📦 1. คลังสินค้าโซล่าเซลล์ (Solar Inventory)
# ==========================================
class SolarProductCategory(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name="หมวดหมู่แพ็กเกจ/สินค้า (FG)")
    def __str__(self): return self.name
    class Meta:
        verbose_name_plural = "หมวดหมู่สินค้า (FG)"

class SolarRawMaterialCategory(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name="หมวดหมู่วัตถุดิบ/อุปกรณ์ (RM)")
    def __str__(self): return self.name
    class Meta:
        verbose_name_plural = "หมวดหมู่วัตถุดิบ (RM)"

class SolarProduct(models.Model):
    PRODUCT_TYPES = [('FG', 'แพ็กเกจโซล่า (ขาย)'), ('RM', 'วัตถุดิบ/อุปกรณ์ (เบิก/ซื้อ)')]
    product_type = models.CharField(max_length=2, choices=PRODUCT_TYPES, default='FG', verbose_name="ประเภทสินค้า")
    code = models.CharField(max_length=50, unique=True, blank=True, verbose_name="รหัสสินค้า (SKU)")
    name = models.CharField(max_length=200, verbose_name="ชื่อสินค้า/แพ็กเกจ")
    unit = models.CharField(max_length=50, blank=True, null=True, verbose_name="หน่วยนับ")

    category = models.ForeignKey(SolarProductCategory, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="หมวดหมู่ (FG)")
    rm_category = models.ForeignKey(SolarRawMaterialCategory, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="หมวดหมู่ (RM)")

    cost_price = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="ราคาทุน")
    sell_price = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="ราคาขาย")
    stock_qty = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="จำนวนคงเหลือ")
    min_level = models.DecimalField(max_digits=12, decimal_places=2, default=5, verbose_name="จุดสั่งซื้อ (Low Stock)")

    is_active = models.BooleanField(default=True, verbose_name="เปิดใช้งาน")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self): return f"{self.code} - {self.name}"

    def save(self, *args, **kwargs):
        if not self.code:
            today = datetime.date.today()
            thai_year = (today.year + 543) % 100
            year_month = f"{thai_year:02d}{today.strftime('%m')}"
            prefix = f"SR-{year_month}-" if self.product_type == 'RM' else f"SP-{year_month}-"
            last_product = SolarProduct.objects.filter(code__startswith=prefix).order_by('code').last()
            if last_product:
                try: new_running = int(last_product.code.split('-')[-1]) + 1
                except ValueError: new_running = 1
            else: new_running = 1
            self.code = f"{prefix}{new_running:03d}"
        super().save(*args, **kwargs)

class SolarStockMovement(models.Model):
    product = models.ForeignKey(SolarProduct, on_delete=models.CASCADE, verbose_name="สินค้าโซล่า")
    quantity = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="จำนวน")
    movement_type = models.CharField(max_length=10, choices=[('IN', 'เข้า'), ('OUT', 'ออก')], verbose_name="ประเภท")
    reference_doc = models.CharField(max_length=50, blank=True, verbose_name="อ้างอิงเอกสาร")
    created_at = models.DateTimeField(default=timezone.now, verbose_name="วันที่ทำรายการ (dd/mm/yyyy)")

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.movement_type == 'IN': self.product.stock_qty += self.quantity
        elif self.movement_type == 'OUT': self.product.stock_qty -= self.quantity
        self.product.save()


# ==========================================
# 📝 2. ระบบขายโซล่าเซลล์ (Solar Sales)
# ==========================================
class SolarQuotation(models.Model):
    STATUS_CHOICES = [
        ('DRAFT', 'รออนุมัติ'), ('APPROVED', 'อนุมัติแล้ว'),
        ('CONVERTED', 'เปิดบิลขายแล้ว'), ('CANCELLED', 'ยกเลิกแล้ว')
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
    vat_type = models.CharField(max_length=10, choices=VAT_CHOICES, default='NONE', verbose_name="ประเภทภาษี")
    vat_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="ยอด VAT 7%")
    grand_total = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="ยอดสุทธิ (Grand Total)")

    payment_terms = models.TextField(
        default="- ชำระเงินมัดจำ 50% ของยอดรวมเพื่อยืนยันการสั่งซื้อ\n- ส่วนที่เหลือชำระก่อนการติดตั้ง",
        verbose_name="เงื่อนไขการชำระเงิน (Payment Terms)"
    )

    deposit_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="มัดจำ")
    deposit_method = models.CharField(max_length=20, default='TRANSFER', verbose_name="ช่องทางรับเงิน")
    deposit_date = models.DateField(null=True, blank=True, verbose_name="วันที่รับเงินมัดจำ")
    deposit_slip = models.ImageField(upload_to='solar_deposits/', null=True, blank=True, verbose_name="สลิปโอนเงิน")
    is_deposit_paid = models.BooleanField(default=False)
    is_deposit_verified = models.BooleanField(default=False, verbose_name="บัญชีตรวจสอบแล้ว")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT')
    note = models.TextField(blank=True, verbose_name="หมายเหตุ")

    # 🌟 [FIXED] เพิ่มฟังก์ชันคำนวณยอดค้างชำระ (Balance Due) 🌟
    @property
    def balance_due(self):
        return self.grand_total - self.deposit_amount

    def save(self, *args, **kwargs):
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