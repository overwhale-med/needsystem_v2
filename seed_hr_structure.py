import os
import django

# ตั้งค่าให้สคริปต์รู้จักกับโปรเจกต์ Django ของเรา
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from hr.models import Department, Position

def seed_hr_data():
    print("🚀 กำลังล้างข้อมูลแผนกและตำแหน่งเก่าเพื่อเตรียมระบบใหม่...")
    # ลบข้อมูลเก่าเพื่อป้องกันการซ้ำซ้อน
    Position.objects.all().delete()
    Department.objects.all().delete()

    # 🏢 กำหนดโครงสร้างแผนกหลักและตำแหน่งงาน
    departments_data = {
        "บริหารจัดการ": [
            "Managing Director (MD)", 
            "General Manager (GM)"
        ],
        "ฝ่ายขายและการตลาด": [
            "Sales Manager", 
            "Sales Supervisor", 
            "Sales Executive", 
            "CRM / Marketing Admin"
        ],
        "วางแผนและเขียนแบบ": [
            "Production Planner", 
            "Draftsman / Architect"
        ],
        "ศูนย์ปฏิบัติการ": [
            "Center Manager", 
            "Production Head", 
            "QC Inspector"
        ],
        "จัดซื้อและคลังสินค้า": [
            "Purchasing Manager", 
            "Purchasing Officer", 
            "Warehouse Staff"
        ],
        "จัดส่งสินค้า": [
            "Logistics Coordinator", 
            "Driver / Transporter"
        ],
        "บัญชีและการเงิน": [
            "Accounting Manager", 
            "Finance Officer"
        ],
        "บุคคลและธุรการ": [
            "HR Manager", 
            "System Admin"
        ]
    }

    print("🏗️ กำลังสร้างโครงสร้างองค์กรหลักและตำแหน่งงาน...")
    for dept_name, positions in departments_data.items():
        # สร้างแผนกหลัก (ไม่มี parent)
        dept, created = Department.objects.get_or_create(name=dept_name, parent=None)
        
        # สร้างตำแหน่งงานภายใต้แผนกหลัก
        for pos_title in positions:
            Position.objects.get_or_create(title=pos_title, department=dept)
            
    print("☀️ กำลังสร้างแผนกย่อย (Sub-departments) สำหรับงานขายเฉพาะทาง...")
    
    # ดึงแผนกหลัก "ฝ่ายขายและการตลาด" ขึ้นมา
    sales_main = Department.objects.get(name="ฝ่ายขายและการตลาด")
    
    # สร้างแผนกย่อย ภายใต้แผนกฝ่ายขายและการตลาด
    Department.objects.get_or_create(name="ทีมขายบ้านน็อคดาวน์", parent=sales_main)
    Department.objects.get_or_create(name="ทีมขายโซล่าเซลล์", parent=sales_main)
    Department.objects.get_or_create(name="ทีมการตลาด / CRM", parent=sales_main)

    print("✅ นำเข้าข้อมูลโครงสร้างแผนกและตำแหน่งงานสำเร็จเรียบร้อยแล้ว!")
    print("🎉 ตอนนี้ระบบ HR ของคุณพร้อมสำหรับใช้งานกับระบบ Premium ERP แล้วครับ")

if __name__ == '__main__':
    seed_hr_data()