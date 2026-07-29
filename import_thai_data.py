import os
import json
import ssl
import urllib.request
import django

# ตั้งค่า Django Environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from master_data.models import Province, Amphure, Tambon

# ✅ ลิงก์ใหม่ (จาก Repo ของ Earthchie ที่เสถียรที่สุดในไทย)
DATA_URL = "https://raw.githubusercontent.com/earthchie/jquery.Thailand.js/master/jquery.Thailand.js/database/raw_database/raw_database.json"

def import_data():
    print("🧹 1. กำลังล้างข้อมูลเก่าทิ้ง (เพื่อให้เริ่มใหม่แบบสะอาด)...")
    Tambon.objects.all().delete()
    Amphure.objects.all().delete()
    Province.objects.all().delete()
    print("   ✨ ล้างข้อมูลเสร็จแล้ว!")

    print("\n📥 2. กำลังดาวน์โหลดข้อมูลชุดใหม่ (จาก Earthchie)...")
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    
    try:
        with urllib.request.urlopen(DATA_URL, context=ctx) as url:
            data = json.loads(url.read().decode())
    except Exception as e:
        print(f"❌ ดาวน์โหลดพลาด: {e}")
        return

    print(f"   ✅ โหลดเสร็จ! พบข้อมูลทั้งหมด {len(data)} รายการ")
    print("\n🚀 3. เริ่มนำเข้าฐานข้อมูล (รอประมาณ 1-2 นาที)...")
    
    # ตัวช่วยจำ (Cache) เพื่อให้ทำงานเร็วขึ้น
    prov_cache = {}
    amp_cache = {}
    
    count = 0
    for item in data:
        # 1. จังหวัด
        p_name = item['province']
        if p_name not in prov_cache:
            p_obj, _ = Province.objects.get_or_create(name_th=p_name)
            prov_cache[p_name] = p_obj
        else:
            p_obj = prov_cache[p_name]

        # 2. อำเภอ
        a_name = item['amphoe']
        # ใช้ key ผสมจังหวัด กันอำเภอชื่อซ้ำ (เช่น อ.เมือง มีทุกจังหวัด)
        a_key = f"{p_name}_{a_name}"
        
        if a_key not in amp_cache:
            a_obj, _ = Amphure.objects.get_or_create(name_th=a_name, province=p_obj)
            amp_cache[a_key] = a_obj
        else:
            a_obj = amp_cache[a_key]

        # 3. ตำบล
        t_name = item['district']
        z_code = str(item.get('zipcode', ''))
        
        Tambon.objects.get_or_create(
            name_th=t_name, 
            amphure=a_obj, 
            defaults={'zip_code': z_code}
        )
        
        count += 1
        if count % 2000 == 0:
            print(f"   ...บันทึกแล้ว {count} รายการ")

    print(f"\n🎉 เสร็จสมบูรณ์! ข้อมูลกลับมาครบแล้วครับ")

if __name__ == "__main__":
    import_data()