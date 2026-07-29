from django.db import models
from django.utils import timezone
import datetime

# ดึงข้อมูล Master Data จากแอปอื่นๆ มาใช้ร่วมกัน
from master_data.models import Supplier
from inventory.models import Product
from hr.models import Employee

class SolarPurchaseOrder(models.Model):
    STATUS_CHOICES = [
        ('DRAFT', 'ร่าง (รอผู้จัดการอนุมัติ)'),
        ('APPROVED', 'อนุมัติแล้ว (ดำเนินการสั่งซื้อ)'),
        ('CANCELLED', 'ยกเลิก')
    ]

    PAYMENT_STATUS = [('PENDING', 'รอชำระเงิน'), ('DEPOSIT', 'จ่ายมัดจำแล้ว'), ('PAID', 'ชำระครบแล้ว')]
    RECEIPT_STATUS = [('PENDING', 'รอรับเข้าคลัง'), ('PARTIAL', 'รับของบางส่วน'), ('COMPLETED', 'รับของครบถ้วน')]

    # 🌟 รหัส POS- (Purchase Order Solar)
    code = models.CharField(max_length=20, unique=True, verbose_name="เลขที่ใบสั่งซื้อโซล่า (POS)")
    
    # 🌟 รองรับ Supplier ทั้งในระบบและนอกระบบ (Free Text)
    supplier = models.ForeignKey(Supplier, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="ผู้ขาย (Supplier)")
    supplier_name_free_text = models.CharField(max_length=255, blank=True, verbose_name="ชื่อร้านค้า (กรณีเร่งด่วน/ไม่อยู่ในระบบ)")
    
    buyer = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, verbose_name="ผู้จัดซื้อ")

    date = models.DateField(default=timezone.now, verbose_name="วันที่สั่งซื้อ")
    expected_date = models.DateField(null=True, blank=True, verbose_name="กำหนดรับของ")
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="ยอดรวมสุทธิ")

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT', verbose_name="สถานะเอกสาร")
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS, default='PENDING', verbose_name="สถานะชำระเงิน")
    receipt_status = models.CharField(max_length=20, choices=RECEIPT_STATUS, default='PENDING', verbose_name="สถานะรับของเข้าคลัง")

    note = models.TextField(blank=True, verbose_name="หมายเหตุ")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "ใบสั่งซื้อโซล่า (POS)"
        verbose_name_plural = "จัดการใบสั่งซื้อโซล่า"

    def __str__(self):
        sup_name = self.supplier.name if self.supplier else self.supplier_name_free_text
        return f"{self.code} - {sup_name}"

    def save(self, *args, **kwargs):
        # 🌟 Auto-generate รหัส POS-YYMM-XXX
        if not self.code:
            today = datetime.date.today()
            thai_year = (today.year + 543) % 100
            prefix = f"POS-{thai_year:02d}{today.strftime('%m')}"
            
            last_po = SolarPurchaseOrder.objects.filter(code__startswith=prefix).order_by('code').last()
            if last_po:
                try: seq = int(last_po.code.split('-')[-1]) + 1
                except: seq = 1
            else:
                seq = 1
            self.code = f"{prefix}-{seq:03d}"
        super().save(*args, **kwargs)


class SolarPurchaseOrderItem(models.Model):
    po = models.ForeignKey(SolarPurchaseOrder, related_name='items', on_delete=models.CASCADE)
    
    # 🌟 รองรับสินค้าในคลัง และ สินค้าเฉพาะกิจ (Free Text)
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="รหัสวัตถุดิบ (จากคลัง)")
    item_name_free_text = models.CharField(max_length=255, blank=True, verbose_name="ชื่อสินค้า (กรณีด่วน/ไม่มีรหัสคลัง)")

    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=1, verbose_name="จำนวนที่สั่ง")
    received_qty = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="จำนวนที่รับเข้าคลังแล้ว")

    unit_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="ราคาต่อหน่วย")
    total_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="รวมเป็นเงิน")

    def save(self, *args, **kwargs):
        # 🌟 คำนวณราคารวมอัตโนมัติ
        self.total_cost = self.quantity * self.unit_cost
        super().save(*args, **kwargs)

    def __str__(self):
        name = self.product.name if self.product else self.item_name_free_text
        return f"{name} ({self.quantity})"