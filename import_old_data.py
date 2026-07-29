import os
import django
import sqlite3

# ตั้งค่า Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from hr.models import Employee, Position, Department

# เชื่อมต่อฐานข้อมูลเก่า
OLD_DB_PATH = '../django-hr-system/db.sqlite3'

def run_import():
    if not os.path.exists(OLD_DB_PATH):
        print(f"❌ ไม่พบไฟล์ฐานข้อมูลเก่าที่: {OLD_DB_PATH}")
        return

    print("🚀 เริ่มเชื่อมต่อฐานข้อมูลเก่า (V3)...")
    conn = sqlite3.connect(OLD_DB_PATH)
    cursor = conn.cursor()

    # ดึงรายชื่อตารางมาเช็คอีกรอบ
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [row[0] for row in cursor.fetchall()]

    # --- ย้ายพนักงาน (Employees) ---
    if 'employees_employee' in tables:
        print("...กำลังย้ายพนักงาน (ดึงเฉพาะ ชื่อ-นามสกุล)...")
        try:
            # สร้างตำแหน่ง Default
            dept, _ = Department.objects.get_or_create(name="ฝ่ายทั่วไป")
            pos, _ = Position.objects.get_or_create(name="พนักงาน", department=dept)

            # 👉 แก้ไข: ดึงแค่ first_name, last_name (ตัด phone, nickname ออกหมดเพื่อกัน Error)
            cursor.execute("SELECT first_name, last_name FROM employees_employee")
            
            count = 0
            for row in cursor.fetchall():
                emp_count = Employee.objects.count() + 1
                Employee.objects.get_or_create(
                    first_name=row[0],
                    defaults={
                        'last_name': row[1] or '', # ถ้านามสกุลไม่มี ให้ว่างไว้
                        'nickname': '',
                        'phone': '', # เบอร์โทรเว้นว่างไว้ก่อน
                        'employee_id': f"EMP-{emp_count:03d}",
                        'position': pos,
                        'is_active': True
                    }
                )
                count += 1
            print(f"✅ ย้ายพนักงานสำเร็จ: {count} คน")
        except Exception as e:
            print(f"❌ Error: {e}")
    else:
        print("⚠️ ไม่พบตาราง employees_employee")

    print("🎉 เสร็จสิ้นการทำงาน!")

if __name__ == '__main__':
    run_import()