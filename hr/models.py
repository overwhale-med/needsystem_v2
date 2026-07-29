from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
import datetime

# --- Master Data HR ---
class Department(models.Model):
    name = models.CharField(max_length=100, verbose_name="ชื่อแผนก")
    # 🌟 [NEW] เพิ่มฟิลด์ parent เพื่อทำระบบ แผนกหลัก-แผนกย่อย 🌟
    parent = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='sub_departments', verbose_name="สังกัดแผนกหลัก (ถ้ามี)")

    def __str__(self):
        # ถ้ามีแผนกแม่ ให้โชว์แบบ "แผนกแม่ > แผนกลูก"
        if self.parent:
            return f"{self.parent.name} > {self.name}"
        return self.name

    class Meta: verbose_name_plural = "ข้อมูลแผนก"

class Position(models.Model):
    title = models.CharField(max_length=100, verbose_name="ชื่อตำแหน่ง")
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, verbose_name="สังกัดแผนก")
    def __str__(self): return f"{self.title} ({self.department})"
    class Meta: verbose_name_plural = "ข้อมูลตำแหน่ง"

class EmployeeType(models.Model):
    name = models.CharField(max_length=50, verbose_name="ประเภทพนักงาน")
    def __str__(self): return self.name
    class Meta: verbose_name_plural = "ข้อมูลประเภทพนักงาน"

# ==========================================
# 🌟 ระบบกลุ่มและกองทุนทีม (New 2026) 🌟
# ==========================================
class SalesGroup(models.Model):
    GROUP_TYPES = [
        ('EXECUTIVE', 'กลุ่มผู้บริหาร'),
        ('TEAM', 'กลุ่มทำงาน'),
        ('INDEPENDENT', 'พนักงานขายอิสระ')
    ]
    name = models.CharField(max_length=100, unique=True, verbose_name="ชื่อกลุ่ม/ทีม")
    group_type = models.CharField(max_length=20, choices=GROUP_TYPES, verbose_name="ประเภทกลุ่ม")
    commission_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0.00, verbose_name="ค่าคอมฯจากยอดขาย (%)")
    # 🌟 [NEW] เพิ่มช่องค่าตอบแทนเหมาจ่าย สำหรับงานตรวจแบบแปลน/ผลิต
    flat_rate_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, verbose_name="ค่าตอบแทนเหมาจ่าย (บาท/งาน)")

    # สัดส่วนการแบ่งเงิน กลุ่มทำงาน
    share_leader = models.DecimalField(max_digits=5, decimal_places=2, default=0.00, verbose_name="ส่วนแบ่งหัวหน้า (%)")
    share_level1 = models.DecimalField(max_digits=5, decimal_places=2, default=0.00, verbose_name="ส่วนแบ่งระดับ 1 (%)")
    share_level2 = models.DecimalField(max_digits=5, decimal_places=2, default=0.00, verbose_name="ส่วนแบ่งระดับ 2 (%)")

    # 🌟 สัดส่วนการแบ่งเงิน กลุ่มผู้บริหาร 1-5 🌟
    share_exec1 = models.DecimalField(max_digits=5, decimal_places=2, default=0.00, verbose_name="ส่วนแบ่งผู้บริหารคนที่ 1 (%)")
    share_exec2 = models.DecimalField(max_digits=5, decimal_places=2, default=0.00, verbose_name="ส่วนแบ่งผู้บริหารคนที่ 2 (%)")
    share_exec3 = models.DecimalField(max_digits=5, decimal_places=2, default=0.00, verbose_name="ส่วนแบ่งผู้บริหารคนที่ 3 (%)")
    share_exec4 = models.DecimalField(max_digits=5, decimal_places=2, default=0.00, verbose_name="ส่วนแบ่งผู้บริหารคนที่ 4 (%)")
    share_exec5 = models.DecimalField(max_digits=5, decimal_places=2, default=0.00, verbose_name="ส่วนแบ่งผู้บริหารคนที่ 5 (%)")

    # กองทุน
    share_fund = models.DecimalField(max_digits=5, decimal_places=2, default=0.00, verbose_name="เข้ากองทุนกลุ่ม (%)")

    fund_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, verbose_name="ยอดเงินกองทุนคงเหลือ")

    def __str__(self): return f"{self.name} ({self.get_group_type_display()})"
    class Meta: verbose_name_plural = "จัดการกลุ่มขายและกองทุน"


# --- Employee Core ---
class Employee(models.Model):
    STATUS_CHOICES = [('probation', 'ทดลองงาน'), ('permanent', 'พนักงานประจำ'), ('resigned', 'ลาออก')]
    GENDER_CHOICES = [('M', 'ชาย'), ('F', 'หญิง')]

    user = models.OneToOneField(User, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="User Account")
    emp_id = models.CharField(max_length=20, unique=True, verbose_name="รหัสพนักงาน")
    prefix = models.CharField(max_length=20, verbose_name="คำนำหน้า", default="คุณ")
    first_name = models.CharField(max_length=100, verbose_name="ชื่อจริง (ไทย)")
    last_name = models.CharField(max_length=100, verbose_name="นามสกุล (ไทย)")
    nickname = models.CharField(max_length=50, blank=True, verbose_name="ชื่อเล่น")
    id_card = models.CharField(max_length=13, blank=True, verbose_name="เลขบัตรประชาชน")
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES, verbose_name="เพศ")
    birth_date = models.DateField(null=True, blank=True, verbose_name="วันเกิด")
    address = models.TextField(blank=True, verbose_name="ที่อยู่ปัจจุบัน")
    phone = models.CharField(max_length=20, verbose_name="เบอร์โทรศัพท์")

    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, verbose_name="แผนก")
    position = models.ForeignKey(Position, on_delete=models.SET_NULL, null=True, verbose_name="ตำแหน่ง")
    emp_type = models.ForeignKey(EmployeeType, on_delete=models.SET_NULL, null=True, verbose_name="ประเภทการจ้าง")
    start_date = models.DateField(verbose_name="วันที่เริ่มงาน", default=timezone.now)
    resign_date = models.DateField(null=True, blank=True, verbose_name="วันที่ลาออก")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='probation', verbose_name="สถานะภาพ")

    salary = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="เงินเดือนปัจจุบัน")
    social_security_id = models.CharField(max_length=20, blank=True, verbose_name="เลขประกันสังคม")
    bank_account_no = models.CharField(max_length=20, blank=True, verbose_name="เลขที่บัญชี (เงินเดือน)")
    photo = models.ImageField(upload_to='employees/', blank=True, verbose_name="รูปถ่าย")
    signature = models.ImageField(upload_to='signatures/', blank=True, null=True, verbose_name="รูปลายเซ็นต์ (สำหรับอนุมัติ)")

    # 🌟 ฟิลด์โครงสร้างทีม (เชื่อมกับ SalesGroup) 🌟
    sales_group = models.ForeignKey(SalesGroup, on_delete=models.SET_NULL, null=True, blank=True, related_name='members', verbose_name="สังกัดทีมขาย")
    ROLE_CHOICES = [('LEADER', 'หัวหน้ากลุ่ม'), ('LEVEL1', 'พนักงานระดับ 1'), ('LEVEL2', 'พนักงานระดับ 2'), ('MEMBER', 'สมาชิก/อิสระ')]
    group_role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='MEMBER', verbose_name="บทบาทในทีม")

    # 🌟 [NEW] ฟิลด์เชื่อมโยงกับทีมช่างผลิต 🌟
    production_team = models.ForeignKey('manufacturing.ProductionTeam', on_delete=models.SET_NULL, null=True, blank=True, verbose_name="สังกัดทีมช่างผลิต")

    # (ของเดิม) Network & Rank
    introducer = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='downlines', verbose_name='ผู้แนะนำ (Upline)')
    RANK_CHOICES = [('member', 'Member'), ('supervisor', 'Supervisor'), ('manager', 'Manager'), ('director', 'Director')]
    business_rank = models.CharField(max_length=20, choices=RANK_CHOICES, default='member', verbose_name='ระดับธุรกิจเก่า')
    commission_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0.00, verbose_name='เรทคอมฯส่วนตัวเดิม')
    bank_name = models.CharField(max_length=100, blank=True, null=True, verbose_name='ธนาคาร (รับคอมมิชชั่น)')
    bank_account = models.CharField(max_length=20, blank=True, null=True, verbose_name='เลขบัญชี (รับคอมมิชชั่น)')

    def __str__(self): return f"{self.emp_id} - {self.first_name} {self.last_name}"
    class Meta: verbose_name_plural = "ข้อมูลพนักงาน"

# ==========================================
# 🌟 ระบบภารกิจผู้บริหาร และ การเบิกกองทุน 🌟
# ==========================================
class CompanySalesTarget(models.Model):
    year = models.IntegerField(verbose_name="ปี ค.ศ.")
    month = models.IntegerField(verbose_name="เดือน")
    target_amount = models.DecimalField(max_digits=15, decimal_places=2, default=50000000.00, verbose_name="เป้าหมายยอดขายบริษัท")
    current_sales = models.DecimalField(max_digits=15, decimal_places=2, default=0.00, verbose_name="ยอดขายปัจจุบัน")
    is_unlocked = models.BooleanField(default=False, verbose_name="บรรลุเป้าหมาย (ปลดล็อคคอมผู้บริหารแล้ว)")
    class Meta:
        unique_together = ('year', 'month')
        verbose_name_plural = "เป้าหมายยอดขายบริษัท (ภารกิจผู้บริหาร)"

class FundWithdrawalRequest(models.Model):
    STATUS_CHOICES = [('VOTING', 'รอสมาชิกในกลุ่มยืนยัน'), ('PENDING', 'รอผู้บริหารอนุมัติ'), ('APPROVED', 'อนุมัติแล้ว'), ('REJECTED', 'ไม่อนุมัติ')]
    group = models.ForeignKey(SalesGroup, on_delete=models.CASCADE, verbose_name="กลุ่มที่ขอเบิก")
    requester = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='fund_requests', verbose_name="พนักงานผู้ขอเบิก")
    amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="จำนวนเงิน")
    reason = models.TextField(verbose_name="วัตถุประสงค์การใช้เงิน")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='VOTING', verbose_name="สถานะ")
    created_at = models.DateTimeField(auto_now_add=True)
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="ผู้บริหารที่อนุมัติ")
    class Meta: verbose_name_plural = "คำร้องขอเบิกเงินกองทุนกลุ่ม"

class FundWithdrawalVote(models.Model):
    request = models.ForeignKey(FundWithdrawalRequest, on_delete=models.CASCADE, related_name='votes')
    voter = models.ForeignKey(Employee, on_delete=models.CASCADE, verbose_name="ผู้ลงมติ")
    is_confirmed = models.BooleanField(default=False, verbose_name="กดยืนยันแล้ว")
    confirmed_at = models.DateTimeField(null=True, blank=True)

class FundTransaction(models.Model):
    group = models.ForeignKey(SalesGroup, on_delete=models.CASCADE, related_name='transactions')
    transaction_type = models.CharField(max_length=20, choices=[('IN', 'รายรับ (คอมมิชชัน)'), ('OUT', 'รายจ่าย (เบิกใช้)')])
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

# --- ส่วนอื่นๆ คงเดิม ---
class Attendance(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, verbose_name="พนักงาน")
    date = models.DateField(verbose_name="วันที่")
    time_in = models.TimeField(null=True, blank=True, verbose_name="เวลาเข้างาน")
    time_out = models.TimeField(null=True, blank=True, verbose_name="เวลาออกงาน")
    total_hours = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name="ชั่วโมงทำงานรวม")
    is_late = models.BooleanField(default=False, verbose_name="มาสาย")
    is_overtime = models.BooleanField(default=False, verbose_name="มี OT")
    note = models.TextField(blank=True, verbose_name="หมายเหตุ")

    # 🌟 [NEW] เพิ่มฟิลด์สำหรับเก็บพิกัด GPS ตอนเช็คอิน 🌟
    latitude = models.CharField(max_length=50, null=True, blank=True, verbose_name="ละติจูด (Latitude)")
    longitude = models.CharField(max_length=50, null=True, blank=True, verbose_name="ลองจิจูด (Longitude)")

    def save(self, *args, **kwargs):
        WORK_START_TIME = datetime.time(8, 30, 0)
        if self.time_in:
            if self.time_in > WORK_START_TIME: self.is_late = True
            else: self.is_late = False
        if self.time_in and self.time_out:
            dummy_date = datetime.date(2000, 1, 1)
            dt_in = datetime.datetime.combine(dummy_date, self.time_in)
            dt_out = datetime.datetime.combine(dummy_date, self.time_out)
            duration = dt_out - dt_in
            self.total_hours = duration.total_seconds() / 3600
        super().save(*args, **kwargs)

    class Meta: verbose_name_plural = "บันทึกเวลาทำงาน"

class LeaveRequest(models.Model):
    LEAVE_TYPES = [('sick', 'ลาป่วย'), ('business', 'ลากิจ'), ('vacation', 'ลาพักร้อน'), ('other', 'อื่นๆ')]
    STATUS_CHOICES = [('pending', 'รออนุมัติ'), ('approved', 'อนุมัติแล้ว'), ('rejected', 'ไม่อนุมัติ')]
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, verbose_name="พนักงาน")
    leave_type = models.CharField(max_length=20, choices=LEAVE_TYPES, verbose_name="ประเภทการลา")
    start_date = models.DateField(verbose_name="วันที่เริ่มลา")
    end_date = models.DateField(verbose_name="ถึงวันที่")
    reason = models.TextField(verbose_name="เหตุผลการลา")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name="สถานะ")
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="ผู้อนุมัติ")
    approved_date = models.DateTimeField(null=True, blank=True, verbose_name="วันที่อนุมัติ")
    class Meta: verbose_name_plural = "รายการใบลา"

class Payslip(models.Model):
    MONTH_CHOICES = [(i, m) for i, m in enumerate(['มกราคม', 'กุมภาพันธ์', 'มีนาคม', 'เมษายน', 'พฤษภาคม', 'มิถุนายน', 'กรกฎาคม', 'สิงหาคม', 'กันยายน', 'ตุลาคม', 'พฤศจิกายน', 'ธันวาคม'], 1)]
    STATUS_CHOICES = [('draft', 'ร่าง'), ('published', 'อนุมัติ'), ('paid', 'จ่ายแล้ว')]
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, verbose_name="พนักงาน")
    year = models.IntegerField(default=timezone.now().year, verbose_name="ปี ค.ศ.")
    month = models.IntegerField(choices=MONTH_CHOICES, verbose_name="เดือน")
    base_salary = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="เงินเดือน")
    ot_pay = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="OT")
    bonus = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="โบนัส/ค่าคอมมิชชัน")
    other_income = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="รายได้อื่นๆ")
    tax = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="ภาษี")
    social_security = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="ประกันสังคม")
    leave_deduction = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="หักลา")
    other_deduction = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="หักอื่นๆ")
    net_salary = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="สุทธิ")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft', verbose_name="สถานะ")
    payment_date = models.DateField(null=True, blank=True, verbose_name="วันที่โอน")
    note = models.TextField(blank=True, verbose_name="หมายเหตุ")
    def save(self, *args, **kwargs):
        if self.base_salary == 0: self.base_salary = self.employee.salary
        total_income = self.base_salary + self.ot_pay + self.bonus + self.other_income
        total_deduction = self.tax + self.social_security + self.leave_deduction + self.other_deduction
        self.net_salary = total_income - total_deduction
        super().save(*args, **kwargs)
    class Meta: verbose_name_plural = "จัดการสลิปเงินเดือน"

class CommissionLog(models.Model):
    recipient = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='commissions_received', verbose_name="ผู้รับเงิน")
    source_employee = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, verbose_name="จากยอดขายของ")
    level = models.IntegerField(verbose_name="ชั้นที่", default=1)
    amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="จำนวนเงิน")
    sale_ref_id = models.CharField(max_length=50, blank=True, verbose_name="อ้างอิงบิล")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="วันที่ได้รับ")
    class Meta: verbose_name_plural = "ประวัติค่าคอมมิชชั่นบุคคล"