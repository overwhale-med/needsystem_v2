from django.contrib import admin
from .models import SolarPurchaseOrder, SolarPurchaseOrderItem, SolarPurchaseOrderPayment, SolarPurchasePreparation

# 🌟 จัดการตารางใบสั่งซื้อหลัก (POS)
@admin.register(SolarPurchaseOrder)
class SolarPurchaseOrderAdmin(admin.ModelAdmin):
    list_display = ('code', 'get_supplier_name', 'total_amount', 'status', 'payment_status', 'receipt_status', 'date')
    search_fields = ('code', 'supplier__name', 'supplier_name_free_text')
    list_filter = ('status', 'payment_status', 'receipt_status', 'date')

    # สร้างฟังก์ชันจำลองเพื่อดึงชื่อ Supplier มาแสดงให้สวยงาม
    def get_supplier_name(self, obj):
        return obj.supplier.name if obj.supplier else obj.supplier_name_free_text
    get_supplier_name.short_description = 'ผู้ขาย / ร้านค้า'

# 🌟 จัดการตารางประวัติการชำระเงิน
@admin.register(SolarPurchaseOrderPayment)
class SolarPurchaseOrderPaymentAdmin(admin.ModelAdmin):
    list_display = ('pv_code', 'po', 'amount', 'payment_date', 'payment_method')
    search_fields = ('pv_code', 'po__code')
    list_filter = ('payment_date', 'payment_method')

# 🌟 จัดการตารางใบเตรียมสั่งซื้อโซล่า (PPO)
@admin.register(SolarPurchasePreparation)
class SolarPurchasePreparationAdmin(admin.ModelAdmin):
    list_display = ('code', 'created_by', 'status', 'created_at')
    search_fields = ('code',)
    list_filter = ('status', 'created_at')
    
    # หากมีการผูก ManyToMany กับ SolarJob การใช้ filter_horizontal จะช่วยให้เลือกข้อมูลซ้าย-ขวาได้ง่ายขึ้น
    # แต่ถ้าไม่มีความสัมพันธ์นี้ สามารถลบบรรทัด filter_horizontal ออกได้ครับ
    filter_horizontal = ('solar_jobs',)