from django.contrib import admin
from .models import SolarProductCategory, SolarRawMaterialCategory, SolarProduct, SolarStockMovement, SolarQuotation, SolarQuotationItem, SolarInvoice

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

@admin.register(SolarStockMovement)
class SolarStockMovementAdmin(admin.ModelAdmin):
    list_display = ['product', 'movement_type', 'quantity', 'created_at']
    list_filter = ['movement_type']
    search_fields = ['product__name', 'reference_doc']

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