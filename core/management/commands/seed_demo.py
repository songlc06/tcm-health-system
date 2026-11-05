"""初始化演示数据：菜单、角色权限、演示用户、会员、服务、套餐、订单、预约与日志。

用法：
    python manage.py seed_demo            # 幂等初始化（已存在则跳过）
    python manage.py seed_demo --reset    # 清空业务数据后重建
"""
import datetime as dt
import random
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.contrib.auth.models import Group, Permission
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from core.timeutil import local_today

from accounts.models import Member, User
from appointments.models import Appointment, AppointmentAttachment, AppointmentHistory
from core.models import Menu, OperationLog
from orders.models import Order, OrderItem, OrderStatusHistory, Package, PackageItem
from services.models import HealthService, ServiceCategory

PASSWORD = "demo123456"

MENUS = [
    # code, name, url_name, perm_codename, icon, group, sort, role_scope
    ("member_center", "会员中心", "accounts:profile", "", "◉", "member", 1, "member"),
    ("member_list", "会员档案", "accounts:member_list", "accounts.view_member", "◇", "member", 2, ""),
    ("service_list", "养生服务", "services:list", "services.view_healthservice", "❖", "service", 1, ""),
    ("order_list", "套餐订单", "orders:list", "orders.view_order", "▤", "order", 1, ""),
    ("appointment_list", "服务预约", "appointments:list", "appointments.view_appointment", "◷", "appointment", 1, ""),
    ("report_search", "多条件查询", "reports:search", "core.query_report", "⌕", "report", 1, ""),
    ("report_statistics", "统计报表", "reports:statistics", "core.view_statistics", "▥", "report", 2, ""),
    ("report_logs", "操作日志", "reports:logs", "core.view_operationlog", "≡", "report", 3, ""),
    ("sys_users", "用户管理", "accounts:user_list", "auth.view_user", "⚙", "system", 1, ""),
    ("sys_roles", "角色权限", "accounts:role_list", "auth.view_group", "⚿", "system", 2, ""),
]

GROUP_PERMS = {
    "系统管理员": ["*"],
    "服务主管": [
        "services.*", "core.query_report", "core.view_statistics",
        "accounts.view_member", "orders.view_order", "appointments.view_appointment",
    ],
    "订单专员": [
        "orders.*", "accounts.view_member", "services.view_healthservice",
        "core.query_report", "appointments.view_appointment",
    ],
    "健康顾问": [
        "appointments.*", "services.view_healthservice", "orders.view_order",
        "accounts.view_member", "core.query_report",
    ],
    "报表专员": [
        "core.view_statistics", "core.export_report", "core.query_report", "core.view_operationlog",
        "orders.view_order", "orders.export_order", "appointments.view_appointment",
        "services.view_healthservice", "accounts.view_member",
    ],
    "会员": [],
}

USERS = [
    # username, role, display_name, phone
    ("admin", "admin", "张启明", "13800000001"),
    ("service", "service_manager", "李慧芳", "13800000002"),
    ("clerk", "order_clerk", "王婷", "13800000003"),
    ("therapist", "therapist", "陈志远", "13800000004"),
    ("therapist2", "therapist", "周敏", "13800000005"),
    ("reporter", "reporter", "赵鑫", "13800000006"),
    ("member01", "member", "宋青禾", "13900000001"),
]

CATEGORIES = [
    ("针灸推拿", "TUINA", "传统推拿与针灸，疏通经络、缓解疼痛"),
    ("艾灸理疗", "MOXA", "以艾温阳，适用于虚寒体质与亚健康调理"),
    ("中药调理", "HERB", "中药熏蒸、足浴、穴位贴敷等外治调理"),
    ("经络养生", "MERIDIAN", "经络疏通、刮痧拔罐与体质辨识"),
    ("小儿推拿", "PEDIATRIC", "儿童常见问题的绿色调理手法"),
]

SERVICES = [
    # code, name, category_idx, duration, price, member_price, summary, suitable, contra, hot
    ("SVC001", "经络推拿", 0, 60, 298, 268, "全身经络推拿，疏通气血、缓解疲劳", "久坐人群、肩颈腰背酸胀者", "皮肤破损、急性外伤期禁做", True),
    ("SVC002", "肩颈调理推拿", 0, 45, 258, 228, "针对颈肩劳损的局部推拿手法", "长期伏案、颈椎不适人群", "颈椎骨折、严重骨质疏松者慎用", True),
    ("SVC003", "温针灸", 0, 40, 218, 198, "针刺配合艾灸温通经络", "寒湿痹痛、关节冷痛者", "出血倾向、孕期腰骶部禁用", False),
    ("SVC004", "头部经络放松", 0, 40, 138, 128, "头部穴位按揉，改善睡眠与紧张性头痛", "失眠、用脑过度人群", "头皮破损、急性发热期不宜", False),
    ("SVC005", "艾灸温阳调理", 1, 60, 268, 238, "任脉督脉温和灸，温补阳气", "阳虚怕冷、经期腹痛者", "实热体质、皮肤过敏者慎用", True),
    ("SVC006", "督脉艾灸", 1, 50, 328, 298, "督脉铺灸，调理全身阳气", "体虚易感冒、慢性疲劳者", "高热、急性炎症期禁用", False),
    ("SVC007", "中药熏蒸", 2, 45, 228, 208, "中药蒸汽熏蒸，祛湿散寒", "湿气重、关节僵硬者", "高血压未控制、心功能不全者禁用", False),
    ("SVC008", "中药足浴", 2, 40, 98, 88, "足部药浴配合足底按摩", "手脚冰凉、睡眠不佳者", "糖尿病足、下肢静脉曲张者慎用", False),
    ("SVC009", "穴位埋线", 2, 45, 358, 328, "穴位埋线调理脾胃与体重管理", "单纯性肥胖、脾胃虚弱者", "瘢痕体质、孕期禁用", False),
    ("SVC010", "拔罐祛湿", 3, 30, 128, 118, "留罐与走罐结合，祛湿通络", "湿重、肌肉酸痛人群", "皮肤过敏、凝血功能障碍者禁用", True),
    ("SVC011", "刮痧排毒", 3, 40, 158, 148, "经络刮痧，改善循环", "肩背僵硬、易疲劳者", "皮肤病、孕期腹部禁用", False),
    ("SVC012", "体质辨识与调理方案", 3, 60, 198, 168, "中医体质辨识并出具调理建议", "所有亚健康人群", "无特殊禁忌", False),
    ("SVC013", "小儿推拿（脾胃）", 4, 30, 168, 148, "小儿脾胃调理推拿", "积食、食欲不振儿童", "皮肤破损、急性传染病期禁用", True),
    ("SVC014", "小儿推拿（助长）", 4, 30, 178, 158, "小儿助长保健推拿", "生长发育期儿童", "发热、急性感染期不宜", False),
]

PACKAGES = [
    # code, name, price, member_price, valid_days, desc, recommended, items[(service_code, times)]
    ("PKG001", "肩颈舒缓 10 次卡", 2380, 2180, 365, "针对伏案人群的肩颈综合调理，含推拿与经络疏通", True,
     [("SVC002", 6), ("SVC001", 4)]),
    ("PKG002", "艾灸温阳 12 次卡", 2880, 2680, 365, "阳虚体质温补套餐，艾灸为主、督脉为辅", True,
     [("SVC005", 8), ("SVC006", 4)]),
    ("PKG003", "祛湿排毒 8 次卡", 1080, 980, 180, "拔罐与刮痧组合，适合湿气重、易疲劳人群", False,
     [("SVC010", 4), ("SVC011", 4)]),
    ("PKG004", "产后调理 15 次卡", 4380, 3980, 365, "产后经络调理、艾灸温阳与中药熏蒸组合", False,
     [("SVC001", 6), ("SVC005", 5), ("SVC007", 4)]),
    ("PKG005", "小儿推拿月卡 12 次", 1680, 1580, 90, "儿童脾胃调理与助长保健，30 天有效", False,
     [("SVC013", 8), ("SVC014", 4)]),
]

MEMBERS = [
    # name, gender, birthday, phone, level, points, constitution, allergy, tags, notes
    ("宋青禾", "F", "1990-04-12", "13900000001", "gold", 1280, "气虚质", "青霉素", "肩颈不适,睡眠差", "长期伏案工作，颈肩僵硬，入睡困难。"),
    ("林嘉言", "M", "1985-09-03", "13900000002", "silver", 760, "痰湿质", "无", "体重管理,湿气重", "体形偏胖，易疲乏，晨起口黏。"),
    ("许静姝", "F", "1993-11-21", "13900000003", "diamond", 3260, "阳虚质", "海鲜", "怕冷,经期腹痛", "手脚常年冰凉，经期小腹冷痛。"),
    ("陈慕白", "M", "1978-02-17", "13900000004", "bronze", 180, "平和质", "无", "腰背酸痛", "久站工作，腰背酸胀。"),
    ("周聽雨", "F", "1996-07-08", "13900000005", "silver", 920, "气郁质", "花粉", "情绪紧张,头痛", "工作压力大，易紧张性头痛。"),
    ("吴柏舟", "M", "1988-12-30", "13900000006", "gold", 1540, "湿热质", "无", "易上火,口苦", "喜辛辣，易口苦咽干。"),
    ("郑云舒", "F", "1992-03-05", "13900000007", "bronze", 260, "血瘀质", "无", "痛经,面色暗", "经期腹痛，血块较多。"),
    ("何砚清", "M", "1975-06-19", "13900000008", "silver", 640, "气虚质", "磺胺", "易感冒,乏力", "体质偏虚，换季易感冒。"),
    ("苏婉如", "F", "1998-10-11", "13900000009", "bronze", 120, "平和质", "无", "产后调理", "产后半年，腰膝酸软。"),
    ("唐子墨", "M", "2018-05-22", "13900000010", "bronze", 80, "平和质", "无", "小儿积食", "食欲不佳，夜间磨牙。"),
    ("方曼卿", "F", "1983-08-14", "13900000011", "gold", 1870, "阳虚质", "无", "怕冷,睡眠差", "畏寒肢冷，睡眠浅易醒。"),
    ("罗清和", "M", "1991-01-27", "13900000012", "diamond", 4120, "平和质", "无", "健身,运动恢复", "健身爱好者，运动后肌肉紧张。"),
]


class Command(BaseCommand):
    help = "初始化菜单、角色权限、演示账号与模拟业务数据"

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="清空业务数据后重建")
        parser.add_argument("--password", default=PASSWORD, help="演示账号密码")

    @transaction.atomic
    def handle(self, *args, **options):
        random.seed(20261104)
        self.password = options["password"]

        if options["reset"]:
            self.stdout.write("清空已有业务数据 ...")
            AppointmentAttachment.objects.all().delete()
            AppointmentHistory.objects.all().delete()
            Appointment.objects.all().delete()
            OrderStatusHistory.objects.all().delete()
            OrderItem.objects.all().delete()
            Order.objects.all().delete()
            PackageItem.objects.all().delete()
            Package.objects.all().delete()
            HealthService.objects.all().delete()
            ServiceCategory.objects.all().delete()
            Member.objects.all().delete()
            OperationLog.objects.all().delete()
            User.objects.exclude(is_superuser=True).delete()
            Group.objects.all().delete()
            Menu.objects.all().delete()

        self.create_menus()
        self.create_groups()
        self.create_users()
        self.create_services()
        self.create_packages()
        self.create_members()
        self.create_orders()
        self.create_appointments()
        self.create_logs()

        self.stdout.write(self.style.SUCCESS("\n演示数据初始化完成："))
        self.stdout.write(
            f"  用户 {User.objects.count()} 个 / 会员 {Member.objects.count()} 位 / "
            f"服务 {HealthService.objects.count()} 项 / 套餐 {Package.objects.count()} 个 / "
            f"订单 {Order.objects.count()} 单 / 预约 {Appointment.objects.count()} 单 / "
            f"日志 {OperationLog.objects.count()} 条"
        )
        self.stdout.write(f"  演示密码：{self.password}（admin / service / clerk / therapist / reporter / member01）")

    # ------------------------------------------------------------------ 菜单
    def create_menus(self):
        for code, name, url_name, perm, icon, group, sort, scope in MENUS:
            Menu.objects.update_or_create(
                code=code,
                defaults={
                    "name": name, "url_name": url_name, "perm_codename": perm,
                    "icon": icon, "group": group, "sort_order": sort, "role_scope": scope,
                    "is_active": True,
                },
            )
        self.stdout.write(f"菜单 {Menu.objects.count()} 项")

    # ------------------------------------------------------------------ 角色
    def create_groups(self):
        for group_name, patterns in GROUP_PERMS.items():
            group, _ = Group.objects.get_or_create(name=group_name)
            perms = Permission.objects.none()
            for pattern in patterns:
                if pattern == "*":
                    perms = Permission.objects.all()
                    break
                app_label, codename = pattern.split(".")
                if codename == "*":
                    perms |= Permission.objects.filter(content_type__app_label=app_label)
                else:
                    perms |= Permission.objects.filter(
                        content_type__app_label=app_label, codename=codename)
            group.permissions.set(perms.distinct())
        self.stdout.write(f"角色 {Group.objects.count()} 个")

    # ------------------------------------------------------------------ 用户
    def create_users(self):
        for username, role, display_name, phone in USERS:
            user, created = User.objects.get_or_create(
                username=username,
                defaults={"role": role, "display_name": display_name, "phone": phone,
                          "is_staff": role != "member"},
            )
            if created:
                user.set_password(self.password)
                user.save()
            group = Group.objects.filter(name=User.ROLE_GROUP_MAP.get(role, "")).first()
            if group:
                user.groups.add(group)
        # 超级管理员
        admin = User.objects.get(username="admin")
        admin.is_superuser = True
        admin.is_staff = True
        admin.save()

    # ------------------------------------------------------------------ 服务
    def create_services(self):
        cats = {}
        for i, (name, code, desc) in enumerate(CATEGORIES):
            cat, _ = ServiceCategory.objects.update_or_create(
                code=code, defaults={"name": name, "description": desc, "sort_order": i, "is_active": True})
            cats[i] = cat

        creator = User.objects.filter(username="service").first()
        for idx, (code, name, cat_idx, duration, price, mprice, summary, suitable, contra, hot) in enumerate(SERVICES):
            HealthService.objects.update_or_create(
                code=code,
                defaults={
                    "name": name, "category": cats[cat_idx], "summary": summary,
                    "description": f"{summary}。服务流程：体质问询 → 手法调理 → 术后嘱托。"
                                   f"建议每周 1-2 次，连续调理效果更佳。",
                    "duration": duration, "price": Decimal(price), "member_price": Decimal(mprice),
                    "suitable_for": suitable, "contraindication": contra,
                    "status": "on", "is_hot": hot, "sort_order": idx,
                    "created_by": creator,
                },
            )
        self.stdout.write(f"服务 {HealthService.objects.count()} 项")

    def create_packages(self):
        for code, name, price, mprice, days, desc, rec, items in PACKAGES:
            package, _ = Package.objects.update_or_create(
                code=code,
                defaults={"name": name, "price": Decimal(price), "member_price": Decimal(mprice),
                          "valid_days": days, "description": desc, "status": "on",
                          "is_recommended": rec},
            )
            for service_code, times in items:
                service = HealthService.objects.get(code=service_code)
                PackageItem.objects.update_or_create(
                    package=package, service=service, defaults={"times": times})
        self.stdout.write(f"套餐 {Package.objects.count()} 个")

    # ------------------------------------------------------------------ 会员
    def create_members(self):
        creator = User.objects.filter(username="service").first()
        today = local_today()
        for i, (name, gender, birthday, phone, level, points, cons, allergy, tags, notes) in enumerate(MEMBERS):
            member, created = Member.objects.get_or_create(
                phone=phone,
                defaults={
                    "name": name, "gender": gender,
                    "birthday": dt.datetime.strptime(birthday, "%Y-%m-%d").date(),
                    "level": level, "points": points, "balance": Decimal("0.00"),
                    "constitution": cons, "allergy": allergy, "tags": tags,
                    "health_notes": notes, "join_date": today - timedelta(days=180 - i * 12),
                    "is_active": True, "created_by": creator,
                },
            )
            if i == 0:
                member.user = User.objects.filter(username="member01").first()
                member.save(update_fields=["user"])
        self.stdout.write(f"会员 {Member.objects.count()} 位")

    # ------------------------------------------------------------------ 订单
    def create_orders(self):
        members = list(Member.objects.all())
        packages = list(Package.objects.filter(status="on"))
        clerk = User.objects.filter(username="clerk").first()
        now = timezone.now()
        counters = {}
        status_pool = ["completed", "paid", "servicing", "pending", "cancelled", "refunded"]
        weights = [30, 24, 14, 16, 10, 6]

        for _ in range(24):
            member = random.choice(members)
            package = random.choice(packages)
            qty = 2 if random.random() < 0.18 else 1
            created = now - timedelta(days=random.randint(0, 29),
                                      hours=random.randint(0, 9), minutes=random.randint(0, 59))
            status = random.choices(status_pool, weights=weights)[0]
            day_key = created.strftime("%Y%m%d")
            counters[day_key] = counters.get(day_key, 0) + 1
            order_no = f"TK{day_key}{counters[day_key]:04d}"

            order = Order.objects.create(
                order_no=order_no, member=member, package=package, quantity=qty,
                unit_price=package.sale_price, status=status, salesperson=clerk,
                remark=random.choice(["", "会员希望周末到店服务", "老会员续卡", "活动价购买", ""]),
            )
            total = Decimal("0.00")
            for pi in package.items.select_related("service"):
                price = (pi.service.member_price or pi.service.price) * Decimal(str(member.discount))
                price = price.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                item = OrderItem.objects.create(
                    order=order, service=pi.service, times_total=pi.times * qty,
                    unit_price=price, remark=pi.remark,
                )
                total += item.amount
                if status in ("servicing", "completed"):
                    used = random.randint(0, item.times_total)
                    item.times_used = used
                    item.save(update_fields=["times_used"])

            discount = Decimal("0.00")
            if total > Decimal("1500") and random.random() < 0.45:
                discount = Decimal(random.choice(["50.00", "100.00", "150.00", "200.00"]))
            order.total_amount = total
            order.discount_amount = discount
            order.pay_amount = max(total - discount, Decimal("0.00"))

            paid_at = completed_at = None
            if status in ("paid", "servicing", "completed", "refunded"):
                paid_at = created + timedelta(hours=random.randint(1, 20))
            if status == "completed":
                completed_at = paid_at + timedelta(days=random.randint(1, 12))
            if status == "cancelled":
                order.cancel_reason = random.choice(["会员临时有事", "重复下单", "改选其他套餐"])
            order.paid_at = paid_at
            order.completed_at = completed_at
            order.save()

            Order.objects.filter(pk=order.pk).update(created_at=created)
            OrderStatusHistory.objects.create(
                order=order, from_status="", to_status="pending", operator=clerk,
                note="创建订单", created_at=created)
            if status != "pending":
                OrderStatusHistory.objects.create(
                    order=order, from_status="pending", to_status=status, operator=clerk,
                    note="演示数据状态初始化", created_at=paid_at or created)

        self.stdout.write(f"订单 {Order.objects.count()} 单")

    # ------------------------------------------------------------------ 预约
    def create_appointments(self):
        members = list(Member.objects.all())
        services = list(HealthService.objects.filter(status="on"))
        therapists = list(User.objects.filter(role__in=["therapist", "admin"]))
        operator = User.objects.filter(username="therapist").first()
        slots = [slot[0] for slot in Appointment.TIME_SLOTS]
        today = local_today()
        now = timezone.now()
        status_pool = ["finished", "confirmed", "pending", "cancelled", "servicing", "no_show"]
        weights = [38, 24, 16, 10, 6, 6]
        counters = {}

        for _ in range(34):
            member = random.choice(members)
            order = (Order.objects.filter(member=member, status__in=["paid", "servicing", "completed"])
                     .order_by("-created_at").first())
            item = None
            if order and random.random() < 0.6:
                candidates = [i for i in order.items.all() if i.times_left > 0]
                if candidates:
                    item = random.choice(candidates)
            service = item.service if item else random.choice(services)

            offset = random.randint(-21, 8)
            date = today + timedelta(days=offset)
            slot = random.choice(slots)
            status = random.choices(status_pool, weights=weights)[0]
            if offset < 0 and status in ("pending", "confirmed"):
                status = "finished"
            if offset > 0 and status in ("finished", "servicing"):
                status = "confirmed"

            day_key = date.strftime("%Y%m%d")
            counters[day_key] = counters.get(day_key, 0) + 1
            appt_no = f"YY{day_key}{counters[day_key]:04d}"
            created = now - timedelta(days=max(offset * -1, 0) + random.randint(0, 3),
                                      hours=random.randint(0, 5))

            appt = Appointment.objects.create(
                appointment_no=appt_no, member=member, service=service, order_item=item,
                therapist=random.choice(therapists), appoint_date=date, appoint_time=slot,
                duration=service.duration, status=status,
                source=random.choice(["online", "phone", "onsite", "package"]),
                contact_phone=member.phone,
                remark=random.choice(["", "希望手法轻一些", "最近睡眠不好", "肩颈酸胀明显", ""]),
                created_by=operator,
            )
            if status in ("confirmed", "servicing", "finished"):
                appt.confirmed_by = operator
                appt.confirmed_at = created + timedelta(hours=2)
            if status == "finished":
                appt.finished_at = dt.datetime.combine(
                    date, dt.datetime.strptime(slot, "%H:%M").time())
                if item and item.times_used < item.times_total:
                    item.times_used += 1
                    item.save(update_fields=["times_used"])
            if status == "cancelled":
                appt.cancelled_reason = random.choice(["会员临时取消", "身体不适改期", "顾问排班调整"])
            appt.save()
            Appointment.objects.filter(pk=appt.pk).update(created_at=created)

            AppointmentHistory.objects.create(
                appointment=appt, from_status="", to_status="pending", action="创建预约",
                operator=operator, note=f"{date} {slot} {service.name}", created_at=created)
            if status != "pending":
                AppointmentHistory.objects.create(
                    appointment=appt, from_status="pending", to_status=status,
                    action="状态处理", operator=operator, note="演示数据状态初始化",
                    created_at=created + timedelta(hours=3))

            if status == "finished" and random.random() < 0.25:
                att = AppointmentAttachment(
                    appointment=appt, original_name="服务知情同意书.txt",
                    content_type="text/plain", note="服务前签署", uploaded_by=operator,
                )
                content = f"会员：{member.name}\n服务项目：{service.name}\n服务日期：{date}\n顾问：{appt.therapist.display_name}\n".encode("utf-8")
                att.file.save("consent.txt", ContentFile(content), save=False)
                att.size = len(content)
                att.save()

        self.stdout.write(f"预约 {Appointment.objects.count()} 单")

    # ------------------------------------------------------------------ 日志
    def create_logs(self):
        users = list(User.objects.exclude(role="member"))
        now = timezone.now()
        actions = [
            ("登录系统", "auth", "User", "角色登录成功"),
            ("新增会员档案", "business", "Member", "建档并录入体质信息"),
            ("新增养生服务", "business", "HealthService", "维护服务价格与时长"),
            ("创建套餐订单", "business", "Order", "套餐订单创建并展开明细"),
            ("变更订单状态", "business", "Order", "订单状态流转"),
            ("审核服务预约", "business", "Appointment", "审核确认预约"),
            ("更新预约异常备注", "business", "Appointment", "记录服务过程异常"),
            ("导出查询结果", "query", "Report", "按条件导出报表"),
            ("配置角色权限", "system", "Group", "调整角色菜单与接口权限"),
        ]
        for _ in range(40):
            action, category, target, detail = random.choice(actions)
            user = random.choice(users)
            created = now - timedelta(days=random.randint(0, 14),
                                      hours=random.randint(0, 20))
            log = OperationLog.objects.create(
                category=category, action=action, target_type=target,
                target_repr=random.choice(["TK2026", "YY2026", "SVC00", "HY2026", ""]) + str(random.randint(1, 99)),
                detail=detail, username=user.username, role=user.get_role_display(),
                method="POST" if category != "query" else "GET",
                path="/" + random.choice(["orders/", "appointments/", "services/", "reports/"]),
                status_code=200, duration_ms=random.randint(20, 320),
                ip=f"192.168.1.{random.randint(2, 60)}",
            )
            # created_at 为 auto_now_add，创建后回写，让日志时间分布更真实
            OperationLog.objects.filter(pk=log.pk).update(created_at=created)
        self.stdout.write(f"日志 {OperationLog.objects.count()} 条")
