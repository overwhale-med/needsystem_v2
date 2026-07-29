import datetime
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from django.utils import timezone

from .models import SolarPurchaseOrder, SolarPurchaseOrderItem
from .forms import SolarPurchaseOrderForm, SolarOrderItemFormSet
from inventory.models import Product
from master_data.models import Supplier

# ------------------------------------------
# 🛡️ ระบบเช็คสิทธิ์ (Gatekeeper)
# ------------------------------------------
def is_purchasing_staff(user):
    if user.is_superuser: return True
    if hasattr(user, 'employee') and user.employee:
        dept = getattr(user.employee.department, 'name', '')
        if 'จัดซื้อ' in dept or 'Purchasing' in dept: return True
    return False

def is_purchasing_manager(user):
    if user.is_superuser: return True
    if hasattr(user, 'employee') and user.employee:
        job_title = getattr(user.employee.position, 'title', '').lower()
        rank = getattr(user.employee, 'business_rank', '').lower()
        if 'manager' in job_title or 'ผู้จัดการ' in job_title or rank in ['manager', 'director', 'executive']:
            return True
    return False

# ------------------------------------------
# 🛒 Views สำหรับระบบจัดซื้อโซล่าเซลล์
# ------------------------------------------
@login_required
def solar_po_list(request):
    if not is_purchasing_staff(request.user):
        messages.error(request, "❌ บัญชีของคุณไม่มีสิทธิ์เข้าถึงระบบจัดซื้อโซล่า")
        return redirect('dashboard')

    search_query = request.GET.get('q', '')
    status_filter = request.GET.get('status', '')

    pos = SolarPurchaseOrder.objects.all().order_by('-created_at')

    if search_query:
        pos = pos.filter(
            Q(code__icontains=search_query) |
            Q(supplier__name__icontains=search_query) |
            Q(supplier_name_free_text__icontains=search_query)
        )
    if status_filter:
        pos = pos.filter(status=status_filter)

    is_manager = is_purchasing_manager(request.user)

    context = {
        'pos': pos,
        'search_query': search_query,
        'status_filter': status_filter,
        'is_manager': is_manager,
    }
    return render(request, 'solar_purchasing/solar_po_list.html', context)

@login_required
def solar_po_create(request):
    if not is_purchasing_staff(request.user): return redirect('solar_po_list')

    if request.method == 'POST':
        form = SolarPurchaseOrderForm(request.POST)
        formset = SolarOrderItemFormSet(request.POST)

        if form.is_valid() and formset.is_valid():
            po = form.save(commit=False)
            po.status = 'DRAFT' # บังคับเป็นร่างเพื่อรอผู้จัดการอนุมัติ
            po.buyer = getattr(request.user, 'employee', None)
            po.save()

            formset.instance = po
            formset.save()

            # คำนวณยอดรวมสุทธิ
            total = sum(item.total_cost for item in po.items.all() if item.total_cost)
            po.total_amount = total
            po.save()

            messages.success(request, f"✅ สร้างใบสั่งซื้อโซล่า {po.code} เรียบร้อยแล้ว (รอผู้จัดการอนุมัติ)")
            return redirect('solar_po_list')
        else:
            messages.error(request, "❌ กรุณาตรวจสอบข้อมูลให้ครบถ้วน")
    else:
        form = SolarPurchaseOrderForm(initial={'date': timezone.now().date()})
        formset = SolarOrderItemFormSet()

    # ส่งลิสต์สินค้าหมวดหมู่โซล่าไปให้หน้าเว็บ
    solar_products = Product.objects.filter(is_active=True)
    suppliers = Supplier.objects.all()

    return render(request, 'solar_purchasing/solar_po_form.html', {
        'form': form,
        'formset': formset,
        'products': solar_products,
        'suppliers': suppliers
    })

@login_required
def solar_po_edit(request, po_id):
    if not is_purchasing_staff(request.user): return redirect('solar_po_list')

    po = get_object_or_404(SolarPurchaseOrder, id=po_id)
    is_manager = is_purchasing_manager(request.user)

    if request.method == 'POST':
        form = SolarPurchaseOrderForm(request.POST, instance=po)
        formset = SolarOrderItemFormSet(request.POST, instance=po)

        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()

            total = sum(item.total_cost for item in po.items.all() if item.total_cost)
            po.total_amount = total
            po.save()

            messages.success(request, f"✅ แก้ไขใบสั่งซื้อ {po.code} เรียบร้อยแล้ว")
            return redirect('solar_po_list')
        else:
            messages.error(request, "❌ กรุณาตรวจสอบข้อมูลให้ครบถ้วน")
    else:
        form = SolarPurchaseOrderForm(instance=po)
        formset = SolarOrderItemFormSet(instance=po)

    solar_products = Product.objects.filter(is_active=True)
    suppliers = Supplier.objects.all()

    return render(request, 'solar_purchasing/solar_po_form.html', {
        'form': form,
        'formset': formset,
        'po': po,
        'is_manager': is_manager,
        'products': solar_products,
        'suppliers': suppliers
    })

@login_required
def solar_po_approve(request, po_id):
    po = get_object_or_404(SolarPurchaseOrder, id=po_id)
    if is_purchasing_manager(request.user) and po.status == 'DRAFT':
        po.status = 'APPROVED'
        po.save()
        messages.success(request, f"✅ อนุมัติใบสั่งซื้อ {po.code} เรียบร้อยแล้ว! (แจ้งเตือนแผนกคลังสินค้าและบัญชีแล้ว)")
    else:
        messages.error(request, "❌ คุณไม่มีสิทธิ์อนุมัติ หรือสถานะเอกสารไม่ถูกต้อง")
    return redirect('solar_po_list')

@login_required
def solar_po_cancel(request, po_id):
    po = get_object_or_404(SolarPurchaseOrder, id=po_id)
    if is_purchasing_manager(request.user) and po.status in ['DRAFT', 'APPROVED']:
        po.status = 'CANCELLED'
        po.save()
        messages.warning(request, f"⚠️ ยกเลิกใบสั่งซื้อ {po.code} เรียบร้อยแล้ว")
    else:
        messages.error(request, "❌ คุณไม่มีสิทธิ์ยกเลิกเอกสารนี้")
    return redirect('solar_po_list')