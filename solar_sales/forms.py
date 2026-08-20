from django import forms
from django.forms import inlineformset_factory
from .models import SolarQuotation, SolarQuotationItem, SolarProduct
from hr.models import Employee
from django.db.models import Q

# 🌟 สเต็ป 1: ฟอร์มสร้างหัวบิล (เอกสารใหม่)
class SolarQuotationStep1Form(forms.ModelForm):
    class Meta:
        model = SolarQuotation
        # 🌟 [FIXED] เพิ่ม 'vat_type' เข้าไปใน fields เพื่อให้บิลใหม่บันทึกประเภทภาษีตั้งแต่ตอนสร้าง 🌟
        fields = ['customer', 'date', 'valid_until', 'vat_type']
        widgets = {
            'customer': forms.Select(attrs={'class': 'form-select fw-bold text-dark'}),
            'date': forms.DateInput(format='%d/%m/%Y', attrs={'class': 'form-control datepicker', 'placeholder': 'dd/mm/yyyy'}),
            'valid_until': forms.DateInput(format='%d/%m/%Y', attrs={'class': 'form-control datepicker', 'placeholder': 'dd/mm/yyyy'}),
            'vat_type': forms.Select(attrs={'class': 'form-select fw-bold'}),
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

# ==========================================
# 🌟 ฟอร์มสำหรับระบบสำรวจหน้างานและเบิกจ่ายโซล่าเซลล์
# ==========================================
from .models import SolarSurveyJob, SolarSurveyItem, SolarExpenseClaim

class SolarSurveyJobForm(forms.ModelForm):
    class Meta:
        model = SolarSurveyJob
        # 🌟 [FIXED] เพิ่มฟิลด์ walkin_name และ walkin_phone เข้าไป 🌟
        fields = ['customer', 'walkin_name', 'walkin_phone', 'appointment_date', 'surveyor', 'note']
        widgets = {
            'customer': forms.Select(attrs={'class': 'form-select fw-bold text-dark'}),
            'walkin_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'พิมพ์ชื่อลูกค้า (ถ้าไม่มีในระบบ)'}),
            'walkin_phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'เบอร์โทรติดต่อ...'}),
            # 🌟 [FIXED] เปลี่ยนไปใช้ class datetimepicker เพื่อรองรับการแสดงผล DD/MM/YYYY 🌟
            'appointment_date': forms.TextInput(attrs={'class': 'form-control datetimepicker', 'placeholder': 'คลิกเพื่อเลือกวัน/เวลา'}),
            'surveyor': forms.Select(attrs={'class': 'form-select'}),
            'note': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'รายละเอียดการนัดหมาย...'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['customer'].required = False

        # 🌟 [FIXED] กรองให้แสดงเฉพาะพนักงานแผนกช่าง/โซล่าเซลล์/ผลิต (แก้คำใน icontains ให้ตรงกับชื่อแผนกจริงได้เลยครับ) 🌟
        self.fields['surveyor'].queryset = Employee.objects.filter(
            Q(department__name__icontains='ช่าง') |
            Q(department__name__icontains='โซล่า') |
            Q(department__name__icontains='ผลิต') |
            Q(position__title__icontains='ช่าง')
        ).order_by('first_name')

class SolarExpenseClaimForm(forms.ModelForm):
    # 🌟 [FIXED] เอา multiple: True ออกจาก attrs แล้วให้ไปใส่ใน HTML แทน 🌟
    slip_images = forms.FileField(
        widget=forms.ClearableFileInput(attrs={'class': 'form-control'}),
        required=False,
        label="แนบรูปใบเสร็จ / สลิปหลักฐาน (ลากคลุมเลือกได้หลายรูป)"
    )

    class Meta:
        model = SolarExpenseClaim
        fields = ['amount', 'description']
        widgets = {
            'amount': forms.NumberInput(attrs={'class': 'form-control text-end fs-5 fw-bold text-danger', 'step': '0.01'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'เช่น \n- ค่าน้ำมันรถ 500 บาท\n- ค่าทางด่วน 150 บาท...'}),
        }