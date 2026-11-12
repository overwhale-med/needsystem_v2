from django.contrib import admin
from .models import (
    ProductionOrder, ProductionOrderMaterial, BOM, BOMItem, Branch,
    MfgBranch, Salesperson, ProductionStatus, ProductionTeam,
    DeliveryStatus, Transporter, QCInspectionLog, BlueprintClaim,
    BlueprintLog, BlueprintClaimSplit, LogisticsClaim,
    QCReceiptDoc, QCPassedMedia, QCFailedMedia, MasterExpenseClaim,
    ServiceTicketMedia, DeliveryMedia,
    ServiceTicket, ServiceLaborClaim, ServiceCategory
)

class ProductionOrderMaterialInline(admin.TabularInline):
    model = ProductionOrderMaterial
    extra = 1

class BOMItemInline(admin.TabularInline):
    model = BOMItem
    extra = 1

@admin.register(ProductionOrder)
class ProductionOrderAdmin(admin.ModelAdmin):
    # 🌟 เพิ่ม is_onsite เพื่อให้ดูง่ายขึ้นว่างานไหนไปประกอบหน้างาน
    list_display = ('code', 'product', 'start_date', 'status', 'is_onsite', 'is_closed')
    list_filter = ('status', 'is_closed', 'is_onsite', 'branch')
    search_fields = ('code', 'customer_name')
    inlines = [ProductionOrderMaterialInline]

@admin.register(BOM)
class BOMAdmin(admin.ModelAdmin):
    list_display = ('product', 'name') # ✅ ลบ 'created_at' ออกแล้ว
    search_fields = ('product__name', 'name')
    inlines = [BOMItemInline]

# ==========================================
# 🌟 การลงทะเบียนข้อมูลพื้นฐาน (Master Data) 🌟
# ==========================================
@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)

@admin.register(MfgBranch)
class MfgBranchAdmin(admin.ModelAdmin):
    list_display = ('name', 'weekly_quota')
    search_fields = ('name',)

@admin.register(Salesperson)
class SalespersonAdmin(admin.ModelAdmin):
    list_display = ('name', 'branch')
    list_filter = ('branch',)
    search_fields = ('name',)

@admin.register(ProductionStatus)
class ProductionStatusAdmin(admin.ModelAdmin):
    list_display = ('name', 'sequence')
    ordering = ('sequence',)

@admin.register(ProductionTeam)
class ProductionTeamAdmin(admin.ModelAdmin):
    list_display = ('name',)

@admin.register(DeliveryStatus)
class DeliveryStatusAdmin(admin.ModelAdmin):
    list_display = ('name',)

# ==========================================
# 🌟 การลงทะเบียนตารางบันทึกข้อมูล (Logs & Claims) 🌟
# ==========================================
@admin.register(QCInspectionLog)
class QCInspectionLogAdmin(admin.ModelAdmin):
    list_display = ('production_order', 'round_number', 'status', 'inspector', 'inspected_at')
    list_filter = ('status', 'inspected_at')
    search_fields = ('production_order__code', 'inspector__first_name')

@admin.register(BlueprintClaim)
class BlueprintClaimAdmin(admin.ModelAdmin):
    list_display = ('code', 'employee', 'total_jobs', 'total_amount', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('code', 'employee__first_name')

@admin.register(DeliveryMedia)
class DeliveryMediaAdmin(admin.ModelAdmin):
    list_display = ('production_order', 'uploaded_at')
    list_filter = ('uploaded_at',)
    search_fields = ('production_order__code',)

# ==========================================
# 🌟 ส่วนการจัดการระบบขนส่ง (Logistics) 🌟
# ==========================================

@admin.register(Transporter)
class TransporterAdmin(admin.ModelAdmin):
    list_display = ('name', 'driver_name', 'vehicle_plate', 'delivery_fee')
    search_fields = ('name', 'driver_name', 'vehicle_plate')
    # แสดงผลฟิลด์ใหม่ๆ ในหน้าแก้ไขให้ครบถ้วน
    fields = ('name', 'driver_name', 'vehicle_plate', 'address', 'bank_account', 'id_card_image', 'delivery_fee')

@admin.register(LogisticsClaim)
class LogisticsClaimAdmin(admin.ModelAdmin):
    list_display = ('code', 'transporter', 'total_jobs', 'total_amount', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('code', 'transporter__name')
    # 🌟 ล็อกฟิลด์วันที่สร้างบิลให้เป็น 'อ่านอย่างเดียว' เพื่อป้องกัน Error ตอนกด Save
    readonly_fields = ('created_at',)

# ==========================================
# 🌟 [NEW] แสดงใบรับสินค้าสำเร็จรูป (จาก QC) ใน Admin
# ==========================================
@admin.register(QCReceiptDoc)
class QCReceiptDocAdmin(admin.ModelAdmin):
    list_display = ('doc_no', 'production_order', 'product', 'quantity', 'created_by', 'created_at')
    list_filter = ('created_at', 'created_by')
    search_fields = ('doc_no', 'production_order__code', 'product__name')
    readonly_fields = ('created_at',)
    ordering = ('-created_at',)

@admin.register(MasterExpenseClaim)
class MasterExpenseClaimAdmin(admin.ModelAdmin):
    list_display = ('code', 'requester', 'total_amount', 'status', 'created_at')
    search_fields = ('code', 'requester__first_name')
    list_filter = ('status',)

# ==========================================
# 🌟 ส่วนการจัดการระบบแจ้งซ่อม (After-Sales Service) 🌟
# ==========================================
@admin.register(ServiceCategory)
class ServiceCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name',)

@admin.register(ServiceTicket)
class ServiceTicketAdmin(admin.ModelAdmin):
    list_display = ('code', 'production_order', 'salesperson', 'issue_category', 'status', 'created_at')
    list_filter = ('status', 'issue_category', 'urgency', 'is_warranty')
    search_fields = ('code', 'production_order__customer_name', 'customer_phone')
    readonly_fields = ('created_at', 'updated_at')

@admin.register(ServiceLaborClaim)
class ServiceLaborClaimAdmin(admin.ModelAdmin):
    list_display = ('code', 'service_ticket', 'technician_name', 'amount', 'status')
    list_filter = ('status',)
    search_fields = ('code', 'technician_name', 'service_ticket__code')

# ==========================================
# 🌟 ส่วนการจัดการ Blueprint Log (อัปเกรดให้ดูง่ายขึ้น) 🌟
# ==========================================
@admin.register(BlueprintLog)
class BlueprintLogAdmin(admin.ModelAdmin):
    # กำหนดคอลัมน์ที่จะแสดงในตาราง (ไม่ต้องกดเข้าไปดูข้างในก็รู้เรื่อง)
    list_display = ('production_order', 'action', 'employee', 'created_at')
    # เพิ่มตัวกรองด้านขวามือ
    list_filter = ('created_at', 'employee')
    # เพิ่มช่องค้นหาด้านบน (ค้นหาจากเลข JOB หรือ คำในรายละเอียดได้)
    search_fields = ('production_order__code', 'action')

# ==========================================
# 🌟 ส่วนการจัดการ คลังรูปภาพ QC (อัปเกรดตาราง) 🌟
# ==========================================
@admin.register(QCPassedMedia)
class QCPassedMediaAdmin(admin.ModelAdmin):
    list_display = ('production_order', 'uploaded_by', 'uploaded_at')
    list_filter = ('uploaded_at', 'uploaded_by')
    search_fields = ('production_order__code',)

@admin.register(QCFailedMedia)
class QCFailedMediaAdmin(admin.ModelAdmin):
    list_display = ('qc_log', 'uploaded_at')
    list_filter = ('uploaded_at',)
    search_fields = ('qc_log__production_order__code',)

# ==========================================
# 🌟 ส่วนการจัดการ คลังสื่อแจ้งซ่อม (อัปเกรดตาราง) 🌟
# ==========================================
@admin.register(ServiceTicketMedia)
class ServiceTicketMediaAdmin(admin.ModelAdmin):
    list_display = ('ticket', 'media_type', 'uploaded_at')
    list_filter = ('media_type', 'uploaded_at')
    search_fields = ('ticket__code',)

# ==========================================
# 🌟 ส่วนการจัดการ ส่วนแบ่งใบเบิกผลงาน (อัปเกรดตาราง) 🌟
# ==========================================
@admin.register(BlueprintClaimSplit)
class BlueprintClaimSplitAdmin(admin.ModelAdmin):
    list_display = ('claim', 'employee', 'role_name', 'percentage', 'amount')
    list_filter = ('role_name',)
    search_fields = ('claim__code', 'employee__first_name')