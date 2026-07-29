import os
import django
import random
from datetime import date, timedelta, time

# ตั้งค่า Django Environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from hr.models import Employee, Attendance

def generate_random_time(start_hour, start_min, end_hour, end_min):
    """
    ฟังก์ชันสุ่มเวลาแบบใหม่ (คำนวณจากนาทีรวม เพื่อแก้ปัญหาข้ามชั่วโมง)
    """
    # แปลงเวลาเริ่มต้นและสิ้นสุดเป็น "นาทีนับจากเที่ยงคืน"
    start_total_minutes = (start_hour * 60) + start_min
    end_total_minutes = (end_hour * 60) + end_min
    
    # สุ่มนาทีในช่วงนั้น
    random_minutes = random.randint(start_total_minutes, end_total_minutes)
    
    # แปลงกลับเป็น ชั่วโมง:นาที
    hour = random_minutes // 60
    minute = random_minutes % 60
    
    return time(hour, minute, 0)

def run_seed_attendance():
    print("⏳ กำลังจำลองข้อมูลเวลาเข้า-ออกงาน ย้อนหลัง 60 วัน (ฉบับแก้ไข)...")
    
    employees = Employee.objects.all()
    if not employees.exists():
        print("❌ ไม่พบข้อมูลพนักงาน! กรุณารัน seed_data.py ก่อนนะครับ")
        return

    # วันนี้
    today = date.today()
    # ย้อนหลัง 60 วัน
    start_date = today - timedelta(days=60)
    
    total_created = 0
    
    # วนลูปตั้งแต่วันที่เริ่ม จนถึงเมื่อวาน
    current_date = start_date
    while current_date < today:
        
        # ข้ามวันเสาร์ (5) และอาทิตย์ (6)
        if current_date.weekday() < 5: 
            # print(f"   📅 กำลังประมวลผลวันที่: {current_date.strftime('%d/%m/%Y')}")
            
            for emp in employees:
                # สุ่มเหตุการณ์
                chance = random.random() * 100
                
                # 1. ขาดงาน / ลา (5%)
                if chance < 5:
                    continue
                
                # 2. มาสาย (10%) -> เข้าช่วง 08:31 - 09:59
                elif chance < 15:
                    time_in = generate_random_time(8, 31, 9, 59)
                    note = "รถติด / ตื่นสาย"
                
                # 3. มาปกติ (85%) -> เข้าช่วง 07:30 - 08:25
                else:
                    time_in = generate_random_time(7, 30, 8, 25)
                    note = ""

                # เวลาออกงาน (สุ่มระหว่าง 17:30 - 19:30)
                time_out = generate_random_time(17, 30, 19, 30)
                
                # สร้างข้อมูลลง Database
                Attendance.objects.get_or_create(
                    employee=emp,
                    date=current_date,
                    defaults={
                        'time_in': time_in,
                        'time_out': time_out,
                        'note': note
                    }
                )
                total_created += 1
        
        current_date += timedelta(days=1)

    print("-" * 50)
    print(f"🎉 สำเร็จ! สร้างบันทึกเวลาทำงานไปทั้งหมด {total_created} รายการ")
    print("👉 ลองไปดูที่หน้า Dashboard ของพนักงาน หรือหน้า Admin ได้เลยครับ")

if __name__ == '__main__':
    run_seed_attendance()