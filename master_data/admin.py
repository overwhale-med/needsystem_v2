from django.contrib import admin
from .models import CompanyInfo, Customer, Supplier, Province, Amphure, Tambon
from .models import ShippingRate

# 1. ข้อมูลบริษัท
@admin.register(CompanyInfo)
class CompanyInfoAdmin(admin.ModelAdmin):
    list_display = ('name_th', 'branch', 'phone')

# 2. ลูกค้า (Customer)
@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    # ลบ 'points' ออกแล้ว ใส่ 'province' แทน
    list_display = ('code', 'name', 'phone', 'province', 'is_active')
    search_fields = ('code', 'name', 'phone', 'tax_id')
    list_filter = ('is_active', 'province')
    readonly_fields = ('code',) # ห้ามแก้รหัสลูกค้าเอง

# 3. ผู้ขาย (Supplier)
@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'contact_name', 'phone')
    search_fields = ('code', 'name')

# 4. ข้อมูลภูมิศาสตร์ (เผื่อแก้ไข)
@admin.register(Province)
class ProvinceAdmin(admin.ModelAdmin):
    search_fields = ('name_th', 'name_en')

@admin.register(Amphure)
class AmphureAdmin(admin.ModelAdmin):
    search_fields = ('name_th',)
    list_filter = ('province',)

@admin.register(Tambon)
class TambonAdmin(admin.ModelAdmin):
    search_fields = ('name_th', 'zip_code')
    list_filter = ('amphure__province',)

@admin.register(ShippingRate)
class ShippingRateAdmin(admin.ModelAdmin):
    list_display = ('origin_branch', 'destination_province', 'price')
    list_filter = ('origin_branch',)
    search_fields = ('destination_province',)