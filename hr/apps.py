from django.apps import AppConfig
import os

class HrConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "hr"
    # 🌟 เพิ่มบรรทัดนี้เพื่อชี้เป้าโฟลเดอร์ที่ถูกต้องให้ Django หายสับสน 🌟
    path = os.path.dirname(os.path.abspath(__file__))