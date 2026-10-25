from django import forms
from django.forms import inlineformset_factory
from .models import SolarProduct, SolarStockMovement, SolarStandardBOM

# 🌟 ฟอร์มสำหรับจัดการสินค้าในคลัง (Solar Inventory)
class SolarProductForm(forms.ModelForm):
    class Meta:
        model = SolarProduct
        # 🌟 [UPDATE] เพิ่ม 'supplier' เข้าไปในรายการ fields
        fields = ['product_type', 'image', 'code', 'category', 'rm_category', 'supplier', 'name', 'unit', 'cost_price', 'sell_price', 'stock_qty', 'min_level', 'is_active']
        widgets = {
            'product_type': forms.Select(attrs={'class': 'form-select fw-bold text-primary'}),
            'image': forms.FileInput(attrs={'class': 'form-control'}),

            'code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'เว้นว่างไว้ ระบบจะสร้างรหัสให้โดยอัตโนมัติ'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'rm_category': forms.Select(attrs={'class': 'form-select'}),

            # 🌟 [NEW] ตั้งค่าหน้าตาให้ช่องเลือกร้านค้า
            'supplier': forms.Select(attrs={'class': 'form-select'}),

            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'ระบุชื่อแพ็กเกจ หรือ อุปกรณ์เสริม'}),
            'unit': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'เช่น ชุด, แผง, เมตร'}),

            'cost_price': forms.TextInput(attrs={'class': 'form-control text-end auto-comma', 'placeholder': '0.00'}),
            'sell_price': forms.TextInput(attrs={'class': 'form-control text-end fw-bold text-success auto-comma', 'placeholder': '0.00'}),
            'stock_qty': forms.TextInput(attrs={'class': 'form-control text-end auto-comma', 'placeholder': '0'}),
            'min_level': forms.TextInput(attrs={'class': 'form-control text-end auto-comma', 'placeholder': '0'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input', 'style': 'transform: scale(1.5);'}),
        }

    def __init__(self, *args, **kwargs):
        # 1. กลไกเดิม: ดักจับข้อมูลตอนกดบันทึก (POST) เพื่อถอดลูกน้ำออกก่อนเซฟลงฐานข้อมูล
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

        # 🌟 [NEW] กลไกใหม่: ดักจับข้อมูลตอนเปิดหน้าเว็บเพื่อแก้ไข (GET) เพื่อเติมลูกน้ำใส่กลับเข้าไปให้สวยงาม
        if self.instance and self.instance.pk:
            # จัดฟอร์แมตกลุ่มราคา ให้มีลูกน้ำและทศนิยม 2 ตำแหน่งเสมอ
            for field in ['cost_price', 'sell_price']:
                val = self.initial.get(field)
                if val is not None:
                    try:
                        self.initial[field] = "{:,.2f}".format(float(val))
                    except (ValueError, TypeError):
                        pass

            # จัดฟอร์แมตกลุ่มจำนวนสต็อก ถ้าเป็นเลขลงตัวจะไม่โชว์ทศนิยม
            for field in ['stock_qty', 'min_level']:
                val = self.initial.get(field)
                if val is not None:
                    try:
                        val_float = float(val)
                        if val_float.is_integer():
                            self.initial[field] = "{:,.0f}".format(val_float)
                        else:
                            self.initial[field] = "{:,.2f}".format(val_float)
                    except (ValueError, TypeError):
                        pass

class SolarStockMovementForm(forms.ModelForm):
    class Meta:
        model = SolarStockMovement
        fields = ['product', 'movement_type', 'quantity', 'reference_doc']
        widgets = {
            'product': forms.Select(attrs={'class': 'form-select fw-bold'}),
            'movement_type': forms.Select(attrs={'class': 'form-select'}),
            'quantity': forms.TextInput(attrs={'class': 'form-control text-end', 'placeholder': '0.00'}),
            'reference_doc': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'เช่น ยอดยกมา, เลขที่ PO, ปรับปรุงสต็อก'}),
        }

class SolarStandardBOMForm(forms.ModelForm):
    class Meta:
        model = SolarStandardBOM
        fields = ['raw_material', 'quantity', 'note']
        widgets = {
            # 🌟 ใส่คลาส searchable-select เพื่อเป็นตัวบอกให้สคริปต์หน้าบ้านรู้ว่าต้องเปลี่ยนเป็นช่องค้นหา
            'raw_material': forms.Select(attrs={'class': 'form-select form-select-sm fw-bold searchable-select', 'style': 'width: 100%;'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control text-center', 'step': '0.01'}),
            'note': forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'หมายเหตุ'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 🌟 ล็อคให้เลือกได้เฉพาะ RM และดึงข้อมูลหมวดหมู่ (rm_category) มาด้วย
        queryset = SolarProduct.objects.filter(is_active=True, product_type='RM').select_related('rm_category')
        self.fields['raw_material'].queryset = queryset

        # 🌟 ปรับแต่งการแสดงผลข้อความใน Dropdown (Label) ให้โชว์หมวดหมู่ด้วย
        self.fields['raw_material'].label_from_instance = lambda obj: f"[{obj.rm_category.name if obj.rm_category else 'ไม่มีหมวดหมู่'}] - {obj.name}"

# 🌟 FormSet สำหรับจัดการสูตรการผลิตมาตรฐาน
SolarStandardBOMFormSet = inlineformset_factory(
    SolarProduct, SolarStandardBOM,
    form=SolarStandardBOMForm,
    fk_name='package',
    extra=1,
    can_delete=True
)