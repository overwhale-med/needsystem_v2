from django import forms
from django.forms import inlineformset_factory
from .models import SolarJob, SolarJobMaterial, SolarExpense
# 🌟 ดึงตารางสินค้ามาเพื่อกรองข้อมูล
from solar_sales.models import SolarProduct 

class SolarJobForm(forms.ModelForm):
    class Meta:
        model = SolarJob
        fields = ['technician_team', 'start_date', 'expected_finish_date', 'labor_cost_budget', 'status', 'note']
        widgets = {
            'technician_team': forms.Select(attrs={'class': 'form-select fw-bold'}),
            'start_date': forms.DateInput(format='%d/%m/%Y', attrs={'class': 'form-control datepicker', 'placeholder': 'dd/mm/yyyy'}),
            'expected_finish_date': forms.DateInput(format='%d/%m/%Y', attrs={'class': 'form-control datepicker', 'placeholder': 'dd/mm/yyyy'}),
            'labor_cost_budget': forms.NumberInput(attrs={'class': 'form-control text-end fw-bold text-primary', 'step': '0.01'}),
            'status': forms.Select(attrs={'class': 'form-select fw-bold'}),
            'note': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

class SolarExpenseForm(forms.ModelForm):
    class Meta:
        model = SolarExpense
        fields = ['job', 'expense_type', 'description', 'amount', 'receipt_image']
        widgets = {
            'job': forms.Select(attrs={'class': 'form-select fw-bold text-dark'}),
            'expense_type': forms.Select(attrs={'class': 'form-select fw-bold text-dark'}),
            'description': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'ระบุรายละเอียด เช่น ค่าทางด่วน, ค่าน้ำมัน, ค่าแรงงวด 1'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control text-end fw-bold text-primary', 'step': '0.01'}),
            'receipt_image': forms.FileInput(attrs={'class': 'form-control'}),
        }

# 🌟 สร้างแบบฟอร์มย่อยสำหรับจัดการวัตถุดิบ เพื่อนำไปใช้กับ FormSet
class SolarJobMaterialForm(forms.ModelForm):
    class Meta:
        model = SolarJobMaterial
        fields = ['product', 'quantity', 'unit_cost']
        widgets = {
            'product': forms.Select(attrs={'class': 'form-select form-select-sm fw-bold'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control text-center', 'step': '0.01'}),
            'unit_cost': forms.NumberInput(attrs={'class': 'form-control text-end', 'step': '0.01'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 🌟 ล็อคให้เลือกได้เฉพาะสินค้าประเภทวัตถุดิบ (RM) ที่เปิดใช้งานอยู่เท่านั้น
        self.fields['product'].queryset = SolarProduct.objects.filter(is_active=True, product_type='RM')

# ฟอร์มสำหรับการเบิกวัตถุดิบแบบเพิ่ม/ลดแถวได้
SolarMaterialFormSet = inlineformset_factory(
    SolarJob, SolarJobMaterial,
    form=SolarJobMaterialForm, # 🌟 เรียกใช้ฟอร์มที่เราสร้างไว้ด้านบน
    extra=1,
    can_delete=True
)