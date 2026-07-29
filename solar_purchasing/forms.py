from django import forms
from django.forms import inlineformset_factory
from .models import SolarPurchaseOrder, SolarPurchaseOrderItem

class SolarPurchaseOrderForm(forms.ModelForm):
    class Meta:
        model = SolarPurchaseOrder
        fields = ['supplier', 'supplier_name_free_text', 'date', 'expected_date', 'note']
        widgets = {
            # บังคับรูปแบบวันที่เป็น dd/mm/yyyy เพื่อความแม่นยำ
            'date': forms.DateInput(format='%d/%m/%Y', attrs={'class': 'form-control datepicker', 'placeholder': 'dd/mm/yyyy'}),
            'expected_date': forms.DateInput(format='%d/%m/%Y', attrs={'class': 'form-control datepicker', 'placeholder': 'dd/mm/yyyy'}),
            'supplier_name_free_text': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'พิมพ์ชื่อร้านค้ากรณีไม่มีในระบบ'}),
            'note': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

class SolarPurchaseOrderItemForm(forms.ModelForm):
    class Meta:
        model = SolarPurchaseOrderItem
        fields = ['product', 'item_name_free_text', 'quantity', 'unit_cost']
        widgets = {
            'item_name_free_text': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'พิมพ์ชื่อสินค้าฉุกเฉิน'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control text-center', 'step': '0.01'}),
            'unit_cost': forms.NumberInput(attrs={'class': 'form-control text-end', 'step': '0.01'}),
        }

# สร้าง Formset สำหรับรายการสินค้าย่อยแบบเพิ่มลดได้
SolarOrderItemFormSet = inlineformset_factory(
    SolarPurchaseOrder, SolarPurchaseOrderItem, 
    form=SolarPurchaseOrderItemForm, 
    extra=1, 
    can_delete=True
)