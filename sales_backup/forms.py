from django import forms
from django.core.validators import RegexValidator
from .models import Quotation

class QuotationForm(forms.ModelForm):
    # วันที่ (ปิดประวัติด้วย)
    date = forms.DateField(
        widget=forms.DateInput(attrs={'class': 'form-control datepicker', 'placeholder': 'วว/ดด/ปปปป', 'autocomplete': 'off'}),
        input_formats=['%d/%m/%Y', '%Y-%m-%d']
    )
    valid_until = forms.DateField(
        widget=forms.DateInput(attrs={'class': 'form-control datepicker', 'placeholder': 'วว/ดด/ปปปป', 'autocomplete': 'off'}),
        input_formats=['%d/%m/%Y', '%Y-%m-%d']
    )

    # เบอร์โทรศัพท์ (ปิดประวัติ)
    customer_phone = forms.CharField(
        label="เบอร์โทรศัพท์",
        required=True,
        validators=[RegexValidator(r'^0\d{8,9}$', 'เบอร์โทรต้องเป็นตัวเลข 9-10 หลัก (เช่น 081xxxxxxx)')],
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'ห้ามเว้น ใส่เฉพาะตัวเลขเท่านั้น',
            'autocomplete': 'off' # ✅ ปิดประวัติ
        })
    )

    # เลขผู้เสียภาษี (ปิดประวัติ)
    customer_tax_id = forms.CharField(
        label="เลขผู้เสียภาษี",
        required=False,
        validators=[RegexValidator(r'^\d{13}$', 'เลขผู้เสียภาษีต้องเป็นตัวเลข 13 หลัก')],
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'ระบุเลข 13 หลัก (ถ้ามี)',
            'autocomplete': 'off' # ✅ ปิดประวัติ
        })
    )

    class Meta:
        model = Quotation
        fields = ['date', 'valid_until', 'customer_name', 'customer_tax_id', 'customer_phone', 'customer_address', 'note']
        widgets = {
            'customer_name': forms.TextInput(attrs={
                'class': 'form-control', 
                'required': 'true', 
                'placeholder': 'ระบุชื่อลูกค้า...',
                'autocomplete': 'off' # ✅ ปิดประวัติ
            }),
            'customer_address': forms.Textarea(attrs={
                'class': 'form-control', 
                'rows': 3,
                'autocomplete': 'off' # ✅ ปิดประวัติ
            }),
            'note': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def clean_customer_name(self):
        name = self.cleaned_data.get('customer_name')
        if not name:
            raise forms.ValidationError("กรุณาระบุชื่อลูกค้า")
        return name