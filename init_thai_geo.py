import os
import django

# ✅ แก้ไขตรงนี้: เปลี่ยนเป็น config.settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from master_data.models import Province, Amphure, Tambon

# ข้อมูลตัวอย่าง (ภาคตะวันออก + กทม)
data = {
    "กรุงเทพมหานคร": {"เขตพระนคร": "10200", "เขตดุสิต": "10300", "เขตปทุมวัน": "10330", "เขตบางรัก": "10500"},
    "ชลบุรี": {"เมืองชลบุรี": "20000", "ศรีราชา": "20110", "บางละมุง": "20150", "สัตหีบ": "20180"},
    "ระยอง": {"เมืองระยอง": "21000", "บ้านฉาง": "21130", "ปลวกแดง": "21140"},
    "ฉะเชิงเทรา": {"เมืองฉะเชิงเทรา": "24000", "บางปะกง": "24130"},
}

print("Start importing geography data...")

for prov_name, districts in data.items():
    p, _ = Province.objects.get_or_create(name_th=prov_name, name_en=prov_name)
    print(f"Processing: {prov_name}")
    
    for dist_name, zipcode in districts.items():
        a, _ = Amphure.objects.get_or_create(name_th=dist_name, province=p)
        Tambon.objects.get_or_create(name_th=f"ต.{dist_name}", amphure=a, zip_code=zipcode)

print("✅ Import Finished! พร้อมใช้งานแล้ว")