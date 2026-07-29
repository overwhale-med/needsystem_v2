from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from django.http import JsonResponse
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger

from .models import Customer, Province, Amphure, Tambon, Supplier, CompanyInfo
# 🌟 [UPDATE] นำเข้า MfgBranchFormSet 
from .forms import CustomerForm, SupplierForm, CompanyInfoForm, MfgBranchFormSet
# 🌟 [NEW] นำเข้าโมเดล MfgBranch
from manufacturing.models import MfgBranch

# --- Company Settings (ตั้งค่าองค์กรและโควตา) ---

@login_required
def company_settings(request):
    company = CompanyInfo.objects.first()
    if not company:
        company = CompanyInfo.objects.create(name_th="บริษัท NEED System จำกัด", tax_id="0000000000000")

    if request.method == 'POST':
        form = CompanyInfoForm(request.POST, request.FILES, instance=company)
        # 🌟 [NEW] รับค่าจากตารางโควตาสาขาที่ผู้ใช้กรอกเข้ามา
        branch_formset = MfgBranchFormSet(request.POST, queryset=MfgBranch.objects.all())
        
        if form.is_valid() and branch_formset.is_valid():
            form.save()
            branch_formset.save() # 🌟 บันทึกโควตาย่อยลงฐานข้อมูล
            messages.success(request, "✅ บันทึกข้อมูลบริษัท และอัปเดตโควตาการผลิตของทุกสาขาเรียบร้อยแล้ว!")
            return redirect('company_settings')
        else:
            messages.error(request, "❌ กรุณาตรวจสอบข้อมูลให้ถูกต้อง")
    else:
        form = CompanyInfoForm(instance=company)
        # 🌟 [NEW] ส่งข้อมูลสาขาที่มีอยู่ไปให้หน้าเว็บแสดงผล
        branch_formset = MfgBranchFormSet(queryset=MfgBranch.objects.all().order_by('id'))

    return render(request, 'master_data/company/company_settings.html', {
        'form': form,
        'branch_formset': branch_formset, # 🌟 ส่งตัวแปรไปยัง HTML
        'title': 'ตั้งค่าข้อมูลบริษัท & โควตาการผลิต'
    })


# --- Customer Management ---

@login_required
def customer_list(request):
    search = request.GET.get('search', '')
    if search:
        customer_list = Customer.objects.filter(
            Q(name__icontains=search) | Q(code__icontains=search) |
            Q(phone__icontains=search) | Q(tax_id__icontains=search)
        ).order_by('-created_at')
    else:
        customer_list = Customer.objects.all().order_by('-created_at')

    paginator = Paginator(customer_list, 20) 
    page = request.GET.get('page')
    try:
        customers = paginator.page(page)
    except PageNotAnInteger:
        customers = paginator.page(1)
    except EmptyPage:
        customers = paginator.page(paginator.num_pages)

    return render(request, 'master_data/customer/customer_list.html', {
        'customers': customers,
        'search': search
    })

@login_required
def customer_create(request):
    if request.method == 'POST':
        form = CustomerForm(request.POST)
        if form.is_valid():
            cust = form.save()
            messages.success(request, f"เพิ่มลูกค้า {cust.name} เรียบร้อย")
            next_url = request.GET.get('next')
            if next_url:
                return redirect(next_url) 
            return redirect('customer_list') 
    else:
        form = CustomerForm()

    return render(request, 'master_data/customer/customer_form.html', {'form': form, 'title': 'เพิ่มลูกค้าใหม่'})

@login_required
def customer_edit(request, pk):
    customer = get_object_or_404(Customer, pk=pk)
    if request.method == 'POST':
        form = CustomerForm(request.POST, instance=customer)
        if form.is_valid():
            form.save()
            messages.success(request, "บันทึกข้อมูลเรียบร้อย")
            return redirect('customer_list')
    else:
        form = CustomerForm(instance=customer)

    return render(request, 'master_data/customer/customer_form.html', {'form': form, 'title': 'แก้ไขข้อมูลลูกค้า'})

@login_required
def customer_delete(request, pk):
    customer = get_object_or_404(Customer, pk=pk)
    customer.delete()
    messages.success(request, "ลบข้อมูลเรียบร้อย")
    return redirect('customer_list')


# --- Address API ---

@login_required
def get_provinces(request):
    provinces = list(Province.objects.values('id', 'name_th').order_by('name_th'))
    return JsonResponse(provinces, safe=False)

@login_required
def get_amphures(request):
    province_id = request.GET.get('province_id')
    amphures = []
    if province_id:
        amphures = list(Amphure.objects.filter(province_id=province_id).values('id', 'name_th').order_by('name_th'))
    return JsonResponse(amphures, safe=False)

@login_required
def get_tambons(request):
    amphure_id = request.GET.get('amphure_id')
    tambons = []
    if amphure_id:
        tambons = list(Tambon.objects.filter(amphure_id=amphure_id).values('id', 'name_th', 'zip_code').order_by('name_th'))
    return JsonResponse(tambons, safe=False)


# --- Supplier Management ---

@login_required
def supplier_list(request):
    search = request.GET.get('search', '')
    if search:
        supplier_qs = Supplier.objects.filter(
            Q(name__icontains=search) | Q(code__icontains=search) |
            Q(phone__icontains=search) | Q(tax_id__icontains=search)
        ).order_by('-id')  
    else:
        supplier_qs = Supplier.objects.all().order_by('-id')  

    paginator = Paginator(supplier_qs, 20)
    page = request.GET.get('page')
    try: 
        suppliers = paginator.page(page)
    except PageNotAnInteger: 
        suppliers = paginator.page(1)
    except EmptyPage: 
        suppliers = paginator.page(paginator.num_pages)

    return render(request, 'master_data/supplier/supplier_list.html', {
        'suppliers': suppliers, 'search': search
    })

@login_required
def supplier_create(request):
    if request.method == 'POST':
        form = SupplierForm(request.POST)
        if form.is_valid():
            sup = form.save()
            messages.success(request, f"เพิ่มร้านค้า {sup.name} เรียบร้อย")
            return redirect('supplier_list')
    else:
        form = SupplierForm()
    return render(request, 'master_data/supplier/supplier_form.html', {'form': form, 'title': 'เพิ่มร้านค้าใหม่ (Supplier)'})

@login_required
def supplier_edit(request, pk):
    supplier = get_object_or_404(Supplier, pk=pk)
    if request.method == 'POST':
        form = SupplierForm(request.POST, instance=supplier)
        if form.is_valid():
            form.save()
            messages.success(request, "บันทึกข้อมูลเรียบร้อย")
            return redirect('supplier_list')
    else:
        form = SupplierForm(instance=supplier)
    return render(request, 'master_data/supplier/supplier_form.html', {'form': form, 'title': 'แก้ไขข้อมูลร้านค้า'})

@login_required
def supplier_delete(request, pk):
    supplier = get_object_or_404(Supplier, pk=pk)
    supplier.delete()
    messages.success(request, "ลบข้อมูลร้านค้าเรียบร้อย")
    return redirect('supplier_list')