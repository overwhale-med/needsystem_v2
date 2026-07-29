import os
import django
import random
from datetime import date

# ตั้งค่า Django Environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth.models import User
from hr.models import Department, Position, EmployeeType, Employee

# 🔐 รหัสผ่านกลางสำหรับทุกคน
COMMON_PASSWORD = "A_12345678"

def run_seed():
    print("🚀 เริ่มต้นจำลองข้อมูลพนักงานแบบ Full Option...")

    # 1. สร้างประเภทพนักงาน
    etype_perm, _ = EmployeeType.objects.get_or_create(name="พนักงานประจำ")
    etype_prob, _ = EmployeeType.objects.get_or_create(name="ทดลองงาน")

    # 2. กำหนดโครงสร้างองค์กร (แผนก -> ตำแหน่ง -> เงินเดือน -> Rank)
    # Format: "ชื่อแผนก": [ ("ชื่อตำแหน่ง", เงินเดือน, Business Rank, จำนวนคนที่จะสร้าง) ]
    org_structure = {
        "แผนกบริหาร (Executive)": [
            ("CEO (ประธานเจ้าหน้าที่บริหาร)", 200000, 'director', 1),
            ("Secretary (เลขาานุการ)", 45000, 'supervisor', 1)
        ],
        "แผนกบัญชี (Accounting)": [
            ("Accounting Manager (ผู้จัดการบัญชี)", 85000, 'manager', 1),
            ("Senior Accountant (สมุห์บัญชี)", 55000, 'supervisor', 1),
            ("Accounting Staff (พนักงานบัญชี)", 25000, 'member', 2)
        ],
        "แผนกบุคคล (HR)": [
            ("HR Manager (ผู้จัดการบุคคล)", 80000, 'manager', 1),
            ("Recruitment Officer (เจ้าหน้าที่สรรหา)", 30000, 'member', 1),
            ("HR Admin (ธุรการบุคคล)", 22000, 'member', 1)
        ],
        "แผนกการตลาด (Marketing)": [
            ("Marketing Director (ผอ.การตลาด)", 120000, 'director', 1),
            ("Content Creator (คอนเทนต์)", 35000, 'member', 1),
            ("Ads Specialist (ยิงแอด)", 40000, 'member', 1)
        ],
        "แผนกขายสินค้า (Sales)": [
            ("Sales Director (ผอ.ฝ่ายขาย)", 120000, 'director', 1),
            ("Sales Manager (ผู้จัดการทีมขาย)", 70000, 'manager', 1),
            ("Sales Team Lead (หัวหน้าทีมขาย)", 45000, 'supervisor', 2),
            ("Sales Representative (พนักงานขาย)", 20000, 'member', 5) # สร้างเยอะหน่อย
        ],
        "แผนกจัดซื้อ (Purchasing)": [
            ("Purchasing Manager (ผู้จัดการจัดซื้อ)", 75000, 'manager', 1),
            ("Purchasing Officer (เจ้าหน้าที่จัดซื้อ)", 28000, 'member', 2)
        ],
        "แผนกโรงงานผลิต (Manufacturing)": [
            ("Plant Manager (ผู้จัดการโรงงาน)", 100000, 'manager', 1),
            ("Production Supervisor (หัวหน้าไลน์ผลิต)", 45000, 'supervisor', 2),
            ("Machine Operator (พนักงานคุมเครื่อง)", 18000, 'member', 4),
            ("QC Staff (ตรวจสอบคุณภาพ)", 20000, 'member', 2)
        ],
        "แผนกคลังสินค้า (Warehouse)": [
            ("Warehouse Manager (ผู้จัดการคลัง)", 65000, 'manager', 1),
            ("Stock Controller (เจ้าหน้าที่สต็อก)", 25000, 'member', 2),
            ("General Staff (พนักงานทั่วไป)", 15000, 'member', 2)
        ],
        "แผนกปฏิบัติการ (Operations)": [
            ("COO (ประธานฝ่ายปฏิบัติการ)", 150000, 'director', 1),
            ("Operations Manager (ผู้จัดการปฏิบัติการ)", 80000, 'manager', 1),
            ("Admin Staff (ธุรการทั่วไป)", 20000, 'member', 2)
        ]
    }

    # ตัวแปรเก็บ Object เพื่อใช้ผูกสายงาน
    dept_objs = {}
    pos_objs = {}
    employees_by_dept = {} # เก็บพนักงานแยกตามแผนกเพื่อหาหัวหน้า
    ceo_obj = None

    # --- PHASE 1: สร้างแผนกและตำแหน่ง ---
    print("   ... สร้างโครงสร้างแผนกและตำแหน่ง")
    for dept_name, positions in org_structure.items():
        d, _ = Department.objects.get_or_create(name=dept_name)
        dept_objs[dept_name] = d
        employees_by_dept[dept_name] = [] # เตรียม List ว่าง
        
        for pos_data in positions:
            title = pos_data[0]
            p, _ = Position.objects.get_or_create(title=title, department=d)
            pos_objs[title] = p

    # --- PHASE 2: จ้างพนักงาน (Create Employees) ---
    print("   ... เริ่มจ้างพนักงานและกำหนด User/Password")
    
    # รายชื่อคนไทยสุ่มๆ
    FIRST_NAMES = ["สมชาย", "สมหญิง", "วิชัย", "มานี", "มานะ", "วีระ", "ปิติ", "ชูใจ", "ดวงใจ", "อำนาจ", "สุดา", "กานดา", "นพดล", "รัตนา", "ประเสริฐ", "วันเพ็ญ", "สุชาติ", "พรทิพย์", "เอกชัย", "จินตนา", "ธนพล", "กมลชนก", "วรเวช", "พิมพ์ชนก", "ณเดชน์", "อุรัสยา", "ปริญ", "ราณี", "จิรายุ", "พัชราภา", "อารยา", "ธีรเดช", "แอน", "เคน", "เจนี่"]
    LAST_NAMES = ["ใจดี", "รักงาน", "เก่งกาจ", "มีตา", "อดทน", "กล้าหาญ", "พอใจ", "สีฟ้า", "สดใส", "ครองเมือง", "สวยงาม", "น่ารัก", "ดวงดี", "วงค์สวัสดิ์", "เลิศล้ำ", "จันทร์เจ้า", "แคล้วคลาด", "โรจนัย", "ศรีวิชัย", "สุขใจ", "รวยทรัพย์", "โกมล", "ดานุวงศ์", "ลือวิเศษไพบูลย์", "คูกิมิยะ", "เสปอร์บันด์", "สุภารัตน์", "แคมเปน", "ตั้งศรีสุข", "ไชยเชื้อ", "เอ ฮาร์เก็ต", "วงศ์พัวพันธ์", "ทองประสม", "เทียนโพธิ์สุวรรณ"]

    emp_counter = 1

    # วนลูปสร้างตามโครงสร้าง
    for dept_name, positions in org_structure.items():
        current_dept = dept_objs[dept_name]
        
        for pos_title, salary, rank, count in positions:
            current_pos = pos_objs[pos_title]
            
            for i in range(count):
                # สุ่มชื่อ
                fname = random.choice(FIRST_NAMES)
                lname = random.choice(LAST_NAMES)
                gender = random.choice(['M', 'F'])
                
                # สร้าง Username (เช่น acc01, sales05)
                # แปลงชื่อแผนกเป็นรหัสย่อภาษาอังกฤษ
                dept_code = {
                    "แผนกบริหาร (Executive)": "exec",
                    "แผนกบัญชี (Accounting)": "acc",
                    "แผนกบุคคล (HR)": "hr",
                    "แผนกการตลาด (Marketing)": "mkt",
                    "แผนกขายสินค้า (Sales)": "sale",
                    "แผนกจัดซื้อ (Purchasing)": "pur",
                    "แผนกโรงงานผลิต (Manufacturing)": "mfg",
                    "แผนกคลังสินค้า (Warehouse)": "wh",
                    "แผนกปฏิบัติการ (Operations)": "ops"
                }.get(dept_name, "emp")
                
                username = f"{dept_code}{emp_counter:03d}"
                email = f"{username}@company.com"
                
                # สร้าง User
                user, _ = User.objects.get_or_create(username=username)
                user.set_password(COMMON_PASSWORD) # 🔐 รหัสผ่าน A_12345678
                user.email = email
                user.save()

                # สร้าง Employee
                emp_id = f"EMP-{emp_counter:04d}"
                emp = Employee.objects.create(
                    user=user,
                    emp_id=emp_id,
                    prefix="คุณ",
                    first_name=fname,
                    last_name=lname,
                    nickname=fname[:2],
                    gender=gender,
                    department=current_dept,
                    position=current_pos,
                    emp_type=etype_perm,
                    salary=salary,
                    business_rank=rank,
                    commission_rate=5.0 if dept_code == "sale" else 0.0, # ให้ค่าคอมเฉพาะฝ่ายขาย
                    start_date=date(2024, 1, 1),
                    status='permanent'
                )
                
                # เก็บเข้า List เพื่อเอาไปผูกสายงานทีหลัง
                employees_by_dept[dept_name].append(emp)
                
                # ถ้าเป็น CEO (คนแรกของแผนกบริหาร) ให้เก็บไว้เป็น Root
                if pos_title == "CEO (ประธานเจ้าหน้าที่บริหาร)":
                    ceo_obj = emp
                
                print(f"      + {username} ({fname}) - {pos_title}")
                emp_counter += 1

    # --- PHASE 3: ผูกสายบังคับบัญชา (Wiring Hierarchy) ---
    print("   ... กำลังเชื่อมโยงสายบังคับบัญชา (Network Tree)")
    
    for dept_name, employees in employees_by_dept.items():
        # หาหัวหน้าสูงสุดของแผนก (คนที่มีเงินเดือนเยอะสุด หรือ rank สูงสุด)
        # เรียงพนักงานในแผนกตาม Rank (Director > Manager > Supervisor > Member)
        
        # แยกกลุ่มในแผนก
        directors = [e for e in employees if e.business_rank == 'director']
        managers = [e for e in employees if e.business_rank == 'manager']
        supervisors = [e for e in employees if e.business_rank == 'supervisor']
        members = [e for e in employees if e.business_rank == 'member']
        
        dept_head = None
        if directors: dept_head = directors[0]
        elif managers: dept_head = managers[0]
        
        # 1. หัวหน้าแผนก (Director/Manager) -> ขึ้นตรงกับ CEO (ยกเว้น CEO เอง)
        if dept_head and dept_head != ceo_obj:
            dept_head.introducer = ceo_obj
            dept_head.save()
            
        # 2. Manager (ถ้ามี Director คุม) -> ขึ้นตรงกับ Director
        if directors and managers:
            for m in managers:
                m.introducer = directors[0]
                m.save()
                
        # 3. Supervisor -> ขึ้นตรงกับ Manager (หรือ Director ถ้าไม่มี Manager)
        boss_for_sup = managers[0] if managers else (directors[0] if directors else ceo_obj)
        for s in supervisors:
            s.introducer = boss_for_sup
            s.save()
            
        # 4. Member -> ขึ้นตรงกับ Supervisor (กระจายๆ กันไป) หรือ Manager
        boss_list_for_member = supervisors if supervisors else [boss_for_sup]
        for m in members:
            # สุ่มหัวหน้าจากกลุ่ม Supervisor
            my_boss = random.choice(boss_list_for_member)
            m.introducer = my_boss
            m.save()

    print("🎉 เสร็จสมบูรณ์! สร้างพนักงานทั้งหมดเรียบร้อยแล้ว")
    print(f"👉 รหัสผ่านสำหรับทุกคนคือ: {COMMON_PASSWORD}")

if __name__ == '__main__':
    run_seed()