from django.contrib import admin
from .models import SolarProductCategory, SolarRawMaterialCategory, SolarProduct, SolarStockMovement
from .models import SolarInventoryDoc

@admin.register(SolarProductCategory)
class SolarProductCategoryAdmin(admin.ModelAdmin):
    list_display = ['name']
    search_fields = ['name']

@admin.register(SolarRawMaterialCategory)
class SolarRawMaterialCategoryAdmin(admin.ModelAdmin):
    list_display = ['name']
    search_fields = ['name']

@admin.register(SolarProduct)
class SolarProductAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'product_type', 'category', 'rm_category', 'stock_qty', 'cost_price', 'sell_price', 'is_active']
    list_filter = ['product_type', 'is_active', 'category', 'rm_category']
    search_fields = ['code', 'name']
    readonly_fields = ['code']

# 🌟 [NEW] 1. สร้าง Inline เพื่อแสดงรายการเคลื่อนไหวสต็อก ซ้อนอยู่ข้างในเอกสาร
class SolarStockMovementInline(admin.TabularInline):
    model = SolarStockMovement
    extra = 0
    readonly_fields = ['created_at']

# 🌟 [UPDATE] 2. ตารางประวัติการเคลื่อนไหวสต็อก (เพิ่มคอลัมน์เลขที่เอกสาร 'doc')
@admin.register(SolarStockMovement)
class SolarStockMovementAdmin(admin.ModelAdmin):
    list_display = ['doc', 'product', 'movement_type', 'quantity', 'created_at']
    list_filter = ['movement_type']
    search_fields = ['doc__doc_no', 'product__name', 'reference_doc']

# 🌟 [UPDATE] 3. ตารางเอกสารคลังสินค้า (เพิ่ม inlines เพื่อดึงรายการมาโชว์)
@admin.register(SolarInventoryDoc)
class SolarInventoryDocAdmin(admin.ModelAdmin):
    list_display = ('doc_no', 'doc_type', 'reference', 'created_by', 'created_at')
    search_fields = ('doc_no', 'reference')
    list_filter = ('doc_type', 'created_at')
    readonly_fields = ('doc_no',)
    inlines = [SolarStockMovementInline]