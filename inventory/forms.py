from django import forms
from django.forms import inlineformset_factory
from .models import StockMovement, Product, ProductSupplier

class StockInForm(forms.ModelForm):
    doc_reference = forms.CharField(required=False, label="อ้างอิงเอกสาร (PO)", widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'เช่น PO-2601-001'}))
    doc_note = forms.CharField(required=False, label="หมายเหตุ", widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'รายละเอียดเพิ่มเติม...'}))
    class Meta:
        model = StockMovement
        fields = ['product', 'quantity']
        widgets = {
            'product': forms.Select(attrs={'class': 'form-select select2'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'min': '0.01', 'step': '0.01', 'placeholder': 'จำนวนที่รับ'}),
        }
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['product'].queryset = Product.objects.filter(is_active=True)
        self.fields['product'].label = "เลือกสินค้า/วัตถุดิบ"

class StockOutForm(forms.ModelForm):
    doc_reference = forms.CharField(required=False, label="อ้างอิงเอกสาร (Job No.)", widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'เช่น ใบสั่งผลิต / ใบเสีย'}))
    doc_note = forms.CharField(required=False, label="หมายเหตุ", widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'สาเหตุการเบิก...'}))
    class Meta:
        model = StockMovement
        fields = ['product', 'quantity']
        widgets = {
            'product': forms.Select(attrs={'class': 'form-select select2'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'min': '0.01', 'step': '0.01', 'placeholder': 'จำนวนที่เบิก'}),
        }
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['product'].queryset = Product.objects.filter(is_active=True)
        self.fields['product'].label = "เลือกสินค้า/วัตถุดิบ"

class ProductFGForm(forms.ModelForm):
    cost_price = forms.CharField(label="ราคาทุน", widget=forms.TextInput(attrs={'class': 'form-control number-input', 'style': 'text-align: right;', 'placeholder': '0.00'}))
    sell_price = forms.CharField(required=False, label="ราคาขาย", widget=forms.TextInput(attrs={'class': 'form-control number-input', 'style': 'text-align: right;', 'placeholder': '0.00'}))

    class Meta:
        model = Product
        # เก็บเฉพาะฟิลด์ของสินค้าสำเร็จรูป
        fields = ['code', 'name', 'unit', 'category', 'cost_price', 'sell_price', 'min_level', 'image', 'standard_blueprint', 'is_active']
        widgets = {
            'code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'เว้นว่างเพื่อสร้างรหัสอัตโนมัติ'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'unit': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'เช่น ชิ้น, กล่อง, เมตร...'}),
            'category': forms.Select(attrs={'class': 'form-select select2'}),
            'min_level': forms.NumberInput(attrs={'class': 'form-control', 'value': 5}),
            'image': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'standard_blueprint': forms.ClearableFileInput(attrs={'class': 'form-control', 'accept': '.pdf,image/*'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['code'].required = False
        self.fields['name'].label = "ชื่อสินค้า*"
        self.fields['image'].label = "รูปสินค้า"
        if self.instance.pk:
            if self.instance.cost_price: self.initial['cost_price'] = f"{self.instance.cost_price:,.2f}"
            if self.instance.sell_price: self.initial['sell_price'] = f"{self.instance.sell_price:,.2f}"
        else:
            self.initial['cost_price'] = ''
            self.initial['sell_price'] = ''

    def clean_cost_price(self): return self.cleaned_data['cost_price'].replace(',', '') if self.cleaned_data['cost_price'] else 0
    def clean_sell_price(self): return self.cleaned_data['sell_price'].replace(',', '') if self.cleaned_data['sell_price'] else 0


class ProductRMForm(forms.ModelForm):
    cost_price = forms.CharField(label="ราคาทุน", widget=forms.TextInput(attrs={'class': 'form-control number-input', 'style': 'text-align: right;', 'placeholder': '0.00'}))

    class Meta:
        model = Product
        fields = ['code', 'name', 'unit', 'rm_category', 'supplier', 'cost_price', 'min_level', 'image', 'is_active']
        widgets = {
            'code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'เว้นว่างเพื่อสร้างรหัสอัตโนมัติ'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'unit': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'เช่น ชิ้น, กล่อง, เมตร...'}),
            'rm_category': forms.Select(attrs={'class': 'form-select select2'}),
            'supplier': forms.Select(attrs={'class': 'form-select select2'}),
            'min_level': forms.NumberInput(attrs={'class': 'form-control', 'value': 5}),
            'image': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['code'].required = False

        # 🌟 [NEW] เปลี่ยนชื่อ Label ของรหัส ให้ตรงกับบริบทวัตถุดิบ
        self.fields['code'].label = "รหัสวัตถุดิบ/SKU"
        self.fields['name'].label = "ชื่อวัตถุดิบ*"
        self.fields['image'].label = "รูปวัตถุดิบ"

        if self.instance.pk:
            if self.instance.cost_price: self.initial['cost_price'] = f"{self.instance.cost_price:,.2f}"
        else:
            self.initial['cost_price'] = ''

    def clean_cost_price(self): return self.cleaned_data['cost_price'].replace(',', '') if self.cleaned_data['cost_price'] else 0

class ProductSupplierForm(forms.ModelForm):
    cost_price = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control form-control-sm number-input text-end',
            'placeholder': '0.00'
        })
    )
    class Meta:
        model = ProductSupplier
        fields = ['supplier', 'supplier_part_no', 'cost_price', 'is_default']
        widgets = {
            'supplier': forms.Select(attrs={'class': 'form-select select2'}),
            'supplier_part_no': forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'รหัสอ้างอิงร้าน'}),
            'is_default': forms.CheckboxInput(attrs={'class': 'form-check-input'})
        }
    def clean_cost_price(self):
        val = self.cleaned_data.get('cost_price')
        return val.replace(',', '') if val else 0
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk and self.instance.cost_price:
            self.initial['cost_price'] = f"{self.instance.cost_price:,.2f}"

ProductSupplierFormSet = inlineformset_factory(
    Product, ProductSupplier, form=ProductSupplierForm,
    extra=1, can_delete=True
)