from django import forms
from .models import BOM, BOMItem
from inventory.models import Product, Category 

class BOMForm(forms.ModelForm):
    category = forms.ModelChoiceField(
        queryset=Category.objects.all(),
        required=False,
        label='ตัวกรอง: หมวดหมู่สินค้า',
        empty_label='--- ทั้งหมด ---',
        widget=forms.Select(attrs={'class': 'form-select shadow-sm text-primary fw-bold', 'id': 'id_category'})
    )

    class Meta:
        model = BOM
        fields = ['product', 'name', 'note']
        labels = {
            'product': 'สินค้าสำเร็จรูป (FG)',
            'name': 'ชื่อสูตรผลิต',
            'note': 'หมายเหตุ'
        }
        widgets = {
            'product': forms.Select(attrs={'class': 'form-select shadow-sm border-primary', 'required': 'required', 'id': 'id_product'}),
            'name': forms.TextInput(attrs={'class': 'form-control shadow-sm', 'placeholder': 'เช่น สูตรมาตรฐาน 1 ห้องนอน', 'required': 'required'}),
            'note': forms.Textarea(attrs={'class': 'form-control shadow-sm', 'rows': 2, 'placeholder': 'รายละเอียดเพิ่มเติม (ถ้ามี)'}),
        }

    def __init__(self, *args, **kwargs):
        super(BOMForm, self).__init__(*args, **kwargs)
        self.fields['product'].queryset = Product.objects.filter(product_type='FG', is_active=True)
        if self.instance and self.instance.pk and self.instance.product:
            self.fields['category'].initial = self.instance.product.category

class BOMItemForm(forms.ModelForm):
    class Meta:
        model = BOMItem
        fields = ['raw_material', 'quantity']
        widgets = {
            # 🌟 [UPDATE] ระบุคลาส select2-ajax เพื่อบอกหน้าเว็บว่านี่คือกล่องค้นหา
            'raw_material': forms.Select(attrs={'class': 'form-select shadow-sm select2-ajax'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control shadow-sm text-center', 'step': '0.0001', 'min': '0'}),
        }

    def __init__(self, *args, **kwargs):
        super(BOMItemForm, self).__init__(*args, **kwargs)
        
        # 🌟 [MAGIC FIX] ควบคุมไม่ให้ดึงข้อมูลวัตถุดิบ 200 รายการมาโหลดบนหน้า HTML
        # แต่ยังคงดึงข้อมูลมาทั้งหมดตอนบันทึกข้อมูลเพื่อความถูกต้องของระบบ
        if 'data' in kwargs or len(args) > 0:
            self.fields['raw_material'].queryset = Product.objects.exclude(product_type='FG').filter(is_active=True)
        elif self.instance and self.instance.pk and self.instance.raw_material:
            self.fields['raw_material'].queryset = Product.objects.filter(pk=self.instance.raw_material.pk)
        else:
            self.fields['raw_material'].queryset = Product.objects.none()
        
        # ตัด 0 ทศนิยม
        if self.instance and self.instance.pk and self.instance.quantity is not None:
            qty = self.instance.quantity
            if qty == int(qty):
                self.initial['quantity'] = int(qty)
            else:
                self.initial['quantity'] = float(qty)

BOMItemFormSet = forms.inlineformset_factory(
    BOM, BOMItem, form=BOMItemForm, extra=1, can_delete=True
)