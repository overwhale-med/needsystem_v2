from django.contrib import admin
from django.contrib import messages
from django.utils.html import format_html
from django.urls import reverse
from accounting.models import Expense, ExpenseCategory

# นำเข้า Model ทั้งหมดที่ต้องใช้
from .models import (
    PurchaseOrder, PurchaseOrderItem, PurchasePreparation, PurchaseOrderPayment,
    OverseasSupplier, OverseasPO, OverseasPOItem, OverseasDocument
)

@admin.action(description='✅ ยืนยันรับของเข้าสต็อก (และลงบัญชี)')
def action_receive_stock(modeladmin, request, queryset):
    try:
        cat = ExpenseCategory.objects.get(name__contains="ต้นทุน")
    except:
        cat, _ = ExpenseCategory.objects.get_or_create(name="ต้นทุนสินค้า (สั่งซื้อ)")

    for po in queryset:
        if po.status == 'RECEIVED': continue
        if po.status == 'CANCELLED': continue

        for item in po.items.all():
            if item.product:
                product = item.product
                product.stock_qty += item.quantity
                if item.unit_cost > 0: product.cost_price = item.unit_cost
                product.save()
        
        if po.total_amount > 0:
            Expense.objects.create(
                title=f"สั่งซื้อสินค้า PO {po.code}", amount=po.total_amount, category=cat,
                date=po.date, note=f"Auto from PO {po.code}"
            )
        po.status = 'RECEIVED'
        po.save()
        messages.success(request, f"✅ PO {po.code} รับของเรียบร้อย!")

class PurchaseItemInline(admin.TabularInline):
    model = PurchaseOrderItem
    extra = 1

@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    list_display = ('code', 'date', 'supplier', 'total_amount', 'status', 'print_button')
    list_filter = ('status', 'date', 'supplier')
    inlines = [PurchaseItemInline]
    actions = [action_receive_stock]

    def print_button(self, obj):
        url = reverse('po_print', args=[obj.id])
        return format_html(f'<a href="{url}" target="_blank" class="button" style="background-color:#fd7e14; color:white; padding:5px 10px; border-radius:5px; text-decoration:none;">🖨️ พิมพ์</a>')
    
    print_button.short_description = 'พิมพ์เอกสาร'

@admin.register(PurchaseOrderPayment)
class PurchaseOrderPaymentAdmin(admin.ModelAdmin):
    list_display = ('po', 'amount', 'payment_date', 'payment_method')
    search_fields = ('po__code',)

@admin.register(PurchasePreparation)
class PurchasePreparationAdmin(admin.ModelAdmin):
    list_display = ('code', 'created_at', 'created_by')
    search_fields = ('code',)


# ==========================================
# 🌟 ระบบจัดซื้อต่างประเทศ (Overseas) เพิ่มให้แสดงใน Admin 🌟
# ==========================================

@admin.register(OverseasSupplier)
class OverseasSupplierAdmin(admin.ModelAdmin):
    list_display = ('name', 'country', 'contact_name', 'phone', 'email')
    search_fields = ('name', 'country', 'contact_name', 'phone')
    list_filter = ('country',)

class OverseasPOItemInline(admin.TabularInline):
    model = OverseasPOItem
    extra = 1

class OverseasDocumentInline(admin.TabularInline):
    model = OverseasDocument
    extra = 1

@admin.register(OverseasPO)
class OverseasPOAdmin(admin.ModelAdmin):
    list_display = ('po_number', 'pi_number', 'get_supplier_name', 'po_date', 'status', 'total_amount')
    list_filter = ('status', 'po_date')
    search_fields = ('po_number', 'pi_number', 'supplier__name', 'supplier_name')
    inlines = [OverseasPOItemInline, OverseasDocumentInline]
    
    def get_supplier_name(self, obj):
        return obj.supplier.name if obj.supplier else obj.supplier_name
    get_supplier_name.short_description = 'ร้านค้าต่างประเทศ'