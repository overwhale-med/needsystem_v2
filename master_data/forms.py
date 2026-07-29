from django import forms
from django.core.exceptions import ValidationError
from .models import Customer, Supplier, CompanyInfo
from manufacturing.models import MfgBranch

class CustomerForm(forms.ModelForm):
    phone = forms.CharField(label="เบอร์โทรศัพท์", required=False, widget=forms.TextInput(attrs={'class': 'form-control', 'id': 'input_phone', 'placeholder': 'ตัวอย่าง: 0812345678', 'autocomplete': 'off'}))
    class Meta:
        model = Customer
        fields = '__all__'
        exclude = ['code', 'created_at', 'updated_at', 'credit_limit', 'credit_term']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'ระบุชื่อลูกค้า / บริษัท', 'autocomplete': 'off'}),
            'tax_id': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'เลขผู้เสียภาษี 13 หลัก', 'autocomplete': 'off'}),
            'contact_person': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'ระบุชื่อผู้ติดต่อ', 'autocomplete': 'off'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'autocomplete': 'off'}),
            'note': forms.Textarea(attrs={'rows': 3}),
            'zip_code': forms.TextInput(attrs={'id': 'input_zipcode', 'autocomplete': 'off'}),
            'location': forms.TextInput(attrs={'id': 'input_location', 'placeholder': 'กดปุ่มเพื่อดึงพิกัด GPS', 'autocomplete': 'off'}),
        }
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields:
            if field != 'is_active':
                self.fields[field].widget.attrs.update({'class': 'form-control'})
        if 'is_active' in self.fields:
            self.fields['is_active'].widget.attrs.update({'class': 'form-check-input ms-2'})
    
    def clean_phone(self):
        data = self.cleaned_data.get('phone')
        if not data: return data
        cleaned_data = data.replace('-', '').replace(' ', '')
        if not cleaned_data.isdigit(): raise ValidationError("เบอร์โทรต้องเป็นตัวเลขเท่านั้น")
        if len(cleaned_data) != 10: raise ValidationError(f"เบอร์โทรต้องมี 10 หลัก (ตอนนี้มี {len(cleaned_data)} หลัก)")
        return cleaned_data

class SupplierForm(forms.ModelForm):
    phone = forms.CharField(label="เบอร์โทรศัพท์", required=False, widget=forms.TextInput(attrs={'class': 'form-control', 'autocomplete': 'off'}))
    class Meta:
        model = Supplier
        fields = ['name', 'tax_id', 'phone', 'contact_name', 'address']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'ระบุชื่อร้านค้า / บริษัท', 'autocomplete': 'off'}),
            'tax_id': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'เลขผู้เสียภาษี 13 หลัก', 'autocomplete': 'off'}),
            'contact_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'ระบุชื่อผู้ติดต่อ', 'autocomplete': 'off'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'autocomplete': 'off'}),
        }
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields:
            self.fields[field].widget.attrs.update({'class': 'form-control'})

class CompanyInfoForm(forms.ModelForm):
    class Meta:
        model = CompanyInfo
        fields = '__all__'
        widgets = {
            'name_th': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'ชื่อบริษัท (ภาษาไทย)'}),
            'name_en': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'ชื่อบริษัท (ภาษาอังกฤษ)'}),
            'tax_id': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'เลขประจำตัวผู้เสียภาษี'}),
            'branch': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'เช่น สำนักงานใหญ่'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'website': forms.URLInput(attrs={'class': 'form-control'}),
            # 🌟 [UPDATE] ทำให้ช่องโควตารวมอ่านได้อย่างเดียว (Readonly) และเปลี่ยนสีให้ดูรู้ว่าเป็นช่อง Auto
            'weekly_job_quota': forms.NumberInput(attrs={'class': 'form-control fw-bold text-primary bg-light', 'style': 'font-size: 1.5rem; text-align: center;', 'readonly': 'readonly', 'id': 'global-quota-input'}),
        }

class MfgBranchForm(forms.ModelForm):
    class Meta:
        model = MfgBranch
        fields = ['name', 'weekly_quota']
        widgets = {
            # 🌟 [UPDATE] ปลดล็อกช่องชื่อ ให้สามารถแก้ไขหรือพิมพ์ชื่อฐานผลิตใหม่ได้
            'name': forms.TextInput(attrs={'class': 'form-control form-control-sm fw-bold text-dark', 'placeholder': 'เช่น ฐานผลิตเชียงใหม่'}),
            # 🌟 [UPDATE] ใส่คลาส branch-quota ให้ JavaScript รู้ว่าต้องเอาช่องนี้ไปบวกกัน
            'weekly_quota': forms.NumberInput(attrs={'class': 'form-control form-control-sm text-center fw-bold text-success branch-quota', 'min': '0'}),
        }

# 🌟 [UPDATE] อนุญาตให้ลบ (can_delete=True) ได้แล้ว
MfgBranchFormSet = forms.modelformset_factory(
    MfgBranch,
    form=MfgBranchForm,
    extra=0,
    can_delete=True 
)