from django import forms
from .models import SolarProduct

# 🌟 ฟอร์มสำหรับจัดการสินค้าในคลัง (Solar Inventory)
class SolarProductForm(forms.ModelForm):
    class Meta:
        model = SolarProduct
        fields = ['product_type', 'code', 'category', 'rm_category', 'name', 'unit', 'cost_price', 'sell_price', 'stock_qty', 'min_level', 'is_active']
        widgets = {
            'product_type': forms.Select(attrs={'class': 'form-select fw-bold text-primary'}),
            'code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'เว้นว่างไว้ ระบบจะสร้างรหัสให้โดยอัตโนมัติ'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'rm_category': forms.Select(attrs={'class': 'form-select'}),
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'ระบุชื่อแพ็กเกจ หรือ อุปกรณ์เสริม'}),
            'unit': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'เช่น ชุด, แผง, เมตร'}),
            
            # 🌟 ช่องตัวเลขที่ใช้คลาส auto-comma สำหรับจัดการเครื่องหมายลูกน้ำ 🌟
            'cost_price': forms.TextInput(attrs={'class': 'form-control text-end auto-comma', 'placeholder': '0.00'}),
            'sell_price': forms.TextInput(attrs={'class': 'form-control text-end fw-bold text-success auto-comma', 'placeholder': '0.00'}),
            'stock_qty': forms.TextInput(attrs={'class': 'form-control text-end auto-comma', 'placeholder': '0'}),
            'min_level': forms.TextInput(attrs={'class': 'form-control text-end auto-comma', 'placeholder': '0'}),
            
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input', 'style': 'transform: scale(1.5);'}),
        }

    # 🌟 ดักจับและลบเครื่องหมายลูกน้ำ (,) ออกก่อนให้ระบบตรวจสอบและบันทึกลงฐานข้อมูล 🌟
    def __init__(self, *args, **kwargs):
        if len(args) > 0 and hasattr(args[0], 'copy'):
            data = args[0].copy()
            for field in ['cost_price', 'sell_price', 'stock_qty', 'min_level']:
                if field in data:
                    data[field] = str(data[field]).replace(',', '')
            args = (data,) + args[1:]
        elif 'data' in kwargs and hasattr(kwargs['data'], 'copy'):
            data = kwargs['data'].copy()
            for field in ['cost_price', 'sell_price', 'stock_qty', 'min_level']:
                if field in data:
                    data[field] = str(data[field]).replace(',', '')
            kwargs['data'] = data
        super().__init__(*args, **kwargs)