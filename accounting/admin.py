from django.contrib import admin
from .models import ExpenseCategory, Expense, Income
from django.db.models import Sum

@admin.register(ExpenseCategory)
class ExpenseCategoryAdmin(admin.ModelAdmin):
    list_display = ('name',)

@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ('date', 'title', 'category', 'amount')
    list_filter = ('date', 'category')
    search_fields = ('title',)
    date_hierarchy = 'date' # เพิ่มเมนูเลือกดูตามปี/เดือน ด้านบน

@admin.register(Income)
class IncomeAdmin(admin.ModelAdmin):
    list_display = ('date', 'title', 'amount', 'pos_order')
    list_filter = ('date',)
    date_hierarchy = 'date'