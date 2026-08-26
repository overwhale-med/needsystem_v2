from django.db import models
from django.utils import timezone
import datetime

class SolarProductCategory(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name="หมวดหมู่แพ็กเกจ/สินค้า (FG)")
    def __str__(self): return self.name
    class Meta: verbose_name_plural = "หมวดหมู่สินค้า (FG)"

class SolarRawMaterialCategory(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name="หมวดหมู่วัตถุดิบ/อุปกรณ์ (RM)")
    def __str__(self): return self.name
    class Meta: verbose_name_plural = "หมวดหมู่วัตถุดิบ (RM)"

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

    # 🌟 [NEW] เพิ่ม Property สำหรับคำนวณมูลค่าคงเหลือ 🌟
    @property
    def total_value(self):
        return self.stock_qty * self.cost_price

    def save(self, *args, **kwargs):
        if not self.code:
            today = datetime.date.today()
            thai_year = (today.year + 543) % 100
            year_month = f"{thai_year:02d}{today.strftime('%m')}"
            prefix = f"SR-{year_month}-" if self.product_type == 'RM' else f"SP-{year_month}-"
            last_product = SolarProduct.objects.filter(code__startswith=prefix).order_by('code').last()
            new_running = int(last_product.code.split('-')[-1]) + 1 if last_product else 1
            self.code = f"{prefix}{new_running:03d}"
        super().save(*args, **kwargs)

class SolarStockMovement(models.Model):
    product = models.ForeignKey(SolarProduct, on_delete=models.CASCADE, verbose_name="สินค้าโซล่า")
    quantity = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="จำนวน")
    movement_type = models.CharField(max_length=10, choices=[('IN', 'เข้า'), ('OUT', 'ออก')], verbose_name="ประเภท")
    reference_doc = models.CharField(max_length=50, blank=True, verbose_name="อ้างอิงเอกสาร")
    created_at = models.DateTimeField(default=timezone.now, verbose_name="วันที่ทำรายการ")

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.movement_type == 'IN': self.product.stock_qty += self.quantity
        elif self.movement_type == 'OUT': self.product.stock_qty -= self.quantity
        self.product.save()