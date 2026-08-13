import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from hr.models import Employee, Department, Position
from django.contrib.auth.models import Group

def assign_roles():
    print("🚀 กำลังรื้อระบบโครงสร้าง และจัดลำดับสายบังคับบัญชา (Hierarchy) ใหม่...")

    def get_dp(dept_name, pos_title):
        d = Department.objects.filter(name__icontains=dept_name).first()
        p = Position.objects.filter(title__icontains=pos_title).first()
        return d, p

    def update_emp(emp_id, role_group, dept_name, pos_title, rank, upline_id=None):
        emp = Employee.objects.filter(emp_id=emp_id).first()
        if not emp: return

        dept, pos = get_dp(dept_name, pos_title)
        if dept: emp.department = dept
        if pos: emp.position = pos

        # 🌟 กำหนดระดับธุรกิจ (เพื่อสีของกล่องแผนผังองค์กร)
        emp.business_rank = rank

        # 🌟 กำหนดสายบังคับบัญชา (หัวหน้างาน) เพื่อสร้างแผนผังต้นไม้
        if upline_id:
            upline = Employee.objects.filter(emp_id=upline_id).first()
            emp.introducer = upline
        else:
            emp.introducer = None

        emp.save()

        # 🌟 กำหนดสิทธิ์การเข้าถึงเมนู
        if emp.user:
            group, _ = Group.objects.get_or_create(name=role_group)
            emp.user.groups.clear()
            emp.user.groups.add(group)

    # ==========================================
    # 🏢 1. ฝ่ายบริหารจัดการ (Executive)
    # ==========================================
    update_emp('EMP-0001', 'Executive', 'บริหารจัดการ', 'Managing Director', 'director', None) # บอสใหญ่ (ไม่มีหัวหน้า)
    update_emp('EMP-0002', 'Executive', 'บริหารจัดการ', 'General Manager', 'manager', 'EMP-0001') # GM ขึ้นตรงกับ MD

    # ==========================================
    # 💰 2. ฝ่ายบัญชีและการเงิน (Accounting)
    # ==========================================
    update_emp('EMP-0003', 'Accounting', 'บัญชีและการเงิน', 'Accounting Manager', 'manager', 'EMP-0002')
    for e in ['EMP-0004', 'EMP-0005', 'EMP-0006']:
        update_emp(e, 'Accounting', 'บัญชีและการเงิน', 'Finance Officer', 'member', 'EMP-0003')

    # ==========================================
    # 👥 3. ฝ่ายบุคคลและธุรการ (HR)
    # ==========================================
    update_emp('EMP-0007', 'HR', 'บุคคลและธุรการ', 'HR Manager', 'manager', 'EMP-0002')
    for e in ['EMP-0008', 'EMP-0009']:
        update_emp(e, 'HR', 'บุคคลและธุรการ', 'System Admin', 'member', 'EMP-0007')

    # ==========================================
    # 📈 4. ฝ่ายขายและการตลาด (Sales & Marketing)
    # ==========================================
    update_emp('EMP-0013', 'Sales', 'ฝ่ายขายและการตลาด', 'Sales Manager', 'manager', 'EMP-0002') # ผู้จัดการฝ่ายขาย

    # 4.1 ทีมการตลาด / CRM (EMP-0010 ถึง EMP-0012 ที่ว่างอยู่)
    update_emp('EMP-0010', 'Marketing', 'ทีมการตลาด', 'CRM / Marketing Admin', 'supervisor', 'EMP-0013')
    for e in ['EMP-0011', 'EMP-0012']:
        update_emp(e, 'Marketing', 'ทีมการตลาด', 'CRM / Marketing Admin', 'member', 'EMP-0010')

    # 4.2 ทีมขายบ้านน็อคดาวน์
    update_emp('EMP-0014', 'Sales', 'ทีมขายบ้านน็อคดาวน์', 'Sales Supervisor', 'supervisor', 'EMP-0013')
    for e in ['EMP-0015', 'EMP-0016']:
        update_emp(e, 'Sales', 'ทีมขายบ้านน็อคดาวน์', 'Sales Executive', 'member', 'EMP-0014')

    # 4.3 ทีมขายโซล่าเซลล์ ☀️
    update_emp('EMP-0017', 'Sales', 'ทีมขายโซล่าเซลล์', 'Sales Supervisor', 'supervisor', 'EMP-0013')
    for e in ['EMP-0018', 'EMP-0019', 'EMP-0020', 'EMP-0021']:
        update_emp(e, 'Sales', 'ทีมขายโซล่าเซลล์', 'Sales Executive', 'member', 'EMP-0017')

    # ==========================================
    # 🛒 5. ฝ่ายจัดซื้อและคลังสินค้า (Purchasing & Inventory)
    # ==========================================
    update_emp('EMP-0022', 'Purchasing', 'จัดซื้อและคลังสินค้า', 'Purchasing Manager', 'manager', 'EMP-0002')
    for e in ['EMP-0023', 'EMP-0024']:
        update_emp(e, 'Purchasing', 'จัดซื้อและคลังสินค้า', 'Purchasing Officer', 'member', 'EMP-0022')

    update_emp('EMP-0034', 'Inventory', 'จัดซื้อและคลังสินค้า', 'Warehouse Staff', 'supervisor', 'EMP-0022') # หัวหน้าคลัง
    for e in ['EMP-0035', 'EMP-0036', 'EMP-0037', 'EMP-0038']:
        update_emp(e, 'Inventory', 'จัดซื้อและคลังสินค้า', 'Warehouse Staff', 'member', 'EMP-0034')

    # ==========================================
    # 🏭 6. ฝ่ายปฏิบัติการและผลิต (Production Center)
    # ==========================================
    update_emp('EMP-0025', 'Production', 'ศูนย์ปฏิบัติการ', 'Center Manager', 'manager', 'EMP-0002')
    update_emp('EMP-0028', 'Production', 'ศูนย์ปฏิบัติการ', 'Production Head', 'supervisor', 'EMP-0025')
    update_emp('EMP-0029', 'Production', 'ศูนย์ปฏิบัติการ', 'Production Head', 'supervisor', 'EMP-0025')

    update_emp('EMP-0032', 'QC Team', 'ศูนย์ปฏิบัติการ', 'QC Inspector', 'supervisor', 'EMP-0025') # หัวหน้า QC
    update_emp('EMP-0033', 'QC Team', 'ศูนย์ปฏิบัติการ', 'QC Inspector', 'member', 'EMP-0032')

    # ==========================================
    # 📐 7. ฝ่ายวางแผนและเขียนแบบ (Planner & Blueprint)
    # ==========================================
    update_emp('EMP-0026', 'Planner Team', 'วางแผนและเขียนแบบ', 'Production Planner', 'supervisor', 'EMP-0002')
    update_emp('EMP-0027', 'Planner Team', 'วางแผนและเขียนแบบ', 'Production Planner', 'member', 'EMP-0026')

    update_emp('EMP-0030', 'Blueprint Team', 'วางแผนและเขียนแบบ', 'Draftsman / Architect', 'supervisor', 'EMP-0026')
    update_emp('EMP-0031', 'Blueprint Team', 'วางแผนและเขียนแบบ', 'Draftsman / Architect', 'member', 'EMP-0030')

    # ==========================================
    # 🚚 8. ฝ่ายจัดส่ง (Logistics)
    # ==========================================
    update_emp('EMP-0039', 'Logistics Team', 'จัดส่งสินค้า', 'Logistics Coordinator', 'supervisor', 'EMP-0002')

    # 🌟 แก้ไขบรรทัดนี้ โดยเพิ่ม 'EMP-0042' เข้าไปครับ 🌟
    for e in ['EMP-0040', 'EMP-0041', 'EMP-0042']:
        update_emp(e, 'Logistics Team', 'จัดส่งสินค้า', 'Driver / Transporter', 'member', 'EMP-0039')

    print("✅ จัดโครงสร้างการบริหาร (Hierarchy) และเชื่อมโยงข้อมูลสำเร็จแล้ว!")

if __name__ == '__main__':
    assign_roles()