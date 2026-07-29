from django import forms
from .models import LeaveRequest, Employee
from django.core.exceptions import ValidationError
import datetime

# --- LeaveRequestForm (คงเดิม) ---
class LeaveRequestForm(forms.ModelForm):
    class Meta:
        model = LeaveRequest
        fields = ['leave_type', 'start_date', 'end_date', 'reason']
        widgets = {
            'leave_type': forms.Select(attrs={'class': 'form-select'}),
            'start_date': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'dd/mm/yyyy', 'autocomplete': 'off'}),
            'end_date': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'dd/mm/yyyy', 'autocomplete': 'off'}),
            'reason': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
    def clean(self):
        cleaned_data = super().clean()
        start = cleaned_data.get("start_date")
        end = cleaned_data.get("end_date")
        if start and end and end < start: raise ValidationError("วันสิ้นสุดต้องไม่ก่อนวันเริ่ม")
        return cleaned_data

# ==========================================
# ✅ ฟอร์มลงทะเบียนพนักงาน (รองรับเงินเดือนแบบมีลูกน้ำ 50,000.00)
# ==========================================
class EmployeeForm(forms.ModelForm):
    create_user_account = forms.BooleanField(required=False, widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}))
    username = forms.CharField(required=False, widget=forms.TextInput(attrs={'class': 'form-control', 'autocomplete': 'off'}))
    password = forms.CharField(required=False, widget=forms.PasswordInput(attrs={'class': 'form-control', 'autocomplete': 'new-password'}))
    email = forms.EmailField(required=False, widget=forms.EmailInput(attrs={'class': 'form-control', 'autocomplete': 'off'}))

    # ✅ เปลี่ยนเงินเดือนเป็น CharField (รับข้อความ) เพื่อให้โชว์ลูกน้ำได้
    salary = forms.CharField(required=False, widget=forms.TextInput(attrs={
        'class': 'form-control',
        'id': 'input_salary',      # ID สำหรับ JS
        'autocomplete': 'off'
    }))

    class Meta:
        model = Employee
        fields = '__all__'
        # 🌟 เอา emp_id ออกจาก exclude เพื่อให้โชว์ในฟอร์ม 🌟
        exclude = ['user', 'resign_date']

        widgets = {
            # 🌟 เพิ่ม widget สำหรับ emp_id 🌟
            'emp_id': forms.TextInput(attrs={'class': 'form-control font-monospace text-primary fw-bold bg-light', 'readonly': 'readonly', 'placeholder': 'คลิกปุ่มเพื่อดึงรหัส ->', 'id': 'id_emp_id'}),

            'photo': forms.FileInput(attrs={'class': 'form-control'}),
            'signature': forms.FileInput(attrs={'class': 'form-control'}),
            'prefix': forms.TextInput(attrs={'class': 'form-control', 'autocomplete': 'off'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control', 'autocomplete': 'off'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control', 'autocomplete': 'off'}),
            'nickname': forms.TextInput(attrs={'class': 'form-control', 'autocomplete': 'off'}),
            'id_card': forms.TextInput(attrs={'class': 'form-control', 'autocomplete': 'off'}),
            'gender': forms.Select(attrs={'class': 'form-select'}),
            'birth_date': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'dd/mm/yyyy', 'autocomplete': 'off'}),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'autocomplete': 'off'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'emp_type': forms.Select(attrs={'class': 'form-select'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'position': forms.Select(attrs={'class': 'form-select'}),
            'department': forms.Select(attrs={'class': 'form-select'}),
            'start_date': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'dd/mm/yyyy', 'autocomplete': 'off'}),
            'social_security_id': forms.TextInput(attrs={'class': 'form-control', 'autocomplete': 'off'}),
            'bank_account_no': forms.TextInput(attrs={'class': 'form-control', 'autocomplete': 'off'}),
            
            # 🌟 [NEW] เพิ่ม Widget สำหรับจัดกลุ่มทีมขาย 🌟
            'sales_group': forms.Select(attrs={'class': 'form-select border-success'}),
            'group_role': forms.Select(attrs={'class': 'form-select border-success'}),
            
            'introducer': forms.Select(attrs={'class': 'form-select'}),
            'business_rank': forms.Select(attrs={'class': 'form-select'}),
            'commission_rate': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'bank_name': forms.TextInput(attrs={'class': 'form-control', 'autocomplete': 'off'}),
            'bank_account': forms.TextInput(attrs={'class': 'form-control', 'autocomplete': 'off'}),
        }

    # ✅ ฟังก์ชันพิเศษ: ล้างลูกน้ำออกก่อนบันทึก (50,000.00 -> 50000.00)
    def clean_salary(self):
        data = self.cleaned_data.get('salary')
        if not data:
            return 0
        if isinstance(data, str):
            # ลบลูกน้ำออก
            return data.replace(',', '')
        return data