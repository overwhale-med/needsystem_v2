from django.contrib import admin
from .models import SolarQuotation, SolarQuotationItem, SolarInvoice, SolarSurveyJob, SolarSurveyItem, SolarExpenseClaim, SolarExpenseSlip, SolarCommissionClaim, SolarCommissionTicket

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

from .models import SolarSurveyJob, SolarCustomer

@admin.register(SolarCustomer)
class SolarCustomerAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'phone', 'contact_person')
    search_fields = ('code', 'name', 'phone')

@admin.register(SolarSurveyJob)
class SolarSurveyJobAdmin(admin.ModelAdmin):
    list_display = ('code', 'customer', 'walkin_name', 'surveyor', 'appointment_date', 'status')
    list_filter = ('status', 'appointment_date')
    search_fields = ('code', 'walkin_name', 'customer__name')

@admin.register(SolarCommissionClaim)
class SolarCommissionClaimAdmin(admin.ModelAdmin):
    list_display = ('code', 'claim_type', 'requester', 'total_amount', 'status', 'created_at')
    list_filter = ('status', 'claim_type')
    search_fields = ('code',)
    readonly_fields = ('code',)

@admin.register(SolarCommissionTicket)
class SolarCommissionTicketAdmin(admin.ModelAdmin):
    list_display = ('code', 'ticket_type', 'quotation_ref', 'commission_amount', 'status')
    list_filter = ('status', 'ticket_type')
    search_fields = ('code', 'quotation_ref__code')
    readonly_fields = ('code',)