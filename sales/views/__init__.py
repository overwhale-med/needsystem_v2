# 🌟 ดึงฟังก์ชันเก่าจาก views_legacy มาใช้ทำงานไปก่อนระหว่างปรับปรุง
from sales.views_legacy import *

# 🌟 ฟังก์ชันใหม่ที่เราจะค่อยๆ ดึงมาเปิดใช้งาน
from .dashboards import *
from .quotations import *
from .invoices import *
from .commissions import *
from .crm import *