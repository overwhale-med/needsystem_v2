from django.contrib import admin
from .models import (
    ProductionOrder, ProductionOrderMaterial, BOM, BOMItem, Branch,
    MfgBranch, Salesperson, ProductionStatus, ProductionTeam,
    DeliveryStatus, Transporter, QCInspectionLog, BlueprintClaim,
    BlueprintLog, BlueprintClaimSplit, LogisticsClaim
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

# การลงทะเบียนแบบปกติ
admin.site.register(Branch)
admin.site.register(MfgBranch)
admin.site.register(Salesperson)
admin.site.register(ProductionStatus)
admin.site.register(ProductionTeam)
admin.site.register(DeliveryStatus)
admin.site.register(QCInspectionLog)
admin.site.register(BlueprintClaim)
admin.site.register(BlueprintLog)
admin.site.register(BlueprintClaimSplit)

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