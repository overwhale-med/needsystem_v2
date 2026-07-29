from django.contrib import admin
from .models import Employee, Department, Position, EmployeeType, Attendance, LeaveRequest, Payslip, CommissionLog

admin.site.site_header = "NEED System Administration"
admin.site.site_title = "NEED System Portal"
admin.site.index_title = "ระบบจัดการข้อมูลหลังบ้าน"

# 1. จัดการพนักงาน
@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    # ✅ เพิ่ม business_rank ในตารางรวม เพื่อให้ดูง่ายว่าใครระดับไหน
    list_display = ('emp_id', 'first_name', 'last_name', 'department', 'business_rank', 'status')
    
    # ✅ เพิ่มตัวกรอง business_rank
    list_filter = ('department', 'business_rank', 'status', 'emp_type')
    
    search_fields = ('first_name', 'last_name', 'emp_id')
    ordering = ('emp_id',)

    fieldsets = (
        ('ข้อมูลทั่วไป', {'fields': (('emp_id', 'user'), ('status', 'emp_type'), ('photo', 'signature'))}),
        
        ('ประวัติส่วนตัว', {'fields': (('prefix', 'first_name', 'last_name', 'nickname'), ('gender', 'birth_date'), 'id_card', 'phone', 'address')}),
        
        ('การทำงาน', {'fields': (('department', 'position'), ('start_date', 'resign_date'))}),
        
        # ✅ เพิ่มหมวดใหม่: โครงสร้างทีม & ผลตอบแทน (Sales)
        ('โครงสร้างทีม & ระดับ (Sales Team)', {
            'fields': (
                ('business_rank', 'commission_rate'), # ระดับ และ % คอมมิชชั่น
                'introducer' # หัวหน้าทีม/ผู้แนะนำ
            )
        }),
        
        # บัญชีเงินเดือน (Payroll)
        ('บัญชีเงินเดือน', {
            'fields': ('salary', 'bank_account_no', 'social_security_id'), 
            'classes': ('collapse',)
        }),

        # ✅ บัญชีรับค่าคอมมิชชั่น (แยกกับเงินเดือน)
        ('บัญชีรับค่าคอมมิชชั่น', {
            'fields': (('bank_name', 'bank_account'),), 
            'classes': ('collapse',)
        }),
    )

# 2. Master Data
# 🌟 [UPDATE] อัปเดตหน้าจัดการ Department ให้โชว์แผนกหลัก-ย่อย 🌟
@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin): 
    list_display = ('name', 'parent')
    list_filter = ('parent',)
    search_fields = ('name',)

@admin.register(Position)
class PositionAdmin(admin.ModelAdmin):
    list_display = ('title', 'department')
    list_filter = ('department',)

@admin.register(EmployeeType)
class EmployeeTypeAdmin(admin.ModelAdmin): pass

# 3. เวลาและการลา
@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ('date', 'employee', 'time_in', 'time_out', 'is_late', 'total_hours')
    list_filter = ('date', 'employee__department')
    date_hierarchy = 'date'

@admin.register(LeaveRequest)
class LeaveRequestAdmin(admin.ModelAdmin):
    list_display = ('employee', 'leave_type', 'start_date', 'status')
    list_filter = ('status', 'leave_type')
    actions = ['approve_leaves', 'reject_leaves']

    def approve_leaves(self, request, queryset): queryset.update(status='approved')
    def reject_leaves(self, request, queryset): queryset.update(status='rejected')

# 4. เงินเดือน (Payroll)
@admin.register(Payslip)
class PayslipAdmin(admin.ModelAdmin):
    list_display = ('employee', 'month_year_display', 'base_salary', 'net_salary', 'status')
    list_filter = ('year', 'month', 'status', 'employee__department')
    search_fields = ('employee__first_name', 'employee__emp_id')

    # จัดกลุ่มให้กรอกง่ายๆ
    fieldsets = (
        ('ข้อมูลหลัก', {'fields': ('employee', ('month', 'year'), 'status', 'payment_date')}),
        ('รายได้ (Income)', {'fields': (('base_salary', 'ot_pay'), ('bonus', 'other_income'))}),
        ('รายหัก (Deduction)', {'fields': (('social_security', 'tax'), ('leave_deduction', 'other_deduction'))}),
        ('สรุปยอด (Net Total)', {'fields': ('net_salary', 'note')}),
    )
    readonly_fields = ('net_salary',) # ล็อกช่องนี้ไว้ ให้ระบบคำนวณเอง

    def month_year_display(self, obj):
        return f"{obj.get_month_display()} {obj.year}"
    month_year_display.short_description = "งวดเดือน"

@admin.register(CommissionLog)
class CommissionLogAdmin(admin.ModelAdmin):
    list_display = ('recipient', 'amount', 'source_employee', 'level', 'sale_ref_id', 'created_at')
    list_filter = ('level', 'created_at')
    search_fields = ('recipient__first_name', 'sale_ref_id')