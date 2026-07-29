from django import forms
from django.forms import inlineformset_factory
from .models import SolarQuotation, SolarQuotationItem, SolarProduct

# 🌟 สเต็ป 1: ฟอร์มสร้างหัวบิล (เอกสารใหม่)
class SolarQuotationStep1Form(forms.ModelForm):
    class Meta:
        model = SolarQuotation
        fields = ['customer', 'date', 'valid_until']
        widgets = {
            'customer': forms.Select(attrs={'class': 'form-select fw-bold text-dark'}),
            'date': forms.DateInput(format='%d/%m/%Y', attrs={'class': 'form-control datepicker', 'placeholder': 'dd/mm/yyyy'}),
            'valid_until': forms.DateInput(format='%d/%m/%Y', attrs={'class': 'form-control datepicker', 'placeholder': 'dd/mm/yyyy'}),
        }

# 🌟 สเต็ป 2: ฟอร์มจัดการเงื่อนไขและสรุปยอดเงิน
class SolarQuotationStep2Form(forms.ModelForm):
    class Meta:
        model = SolarQuotation
        fields = ['discount', 'survey_fee', 'vat_type', 'payment_terms', 'note']
        widgets = {
            'discount': forms.NumberInput(attrs={'class': 'form-control text-end text-danger', 'step': '0.01'}),
            'survey_fee': forms.NumberInput(attrs={'class': 'form-control text-end', 'step': '0.01'}),
            'vat_type': forms.Select(attrs={'class': 'form-select fw-bold'}),
            'payment_terms': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'note': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': '-ไม่มี-'}),
        }

# ฟอร์มสำหรับการเลือกสินค้าแบบเพิ่ม/ลดแถวได้
SolarQuotationItemFormSet = inlineformset_factory(
    SolarQuotation, SolarQuotationItem,
    fields=['product', 'quantity', 'unit_price'],
    widgets={
        'product': forms.Select(attrs={'class': 'form-select form-select-sm fw-bold text-primary'}),
        'quantity': forms.NumberInput(attrs={'class': 'form-control text-center', 'min': '1'}),
        'unit_price': forms.NumberInput(attrs={'class': 'form-control text-end', 'step': '0.01'}),
    },
    extra=1,
    can_delete=True
)

# 🌟 ฟอร์มสำหรับจัดการสินค้าในคลัง (Solar Inventory)
class SolarProductForm(forms.ModelForm):
    class Meta:
        model = SolarProduct
        # เพิ่ม 'category' และ 'rm_category' เข้าไปใน fields
        fields = ['product_type', 'code', 'category', 'rm_category', 'name', 'unit', 'cost_price', 'sell_price', 'stock_qty', 'min_level', 'is_active']
        widgets = {
            'product_type': forms.Select(attrs={'class': 'form-select fw-bold text-primary'}),
            'code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'เว้นว่างไว้ ระบบจะสร้างรหัสให้โดยอัตโนมัติ'}),
            # เพิ่ม Widgets สำหรับหมวดหมู่
            'category': forms.Select(attrs={'class': 'form-select'}),
            'rm_category': forms.Select(attrs={'class': 'form-select'}),

            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'ระบุชื่อแพ็กเกจ หรือ อุปกรณ์เสริม'}),
            'unit': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'เช่น ชุด, แผง, เมตร'}),
            'cost_price': forms.NumberInput(attrs={'class': 'form-control text-end', 'step': '0.01'}),
            'sell_price': forms.NumberInput(attrs={'class': 'form-control text-end fw-bold text-success', 'step': '0.01'}),
            'stock_qty': forms.NumberInput(attrs={'class': 'form-control text-end', 'step': '0.01'}),
            'min_level': forms.NumberInput(attrs={'class': 'form-control text-end', 'step': '0.01'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input', 'style': 'transform: scale(1.5);'}),
        }