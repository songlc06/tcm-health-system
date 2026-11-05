"""根据 Django 模型自动生成《数据库设计》文档（docs/数据库设计.md）。

用法：
    python scripts/export_schema_doc.py
"""
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from django.apps import apps  # noqa: E402

APPS = [
    ("accounts", "学生 1：用户与会员管理"),
    ("services", "学生 2：养生服务管理"),
    ("orders", "学生 3：套餐订单管理"),
    ("appointments", "学生 4：服务预约管理"),
    ("core", "学生 5：查询统计与日志（+ 公共支撑）"),
]


def field_note(field):
    if field.primary_key:
        return "主键"
    if field.is_relation:
        target = field.related_model._meta.verbose_name
        extra = f"，{field.remote_field.on_delete.__name__}" if not field.many_to_many else ""
        return f"外键 → {target}{extra}"
    if field.choices:
        return "枚举：" + "、".join(f"{k}={v}" for k, v in field.choices)
    default = field.get_default()
    if default not in ("", None) and not callable(default):
        return f"默认 {default}"
    return ""


def main():
    lines = [
        "# 数据库设计说明",
        "",
        "> 本文档由 `python scripts/export_schema_doc.py` 依据 `models.py` 自动生成，",
        "> 与代码保持一致。生产/验收环境可用 `DB_ENGINE=mysql python manage.py migrate` 建表。",
        "",
        "## 一、总体结构",
        "",
        "| 数据表 | 中文名 | 所属模块 |",
        "| --- | --- | --- |",
    ]
    models_by_app = {}
    for app_label, _ in APPS:
        models_by_app[app_label] = list(apps.get_app_config(app_label).get_models())
        for model in models_by_app[app_label]:
            lines.append(f"| `{model._meta.db_table}` | {model._meta.verbose_name} | {app_label} |")

    lines += ["", "## 二、表结构明细", ""]
    for app_label, desc in APPS:
        lines += [f"### {desc}", ""]
        for model in models_by_app[app_label]:
            meta = model._meta
            lines += [f"#### `{meta.db_table}` — {meta.verbose_name}", ""]
            if meta.verbose_name_plural != meta.verbose_name:
                lines.append(f"- 复数名：{meta.verbose_name_plural}")
            if meta.unique_together:
                lines.append(f"- 唯一约束：{meta.unique_together}")
            if meta.permissions:
                lines.append("- 自定义权限：" + "、".join(p[1] for p in meta.permissions))
            lines += ["", "| 字段 | 类型 | 约束 | 说明 |", "| --- | --- | --- | --- |"]
            for field in meta.local_fields:
                name = field.db_column or field.attname
                ftype = field.get_internal_type()
                rules = []
                if field.primary_key:
                    rules.append("PK")
                elif field.unique:
                    rules.append("UK")
                if field.db_index and not field.primary_key:
                    rules.append("IDX")
                if not field.null and not field.blank and not field.has_default() and not field.primary_key:
                    rules.append("NOT NULL")
                lines.append(
                    f"| {name} | {ftype} | {'，'.join(rules) or '—'} | "
                    f"{field.verbose_name}；{field_note(field)} |".replace("； |", " |")
                )
            lines.append("")

    lines += [
        "## 三、关键表关系",
        "",
        "```",
        "User 1--1 Member          会员账号与档案",
        "Member 1--N Order         会员购买套餐订单",
        "Package 1--N PackageItem  套餐包含服务与次数",
        "Order 1--N OrderItem      订单明细（服务次数核销）",
        "OrderItem 1--N Appointment 明细驱动的预约核销",
        "HealthService 1--N Appointment / OrderItem / PackageItem",
        "Appointment 1--N AppointmentHistory / AppointmentAttachment",
        "OperationLog 独立登记，按 target_type + target_id 关联业务对象",
        "```",
        "",
        "## 四、建库脚本",
        "",
        "见 `scripts/init_mysql.sql`（建库 + 授权）。业务表由 Django 迁移创建：",
        "",
        "```bash",
        "DB_ENGINE=mysql DB_NAME=tcm_health DB_USER=root DB_PASSWORD=****** python manage.py migrate",
        "DB_ENGINE=mysql python manage.py seed_demo",
        "```",
        "",
    ]
    target = BASE_DIR / "docs" / "数据库设计.md"
    target.write_text("\n".join(lines), encoding="utf-8")
    print(f"已生成 {target}")


if __name__ == "__main__":
    main()
