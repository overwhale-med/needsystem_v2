from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from .models import (
    Product, InventoryDoc, StockMovement, FinishedGood,
    RawMaterial, Category, RawMaterialCategory,
    SupplierPriceHistory, SubCategory
)
# ลบ Supplier ออกจากการ import ตรงนี้ เพราะเราไม่ได้ลงทะเบียน Admin ของมันที่นี่

# 1. จัดการหมวดหมู่
@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name',)

@admin.register(SubCategory)
class SubCategoryAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)

@admin.register(RawMaterialCategory)
class RawMaterialCategoryAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)

# ฟังก์ชันแสดงรูปภาพ
def show_image_preview(obj):
    if obj.image:
        return format_html('<img src="{}" style="width: 40px; height: 40px; object-fit: cover; border-radius: 4px;" />', obj.image.url)
    return "-"
show_image_preview.short_description = 'รูปสินค้า'

# ฟังก์ชันแสดงปุ่มบาร์โค้ด
def show_barcode_btn(obj):
    url = reverse('print_barcode', args=[obj.id])
    return format_html('<a href="{}" target="_blank" style="background:#333; color:#fff; padding:3px 8px; border-radius:3px; text-decoration:none;">🏷️ Print</a>', url)
show_barcode_btn.short_description = 'Barcode'

# ✅ 2.1 เมนูสินค้าสำเร็จรูป (FG)
@admin.register(FinishedGood)
class FinishedGoodAdmin(admin.ModelAdmin):
    list_display = ('code', show_image_preview, 'name', 'category', 'sell_price', 'stock_qty', 'unit', 'is_active', show_barcode_btn)
    list_filter = ('category', 'is_active')
    search_fields = ('code', 'name')

    def get_queryset(self, request):
        return super().get_queryset(request).filter(product_type='FG')

    def save_model(self, request, obj, form, change):
        obj.product_type = 'FG'
        super().save_model(request, obj, form, change)

# ✅ 2.2 เมนูวัตถุดิบ (RM)
@admin.register(RawMaterial)
class RawMaterialAdmin(admin.ModelAdmin):
    list_display = ('code', show_image_preview, 'name', 'rm_category', 'sub_category', 'cost_price', 'stock_qty', 'unit', 'supplier', 'is_active', show_barcode_btn)
    list_filter = ('rm_category', 'sub_category', 'supplier', 'is_active')
    search_fields = ('code', 'name', 'supplier__name')

    def get_queryset(self, request):
        return super().get_queryset(request).filter(product_type='RM')

    def save_model(self, request, obj, form, change):
        obj.product_type = 'RM'
        super().save_model(request, obj, form, change)

# 3. จัดการสต็อก
class StockMovementInline(admin.TabularInline):
    model = StockMovement
    extra = 0
    readonly_fields = ('product', 'quantity', 'movement_type')
    can_delete = False

@admin.register(InventoryDoc)
class InventoryDocAdmin(admin.ModelAdmin):
    list_display = ('doc_no', 'doc_type', 'reference', 'created_at', 'created_by')
    list_filter = ('doc_type', 'created_at')
    search_fields = ('doc_no', 'reference')
    inlines = [StockMovementInline]

# 4. ประวัติราคา
@admin.register(SupplierPriceHistory)
class SupplierPriceHistoryAdmin(admin.ModelAdmin):
    list_display = ('product', 'supplier', 'old_price', 'new_price', 'updated_at')
    list_filter = ('supplier', 'updated_at')
    search_fields = ('product__name',)

# ==========================================
# 🌟 [NEW] เพิ่มสต็อกการ์ด (Stock Movement) ใน Admin 🌟
# ==========================================
@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    # กำหนดคอลัมน์ที่จะแสดงในหน้าตาราง
    list_display = ('get_created_at', 'product', 'movement_type', 'quantity', 'doc', 'created_by')

    # เพิ่มตัวกรองด้านขวามือ
    list_filter = ('movement_type', 'created_at', 'product__product_type')

    # เพิ่มช่องค้นหา
    search_fields = ('product__name', 'product__code', 'doc__doc_no', 'doc__reference')

    # เรียงลำดับจากรายการล่าสุดขึ้นก่อน
    ordering = ('-created_at',)

    # กำหนดจำนวนแถวต่อหน้า
    list_per_page = 30

    def get_created_at(self, obj):
        return obj.created_at.strftime("%d/%m/%Y %H:%M")
    get_created_at.short_description = "วัน/เวลา"