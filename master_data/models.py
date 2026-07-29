from django.db import models
from django.core.validators import RegexValidator
import datetime

# --- ส่วนที่ 1: ตารางข้อมูลที่อยู่ ---
class Province(models.Model):
    name_th = models.CharField(max_length=150, verbose_name="ชื่อภาษาไทย")
    name_en = models.CharField(max_length=150, verbose_name="ชื่อภาษาอังกฤษ")
    def __str__(self): return self.name_th

class Amphure(models.Model):
    name_th = models.CharField(max_length=150, verbose_name="ชื่อภาษาไทย")
    province = models.ForeignKey(Province, on_delete=models.CASCADE, related_name='amphures')
    def __str__(self): return self.name_th

class Tambon(models.Model):
    name_th = models.CharField(max_length=150, verbose_name="ชื่อภาษาไทย")
    amphure = models.ForeignKey(Amphure, on_delete=models.CASCADE, related_name='tambons')
    zip_code = models.CharField(max_length=10, verbose_name="รหัสไปรษณีย์")
    def __str__(self): return self.name_th

# --- ส่วนที่ 2: ข้อมูลบริษัท (Company Info) ---
class CompanyInfo(models.Model):
    name_th = models.CharField(max_length=200, verbose_name="ชื่อบริษัท (ไทย)")
    name_en = models.CharField(max_length=200, verbose_name="ชื่อบริษัท (อังกฤษ)", blank=True)
    tax_id = models.CharField(max_length=20, verbose_name="เลขผู้เสียภาษี")
    branch = models.CharField(max_length=50, default="สำนักงานใหญ่", verbose_name="สาขา")
    address = models.TextField(verbose_name="ที่อยู่ (ไทย)")
    
    # 🌟 [NEW] ช่องที่อยู่ภาษาอังกฤษสำหรับออกเอกสารต่างประเทศ
    address_en = models.TextField(blank=True, verbose_name="ที่อยู่ (อังกฤษ)") 
    
    phone = models.CharField(max_length=50, blank=True, verbose_name="เบอร์โทร")
    email = models.EmailField(blank=True, verbose_name="อีเมล")
    website = models.URLField(blank=True, verbose_name="เว็บไซต์")

    logo = models.ImageField(upload_to='company/', blank=True, null=True, verbose_name="โลโก้")
    # 🌟 เพิ่มช่องอัปโหลดโลโก้สำหรับระบบโซล่าเซลล์
    solar_logo = models.ImageField(upload_to='company/', blank=True, null=True, verbose_name="โลโก้ (ระบบโซล่าเซลล์)")
    
    login_image = models.ImageField(upload_to='company/', blank=True, null=True, verbose_name="รูปหน้า Login")
    navbar_image = models.ImageField(upload_to='company/', blank=True, null=True, verbose_name="โลโก้บนแถบเมนู")
    seal = models.ImageField(upload_to='company/', blank=True, null=True, verbose_name="ตราประทับบริษัท (Seal)")

    weekly_job_quota = models.IntegerField(default=25, verbose_name="โควตางานผลิตต่อสัปดาห์ (Jobs)")

    class Meta:
        verbose_name_plural = "1. ตั้งค่าข้อมูลบริษัท"
    def __str__(self): return self.name_th

# --- ส่วนที่ 3: ข้อมูลลูกค้า (Customer) ---
class Customer(models.Model):
    code = models.CharField(max_length=20, unique=True, verbose_name="รหัสลูกค้า", blank=True)
    name = models.CharField(max_length=200, verbose_name="ชื่อลูกค้า / บริษัท")
    branch = models.CharField(max_length=100, default="สำนักงานใหญ่", blank=True, verbose_name="สาขา")
    tax_id = models.CharField(max_length=13, blank=True, null=True, verbose_name="เลขผู้เสียภาษี", validators=[RegexValidator(r'^\d{13}$', 'ต้องเป็นตัวเลข 13 หลัก')])
    contact_person = models.CharField(max_length=100, blank=True, null=True, verbose_name="ชื่อผู้ติดต่อ")
    phone = models.CharField(max_length=10, verbose_name="เบอร์โทรศัพท์", validators=[RegexValidator(r'^0\d{8,9}$', 'เบอร์โทรไม่ถูกต้อง')])
    email = models.EmailField(blank=True, null=True, verbose_name="อีเมล")
    line_id = models.CharField(max_length=50, blank=True, null=True, verbose_name="Line ID")
    address = models.CharField(max_length=255, verbose_name="ที่อยู่")
    province = models.CharField(max_length=100, blank=True, null=True, verbose_name="จังหวัด")
    district = models.CharField(max_length=100, blank=True, null=True, verbose_name="อำเภอ")
    sub_district = models.CharField(max_length=100, blank=True, null=True, verbose_name="ตำบล")
    zip_code = models.CharField(max_length=10, blank=True, null=True, verbose_name="รหัสไปรษณีย์")
    location = models.CharField(max_length=255, blank=True, null=True, verbose_name="พิกัด GPS")
    credit_limit = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="วงเงินเครดิต")
    credit_term = models.IntegerField(default=0, verbose_name="เครดิต (วัน)")
    note = models.TextField(blank=True, null=True, verbose_name="หมายเหตุ")
    is_active = models.BooleanField(default=True, verbose_name="สถานะใช้งาน")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "2. ฐานข้อมูลลูกค้า"
        ordering = ['-created_at']
    def __str__(self): return f"{self.code} - {self.name}"
    def save(self, *args, **kwargs):
        if not self.code:
            now = datetime.datetime.now()
            prefix = f"CUS-{now.strftime('%y%m')}"
            last = Customer.objects.filter(code__startswith=prefix).order_by('code').last()
            seq = int(last.code.split('-')[-1]) + 1 if last else 1
            self.code = f"{prefix}-{seq:03d}"
        super().save(*args, **kwargs)

# --- ส่วนที่ 4: ข้อมูลผู้ขาย (Supplier) ---
class Supplier(models.Model):
    code = models.CharField(max_length=20, unique=True, verbose_name="รหัสผู้ขาย")
    name = models.CharField(max_length=200, verbose_name="ชื่อบริษัท/ร้านค้า (ซัพพลายเออร์)")
    tax_id = models.CharField(max_length=20, blank=True, verbose_name="เลขประจำตัวผู้เสียภาษี")
    contact_name = models.CharField(max_length=100, blank=True, verbose_name="ชื่อผู้ติดต่อ (เซลส์)")
    phone = models.CharField(max_length=50, blank=True, verbose_name="เบอร์โทรศัพท์")
    email = models.EmailField(blank=True, null=True, verbose_name="อีเมล")
    address = models.TextField(blank=True, verbose_name="ที่อยู่ร้านค้า")
    credit_term = models.IntegerField(default=0, verbose_name="เครดิตเทอม (วัน)")

    class Meta:
        verbose_name_plural = "3. ฐานข้อมูลผู้ขาย"

    def __str__(self):
        return f"{self.code} - {self.name}"

    def save(self, *args, **kwargs):
        if not self.code:
            last_supplier = Supplier.objects.filter(code__startswith='SUP-').order_by('code').last()
            if last_supplier and last_supplier.code:
                try:
                    last_num = int(last_supplier.code.split('-')[1])
                    new_num = last_num + 1
                except (IndexError, ValueError):
                    new_num = 1
            else:
                new_num = 1
            self.code = f"SUP-{new_num:03d}"
        super().save(*args, **kwargs)

# ==========================================
# ส่วนที่ 5: เรทค่าจัดส่ง (Shipping Rate)
# ==========================================
class ShippingRate(models.Model):
    origin_branch = models.CharField(max_length=100, choices=[('บางพระ', 'บางพระ (ชลบุรี)'), ('นครปฐม', 'นครปฐม'), ('อยุธยา', 'อยุธยา')], verbose_name="สาขาต้นทาง (ผลิต)")
    destination_province = models.CharField(max_length=100, verbose_name="จังหวัดปลายทาง")
    price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="ค่าขนส่งมาตรฐาน")

    class Meta:
        verbose_name = "ตั้งค่าเรทค่าขนส่ง"
        verbose_name_plural = "4. ตั้งค่าเรทค่าขนส่ง"
        unique_together = ('origin_branch', 'destination_province')

    def __str__(self):
        return f"จาก {self.origin_branch} -> ส่ง {self.destination_province} : ฿{self.price}"