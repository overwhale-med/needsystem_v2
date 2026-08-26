from django.contrib import admin
from .models import SolarQuotation, SolarQuotationItem, SolarInvoice, SolarSurveyJob, SolarSurveyItem, SolarExpenseClaim, SolarExpenseSlip

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