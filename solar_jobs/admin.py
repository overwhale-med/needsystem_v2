from django.contrib import admin
from .models import SubcontractorTeam, SolarJob, SolarJobBOM, SolarExpense

@admin.register(SubcontractorTeam)
class SubcontractorTeamAdmin(admin.ModelAdmin):
    list_display = ['name', 'leader_name', 'phone', 'is_active']
    search_fields = ['name', 'leader_name']

class SolarJobBOMInline(admin.TabularInline):
    model = SolarJobBOM
    extra = 1

@admin.register(SolarJob)
class SolarJobAdmin(admin.ModelAdmin):
    list_display = ['code', 'quotation_ref', 'customer', 'status', 'start_date']
    list_filter = ['status']
    search_fields = ['code', 'customer__name']
    inlines = [SolarJobBOMInline]

@admin.register(SolarExpense)
class SolarExpenseAdmin(admin.ModelAdmin):
    list_display = ['job', 'expense_type', 'amount', 'status', 'requester']
    list_filter = ['status', 'expense_type']
    search_fields = ['job__code']