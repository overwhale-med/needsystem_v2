from django import forms
from django.forms import inlineformset_factory
from .models import PurchaseOrder, PurchaseOrderItem

class PurchaseOrderForm(forms.ModelForm):
    class Meta:
        model = PurchaseOrder
        fields = ['supplier', 'expected_date', 'status', 'note']
        labels = {
            'supplier': 'ร้านค้า (Supplier)',
            'expected_date': 'กำหนดรับของ',
            'status': 'สถานะเอกสาร',
            'note': 'หมายเหตุ'
        }
        widgets = {
            'supplier': forms.Select(attrs={'class': 'form-select shadow-sm', 'required': 'required'}),
            # 🌟 เปลี่ยนจาก type='date' เป็น type='text' และใส่คลาส datepicker 🌟
            'expected_date': forms.TextInput(attrs={'class': 'form-control shadow-sm datepicker', 'placeholder': 'dd/mm/yyyy'}),
            'status': forms.Select(attrs={'class': 'form-select shadow-sm'}),
            'note': forms.Textarea(attrs={'class': 'form-control shadow-sm', 'rows': 2, 'placeholder': 'ระบุหมายเหตุเพิ่มเติม (ถ้ามี)'}),
        }

class PurchaseOrderItemForm(forms.ModelForm):
    class Meta:
        model = PurchaseOrderItem
        fields = ['product', 'quantity', 'unit_cost', 'total_cost']
        widgets = {
            'product': forms.Select(attrs={'class': 'form-select product-select'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control text-center qty-input', 'min': '0', 'step': '0.01'}),
            # 🌟 แก้ไข: เปลี่ยน NumberInput เป็น TextInput เพื่อให้รองรับเครื่องหมายลูกน้ำได้ 🌟
            'unit_cost': forms.TextInput(attrs={'class': 'form-control text-end cost-input'}),
            'total_cost': forms.TextInput(attrs={'class': 'form-control text-end text-primary fw-bold total-input', 'readonly': 'readonly'}),
        }

# Formset สำหรับเพิ่มรายการสินค้าได้หลายบรรทัด
PurchaseOrderItemFormSet = inlineformset_factory(
    PurchaseOrder, 
    PurchaseOrderItem,
    form=PurchaseOrderItemForm,
    extra=1,
    can_delete=True
)