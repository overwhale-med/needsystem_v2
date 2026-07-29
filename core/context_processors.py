from master_data.models import CompanyInfo

def company_context(request):
    """
    ฟังก์ชันนี้จะทำงานอัตโนมัติทุกครั้งที่เปิดหน้าเว็บ
    โดยจะไปดึงข้อมูลบริษัท (CompanyInfo) จาก Master Data
    แล้วส่งไปให้หน้าจอ HTML ในชื่อตัวแปร {{ company_info }}
    """
    # ดึงข้อมูลแถวแรกสุดในตาราง (ปกติเราจะมีแค่บริษัทเดียว)
    info = CompanyInfo.objects.first()
    
    return {'company_info': info}