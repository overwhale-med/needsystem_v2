from django.contrib import admin
from .models import SolarJob, SolarJobMaterial, SolarExpense

class SolarJobMaterialInline(admin.TabularInline):
    model = SolarJobMaterial
    extra = 1

@admin.register(SolarJob)
class SolarJobAdmin(admin.ModelAdmin):
    list_display = ['code', 'customer', 'package_sold', 'start_date', 'status']
    list_filter = ['status', 'technician_team']
    search_fields = ['code', 'customer__name']
    readonly_fields = ['code']
    inlines = [SolarJobMaterialInline]

@admin.register(SolarExpense)
class SolarExpenseAdmin(admin.ModelAdmin):
    list_display = ['job', 'expense_type', 'amount', 'requester', 'status', 'created_at']
    list_filter = ['status', 'expense_type']
    search_fields = ['job__code', 'requester__first_name']