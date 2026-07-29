from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from master_data.models import Supplier
import datetime

# 1. หมวดหมู่สินค้า
class Category(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name="ชื่อหมวดหมู่")
    def __str__(self): return self.name
    class Meta:
        verbose_name = "1. หมวดหมู่สินค้า"
        verbose_name_plural = "1. จัดการหมวดหมู่ (Categories)"

# 1.1 หมวดหมู่วัตถุดิบ
class RawMaterialCategory(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name="ชื่อหมวดหมู่วัตถุดิบ (แผนก)")
    def __str__(self): return self.name
    class Meta:
        verbose_name = "1.1 แผนกวัตถุดิบ"
        verbose_name_plural = "1.1 จัดการแผนกวัตถุดิบ"

# 🌟 [NEW] 1.2 หมวดหมู่ย่อย
class SubCategory(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name="ชื่อหมวดหมู่ย่อย")
    def __str__(self): return self.name
    class Meta:
        verbose_name = "1.2 หมวดหมู่ย่อย"
        verbose_name_plural = "1.2 จัดการหมวดหมู่ย่อย"

# 2. สินค้า
class Product(models.Model):
    PRODUCT_TYPES = [('FG', 'สินค้าสำเร็จรูป (พร้อมขาย)'), ('RM', 'วัตถุดิบ (สำหรับผลิต)')]
    product_type = models.CharField(max_length=2, choices=PRODUCT_TYPES, default='FG', verbose_name="ประเภทสินค้า")
    code = models.CharField(max_length=50, unique=True, blank=True, verbose_name="รหัสสินค้า/SKU")
    barcode = models.CharField(max_length=50, blank=True, null=True, verbose_name="บาร์โค้ด")
    name = models.CharField(max_length=200, verbose_name="ชื่อสินค้า")
    unit = models.CharField(max_length=50, blank=True, null=True, verbose_name="หน่วยนับ")
    
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="หมวดหมู่สินค้า")
    rm_category = models.ForeignKey(RawMaterialCategory, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="หมวดหมู่วัตถุดิบ (แผนก)")
    sub_category = models.ForeignKey(SubCategory, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="หมวดหมู่ย่อย") # 🌟 เพิ่มแล้ว
    
    cost_price = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="ราคาทุน")
    sell_price = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="ราคาขาย")
    stock_qty = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="จำนวนคงเหลือ")
    min_level = models.DecimalField(max_digits=12, decimal_places=2, default=5, verbose_name="จุดสั่งซื้อ (Low Stock)")
    
    supplier = models.ForeignKey(Supplier, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="ซัพพลายเออร์หลัก (Legacy)")
    image = models.ImageField(upload_to='products/', blank=True, null=True, verbose_name="รูปสินค้า")
    standard_blueprint = models.FileField(upload_to='standard_blueprints/', blank=True, null=True, verbose_name="ไฟล์แบบแปลนมาตรฐาน (PDF/รูปภาพ)")
    is_active = models.BooleanField(default=True, verbose_name="เปิดใช้งาน")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self): return f"{self.code} - {self.name}"

    def save(self, *args, **kwargs):
        if not self.code:
            today = datetime.date.today()
            thai_year = (today.year + 543) % 100
            year_month = f"{thai_year:02d}{today.strftime('%m')}"
            prefix = f"RM-{year_month}-" if self.product_type == 'RM' else f"PD-{year_month}-"
            last_product = Product.objects.filter(code__startswith=prefix).order_by('code').last()
            if last_product:
                try: new_running = int(last_product.code.split('-')[-1]) + 1
                except ValueError: new_running = 1
            else: new_running = 1
            self.code = f"{prefix}{new_running:03d}"
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "2. จัดการคลังสินค้า/วัตถุดิบ (Master)"
        verbose_name_plural = "2. จัดการคลังสินค้า/วัตถุดิบ (Master)"

# ==========================================
# 3. หัวเอกสารคลังสินค้า (Inventory Document)
# ==========================================
class InventoryDoc(models.Model):
    DOC_TYPES = [('GR', 'ใบรับสินค้า (Goods Receipt)'), ('GI', 'ใบเบิกสินค้า (Goods Issue)')]
    doc_no = models.CharField(max_length=50, unique=True, blank=True, verbose_name="เลขที่เอกสาร")
    doc_type = models.CharField(max_length=2, choices=DOC_TYPES, verbose_name="ประเภทเอกสาร")
    po_reference = models.ForeignKey('purchasing.PurchaseOrder', on_delete=models.SET_NULL, null=True, blank=True, related_name='receipt_docs', verbose_name="อ้างอิงใบสั่งซื้อ (PO)")
    reference = models.CharField(max_length=100, blank=True, verbose_name="อ้างอิงอื่นๆ (เช่น ทะเบียนรถ, ใบส่งของ)")
    description = models.TextField(blank=True, verbose_name="หมายเหตุ")
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name="ผู้ทำรายการ")
    created_at = models.DateTimeField(default=timezone.now, verbose_name="วันที่เอกสาร")

    def save(self, *args, **kwargs):
        if not self.doc_no:
            today = datetime.date.today()
            thai_year = (today.year + 543) % 100
            year_month = f"{thai_year:02d}{today.strftime('%m')}"
            prefix = f"{self.doc_type}-{year_month}-"
            last_doc = InventoryDoc.objects.filter(doc_no__startswith=prefix).order_by('doc_no').last()
            if last_doc:
                try: running_number = int(last_doc.doc_no.split('-')[-1]) + 1
                except ValueError: running_number = 1
            else: running_number = 1
            self.doc_no = f"{prefix}{running_number:03d}"
        super().save(*args, **kwargs)

    def __str__(self): return f"{self.doc_no} ({self.get_doc_type_display()})"
    class Meta:
        verbose_name = "3. เอกสารคลังสินค้า"
        verbose_name_plural = "3. เอกสารคลังสินค้า (Docs)"

# ==========================================
# 4. รายการเคลื่อนไหว (Stock Movement)
# ==========================================
class StockMovement(models.Model):
    doc = models.ForeignKey(InventoryDoc, on_delete=models.CASCADE, related_name='movements', verbose_name="เลขที่เอกสาร", null=True, blank=True)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, verbose_name="สินค้า")
    
    # 🌟 [UPDATE] ปลดล็อคให้รองรับทศนิยม 2 ตำแหน่ง 🌟
    quantity = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="จำนวน")
    
    movement_type = models.CharField(max_length=10, choices=[('IN', 'เข้า'), ('OUT', 'ออก')], verbose_name="ประเภท")
    reference_doc = models.CharField(max_length=50, blank=True, verbose_name="อ้างอิงเดิม (Legacy)")
    note = models.TextField(blank=True, verbose_name="หมายเหตุ")
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name="ผู้ทำรายการ")
    created_at = models.DateTimeField(default=timezone.now, verbose_name="เวลาบันทึก")

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.movement_type == 'IN': self.product.stock_qty += self.quantity
        elif self.movement_type == 'OUT': self.product.stock_qty -= self.quantity
        self.product.save()

    def __str__(self): return f"{self.product.name} ({self.movement_type} : {self.quantity})"
    class Meta:
        verbose_name = "4. รายการสินค้าในเอกสาร"
        verbose_name_plural = "4. รายการเคลื่อนไหว (Details)"

class FinishedGood(Product):
    class Meta: 
        proxy = True
        verbose_name = "2.1 แคตตาล็อกสินค้าพร้อมขาย (สำหรับฝ่ายขาย)"
        verbose_name_plural = "2.1 แคตตาล็อกสินค้าพร้อมขาย (สำหรับฝ่ายขาย)"

class RawMaterial(Product):
    class Meta: proxy = True; verbose_name = "2.2 วัตถุดิบ (RM)"; verbose_name_plural = "2.2 วัตถุดิบ (RM)"

class ProductSupplier(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='multi_suppliers', verbose_name="วัตถุดิบ/สินค้า")
    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE, related_name='supplied_products', verbose_name="ร้านค้า")
    supplier_part_no = models.CharField(max_length=50, blank=True, verbose_name="รหัสสินค้าของร้านค้า")
    cost_price = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="ราคาทุน (จากร้านนี้)")
    is_default = models.BooleanField(default=False, verbose_name="เป็นร้านค้าหลัก")
    class Meta:
        verbose_name = "2.3 รายชื่อร้านค้าสำหรับสินค้า"
        verbose_name_plural = "2.3 ร้านค้าแบบ Multi-source"
        unique_together = ('product', 'supplier')
    def __str__(self): return f"{self.supplier.name} - {self.product.name}"

class SupplierPriceHistory(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='price_histories', verbose_name="วัตถุดิบ")
    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE, verbose_name="ร้านค้า")
    old_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="ราคาเดิม")
    new_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="ราคาใหม่")
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name="ผู้แก้ไข")
    updated_at = models.DateTimeField(auto_now_add=True, verbose_name="วันที่อัปเดต")
    class Meta:
        verbose_name = "2.4 ประวัติราคาซื้อ"
        verbose_name_plural = "2.4 ประวัติราคาจากซัพพลายเออร์"
    def __str__(self): return f"{self.product.name} ({self.new_price})"