from django.contrib import admin
from django.utils.html import format_html
from .models import (
    SubcontractorTeam, SolarJob, SolarJobBOM, SolarExpense, SolarJobMedia,
    SolarServiceCategory, SolarServiceTicket, SolarServiceTicketMedia, SolarServiceLaborClaim
)

@admin.register(SubcontractorTeam)
class SubcontractorTeamAdmin(admin.ModelAdmin):
    list_display = ['name', 'leader_name', 'phone', 'is_active']
    search_fields = ['name', 'leader_name']

class SolarJobBOMInline(admin.TabularInline):
    model = SolarJobBOM
    extra = 1

# 🌟 [NEW] เพิ่ม Inline สำหรับให้แอดมินจัดการรูปภาพงานติดตั้งได้จากหน้า Job
class SolarJobMediaInline(admin.TabularInline):
    model = SolarJobMedia
    extra = 1
    readonly_fields = ['uploaded_at']

# 🌟 [NEW] สร้างเมนูแยกสำหรับ "รูปภาพผลงานติดตั้ง" (มี Thumbnail)
@admin.register(SolarJobMedia)
class SolarJobMediaAdmin(admin.ModelAdmin):
    list_display = ('image_tag', 'job', 'description', 'uploaded_by', 'uploaded_at')
    list_filter = ('uploaded_at', 'uploaded_by')
    search_fields = ('job__code', 'description')

    def image_tag(self, obj):
        if obj.image:
            return format_html('<img src="{}" style="width: 60px; height: 60px; object-fit: cover; border-radius: 8px; border: 1px solid #ccc;" />', obj.image.url)
        return "-"
    image_tag.short_description = 'ตัวอย่างรูปภาพ'

@admin.register(SolarJob)
class SolarJobAdmin(admin.ModelAdmin):
    list_display = ['code', 'quotation_ref', 'customer', 'status', 'start_date']
    list_filter = ['status']
    search_fields = ['code', 'customer__name']
    inlines = [SolarJobBOMInline, SolarJobMediaInline] # 🌟 แปะตารางรูปลงในหน้าใบสั่งงาน

@admin.register(SolarExpense)
class SolarExpenseAdmin(admin.ModelAdmin):
    list_display = ['job', 'expense_type', 'amount', 'status', 'requester']
    list_filter = ['status', 'expense_type']
    search_fields = ['job__code']

# ==========================================
# 🌟 ส่วนการจัดการระบบแจ้งซ่อมโซล่า (Solar After-Sales Service) 🌟
# ==========================================
@admin.register(SolarServiceCategory)
class SolarServiceCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name',)

# 🌟 [NEW] เพิ่ม Inline สำหรับให้แอดมินจัดการรูปแจ้งซ่อมได้จากหน้า Ticket
class SolarServiceTicketMediaInline(admin.TabularInline):
    model = SolarServiceTicketMedia
    extra = 1
    readonly_fields = ['uploaded_at']

@admin.register(SolarServiceTicket)
class SolarServiceTicketAdmin(admin.ModelAdmin):
    list_display = ('code', 'job', 'salesperson', 'issue_category', 'status', 'created_at')
    list_filter = ('status', 'issue_category', 'urgency', 'is_warranty')
    search_fields = ('code', 'job__code', 'customer_phone')
    readonly_fields = ('created_at', 'updated_at')
    inlines = [SolarServiceTicketMediaInline] # 🌟 แปะตารางรูปลงในหน้าใบแจ้งซ่อม

# 🌟 [UPDATE] อัปเกรดเมนูรูปแจ้งซ่อม ให้แสดงรูป Thumbnail ได้
@admin.register(SolarServiceTicketMedia)
class SolarServiceTicketMediaAdmin(admin.ModelAdmin):
    list_display = ('image_tag', 'ticket', 'media_type', 'uploaded_at')
    list_filter = ('media_type', 'uploaded_at')

    def image_tag(self, obj):
        if obj.file:
            return format_html('<img src="{}" style="width: 60px; height: 60px; object-fit: cover; border-radius: 8px; border: 1px solid #ccc;" />', obj.file.url)
        return "-"
    image_tag.short_description = 'ตัวอย่างรูป/วิดีโอ'

@admin.register(SolarServiceLaborClaim)
class SolarServiceLaborClaimAdmin(admin.ModelAdmin):
    list_display = ('code', 'service_ticket', 'technician_name', 'amount', 'status')
    list_filter = ('status',)
    search_fields = ('code', 'technician_name', 'service_ticket__code')