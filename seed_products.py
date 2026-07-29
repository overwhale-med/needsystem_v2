import os
import django
import random

# ตั้งค่า Django Environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from inventory.models import Category, Product
from master_data.models import Supplier, Customer

def run_seed_products():
    print("🛒 กำลังจำลองข้อมูลสินค้าและลูกค้า...")

    # 1. สร้างหมวดหมู่ (Categories)
    categories = ['อาหารเสริม (Supplements)', 'เครื่องสำอาง (Cosmetics)', 'กาแฟและเครื่องดื่ม (Coffee & Drinks)', 'ของใช้ส่วนตัว (Personal Care)']
    cat_objs = []
    for cat_name in categories:
        c, created = Category.objects.get_or_create(name=cat_name)
        cat_objs.append(c)
    print(f"   ✅ สร้างหมวดหมู่ครบ {len(cat_objs)} หมวด")

    # 2. สร้างซัพพลายเออร์ (Suppliers)
    suppliers = ['Factory A (Thailand)', 'Korea Lab Import', 'Nature Extract Co.,Ltd.']
    sup_objs = []
    for i, sup_name in enumerate(suppliers):
        s, created = Supplier.objects.get_or_create(
            code=f"SUP-{i+1:03d}",
            defaults={'name': sup_name, 'phone': '02-xxx-xxxx'}
        )
        sup_objs.append(s)
    print(f"   ✅ สร้างซัพพลายเออร์ครบ {len(sup_objs)} ราย")

    # 3. สร้างลูกค้า (Customers)
    customers_data = [
        ("CUS-001", "ลูกค้าทั่วไป (Walk-in)", "099-999-9999"),
        ("CUS-002", "คุณสมชาย ใจดี (VIP)", "081-234-5678"),
        ("CUS-003", "ร้านขายยาชุมชน (Wholesale)", "02-555-5555")
    ]
    for code, name, phone in customers_data:
        Customer.objects.get_or_create(
            code=code,
            defaults={'name': name, 'phone': phone, 'points': 0}
        )
    print("   ✅ สร้างฐานข้อมูลลูกค้าเรียบร้อย")

    # 4. สร้างสินค้า (Products)
    # รายชื่อสินค้าสมมติ (แนวธุรกิจเครือข่าย/สุขภาพ)
    product_names = [
        ("NEED Collagen Tri-Peptide", 0), # 0 = อาหารเสริม
        ("NEED Fiber Detox", 0),
        ("Vitamin C 1000mg", 0),
        ("Multi-Vitamin Complex", 0),
        ("Gluta Pure White", 0),
        ("Coffee Mix 3-in-1 (สูตรคุมหิว)", 2), # 2 = กาแฟ
        ("Cocoa Burn (โกโก้ลดน้ำหนัก)", 2),
        ("Matcha Greentea Latte", 2),
        ("Anti-Aging Serum", 1), # 1 = เครื่องสำอาง
        ("Whitening Cream Day/Night", 1),
        ("Sunscreen SPF50 PA+++", 1),
        ("Facial Foam Cleanser", 1),
        ("Body Lotion Perfume", 3), # 3 = ของใช้
        ("Herbal Toothpaste", 3),
        ("Shampoo Organic", 3)
    ]

    count = 0
    for i, (prod_name, cat_idx) in enumerate(product_names):
        code = f"P-{i+1:04d}"
        
        # สุ่มราคา
        cost = random.randint(100, 500) # ทุน
        price = cost * random.uniform(1.5, 3.0) # ราคาขาย (กำไร 50-200%)
        price = round(price, -1) # ปัดเศษให้ลงท้ายด้วย 0 สวยๆ

        Product.objects.get_or_create(
            code=code,
            defaults={
                'name': prod_name,
                'category': cat_objs[cat_idx],
                'supplier': random.choice(sup_objs),
                'cost_price': cost,
                'sell_price': price,
                'stock_qty': random.randint(50, 500), # สต็อกแน่นๆ
                'min_level': 20,
                'is_active': True
            }
        )
        count += 1
        print(f"      + สินค้า: {prod_name} (สต็อก: {Product.objects.get(code=code).stock_qty})")

    print("-" * 50)
    print(f"🎉 เสร็จสมบูรณ์! พร้อมขายของแล้วครับ (สินค้าทั้งหมด: {count} รายการ)")

if __name__ == '__main__':
    run_seed_products()