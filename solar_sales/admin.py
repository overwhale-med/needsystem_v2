from django.contrib import admin
from django.utils.html import format_html
from .models import SolarQuotation, SolarQuotationItem, SolarInvoice, SolarSurveyJob, SolarSurveyItem, SolarExpenseClaim, SolarExpenseSlip, SolarCommissionClaim, SolarCommissionTicket

class SolarQuotationItemInline(admin.TabularInline):
    model = SolarQuotationItem
    extra = 1

@admin.register(SolarQuotation)
class SolarQuotationAdmin(admin.ModelAdmin):
    list_display = ['code', 'date', 'customer', 'employee', 'grand_total', 'status']
    list_filter = ['status', 'is_deposit_paid']
    search_fields = ['code', 'customer__name']
    readonly_fields = ['code']
    inlines = [SolarQuotationItemInline]

@admin.register(SolarInvoice)
class SolarInvoiceAdmin(admin.ModelAdmin):
    list_display = ['code', 'date', 'customer', 'grand_total', 'balance_amount', 'status']
    list_filter = ['status']
    search_fields = ['code', 'customer__name']
    readonly_fields = ['code']

from .models import SolarSurveyJob, SolarCustomer, SolarSurveyImage

@admin.register(SolarCustomer)
class SolarCustomerAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'phone', 'contact_person')
    search_fields = ('code', 'name', 'phone')

class SolarSurveyImageInline(admin.TabularInline):
    model = SolarSurveyImage
    extra = 1
    readonly_fields = ['uploaded_at']

# 🌟 [NEW] สร้างเมนูแยกสำหรับ "รูปภาพสำรวจหน้างาน" (มี Thumbnail)
@admin.register(SolarSurveyImage)
class SolarSurveyImageAdmin(admin.ModelAdmin):
    list_display = ('image_tag', 'survey_job', 'description', 'uploaded_at')
    list_filter = ('uploaded_at',)
    search_fields = ('survey_job__code', 'description')

    def image_tag(self, obj):
        if obj.image:
            return format_html('<img src="{}" style="width: 60px; height: 60px; object-fit: cover; border-radius: 8px; border: 1px solid #ccc;" />', obj.image.url)
        return "-"
    image_tag.short_description = 'ตัวอย่างรูปภาพ'

@admin.register(SolarSurveyJob)
class SolarSurveyJobAdmin(admin.ModelAdmin):
    list_display = ('code', 'customer', 'walkin_name', 'surveyor', 'appointment_date', 'status')
    list_filter = ('status', 'appointment_date', 'roof_type', 'electric_phase')
    search_fields = ('code', 'walkin_name', 'customer__name')
    readonly_fields = ('code', 'created_at', 'completed_at')
    inlines = [SolarSurveyImageInline]

    # 🌟 แบ่งหมวดหมู่หน้าจอให้แอดมินคีย์ข้อมูลได้ง่ายและดูมืออาชีพ
    fieldsets = (
        ('1. ข้อมูลลูกค้าเบื้องต้น (Admin กรอก)', {
            'fields': ('code', 'status', 'customer', 'walkin_name', 'walkin_phone', 'survey_address')
        }),
        ('2. การนัดหมาย (Admin จ่ายงาน)', {
            'fields': ('appointment_date', 'assigned_by', 'surveyor')
        }),
        ('3. ข้อมูลเทคนิคหน้างาน (Sales อัปเดตกลับมา)', {
            'fields': ('avg_electric_bill', 'electric_phase', 'roof_type', 'cable_distance', 'has_wifi', 'recommended_package', 'note')
        }),
        ('4. ข้อมูลระบบ', {
            'fields': ('created_at', 'completed_at'),
            'classes': ('collapse',)
        }),
    )

@admin.register(SolarCommissionClaim)
class SolarCommissionClaimAdmin(admin.ModelAdmin):
    list_display = ('code', 'claim_type', 'requester', 'total_amount', 'status', 'created_at')
    list_filter = ('status', 'claim_type')
    search_fields = ('code',)
    readonly_fields = ('code',)

@admin.register(SolarCommissionTicket)
class SolarCommissionTicketAdmin(admin.ModelAdmin):
    list_display = ('code', 'ticket_type', 'quotation_ref', 'commission_amount', 'status')
    list_filter = ('status', 'ticket_type')
    search_fields = ('code', 'quotation_ref__code')
    readonly_fields = ('code',)