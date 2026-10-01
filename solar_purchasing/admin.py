from django.contrib import admin
from .models import SolarPurchaseOrderPayment

@admin.register(SolarPurchaseOrderPayment)
class SolarPurchaseOrderPaymentAdmin(admin.ModelAdmin):
    list_display = ('pv_code', 'po', 'amount', 'payment_date', 'payment_method')
    search_fields = ('pv_code', 'po__code')
    list_filter = ('payment_date', 'payment_method')