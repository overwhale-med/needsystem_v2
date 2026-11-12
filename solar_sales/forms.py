from django import forms
from django.forms import inlineformset_factory
from .models import SolarQuotation, SolarQuotationItem, SolarProduct, SolarCustomer
from hr.models import Employee
from django.db.models import Q

# 🌟 สเต็ป 1: ฟอร์มสร้างหัวบิล (เอกสารใหม่)
class SolarQuotationStep1Form(forms.ModelForm):
    class Meta:
        model = SolarQuotation
        fields = ['customer', 'date', 'valid_until', 'vat_type']
        widgets = {
            'customer': forms.Select(attrs={'class': 'form-select fw-bold text-dark'}),
            'date': forms.DateInput(format='%d/%m/%Y', attrs={'class': 'form-control datepicker', 'placeholder': 'dd/mm/yyyy', 'autocomplete': 'off'}),
            'valid_until': forms.DateInput(format='%d/%m/%Y', attrs={'class': 'form-control datepicker', 'placeholder': 'dd/mm/yyyy', 'autocomplete': 'off'}),
            # 🌟 [FIXED] ล็อคปุ่มให้กดเปลี่ยนไม่ได้ (Readonly) 🌟
            'vat_type': forms.Select(attrs={'class': 'form-select fw-bold', 'style': 'pointer-events: none; background-color: #e9ecef;'}),
        }
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # บังคับให้ดึงรายชื่อจากตารางโซล่าเซลล์ และเอาคนล่าสุดขึ้นก่อน
        self.fields['customer'].queryset = SolarCustomer.objects.all().order_by('-id')

# 🌟 สเต็ป 2: ฟอร์มจัดการเงื่อนไขและสรุปยอดเงิน
class SolarQuotationStep2Form(forms.ModelForm):
    class Meta:
        model = SolarQuotation
        fields = ['discount', 'survey_fee', 'vat_type', 'payment_terms', 'note']
        widgets = {
            'discount': forms.NumberInput(attrs={'class': 'form-control text-end text-danger', 'step': '0.01'}),
            'survey_fee': forms.NumberInput(attrs={'class': 'form-control text-end', 'step': '0.01'}),
            # 🌟 [FIXED] ล็อคปุ่มไม่ให้เปลี่ยน VAT ตอนแก้ไขบิลด้วย 🌟
            'vat_type': forms.Select(attrs={'class': 'form-select fw-bold', 'style': 'pointer-events: none; background-color: #e9ecef;'}),
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

        # 🌟 บังคับให้อนุญาตให้เว้นว่างได้ (เผื่อกรณีพิมพ์ชื่อลูกค้า Walk-in เอง)
        self.fields['customer'].required = False

        # 🌟 ดึงรายชื่อเฉพาะลูกค้าโซล่าเซลล์เรียงคนล่าสุดขึ้นก่อน
        self.fields['customer'].queryset = SolarCustomer.objects.all().order_by('-id')

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
            # 🌟 [FIXED] เปลี่ยนจาก NumberInput เป็น TextInput และเพิ่มคลาส 'amount-input' เพื่อให้ JS รู้จัก
            'amount': forms.TextInput(attrs={
                'class': 'form-control text-end fs-5 fw-bold text-danger amount-input',
                'inputmode': 'decimal' # เด้งคีย์บอร์ดตัวเลขในมือถือ
            }),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'เช่น \n- ค่าน้ำมันรถ 500 บาท\n- ค่าทางด่วน 150 บาท...'}),
        }

# ==========================================
# 👥 ฟอร์มจัดการลูกค้าโซล่าเซลล์
# ==========================================
class SolarCustomerForm(forms.ModelForm):
    class Meta:
        model = SolarCustomer
        fields = ['name', 'branch', 'tax_id', 'contact_person', 'phone', 'email', 'address', 'province', 'district', 'sub_district', 'zip_code', 'location', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'ระบุชื่อลูกค้า / บริษัท'}),
            'branch': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'สำนักงานใหญ่ / สาขา...'}),
            'tax_id': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'เลขผู้เสียภาษี 13 หลัก'}),
            'contact_person': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'ระบุชื่อผู้ติดต่อ'}),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'ตัวอย่าง: 0812345678'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'อีเมล (ถ้ามี)'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'ที่อยู่ (เลขที่/หมู่บ้าน/ถนน)'}),
            'zip_code': forms.TextInput(attrs={'class': 'form-control', 'id': 'input_zipcode'}),
            'location': forms.URLInput(attrs={'class': 'form-control', 'id': 'input_location', 'placeholder': 'กดปุ่มเพื่อดึงพิกัด GPS หรือวางลิงก์'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input', 'id': 'id_is_active'}),
        }