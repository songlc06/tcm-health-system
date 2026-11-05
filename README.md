# 中医养生会员与服务预约管理系统（Django 教学项目）

面向中医养生馆的会员档案、养生服务、套餐订单、服务预约与查询统计一体化管理系统。
系统以 **流程规范、信息留痕、便捷查询** 为目标，使用模拟业务数据完成教学实践，
不涉及真实患者隐私、复杂算法与第三方平台对接。

- 后端：Python 3.11+ / Django 5.2（SQLite 开箱即用，可一键切 MySQL）
- 前端：Django Template + Bootstrap 5 + 原生 JavaScript（本地静态资源，离线可用）
- 数据统计：Pandas 清洗汇总 + ECharts 图表
- 5 名学生按功能包独立分工，每人 3 个可演示、可测试的子功能

## 一、快速开始

```bash
# 1. 创建虚拟环境并安装依赖
python -m venv .venv
.venv\Scripts\activate            # Windows
pip install -r requirements.txt

# 2. 初始化数据库（默认 SQLite）
python manage.py migrate
python manage.py seed_demo        # 演示数据：菜单、角色权限、账号、会员、服务、套餐、订单、预约、日志

# 3. 启动
python manage.py runserver 8000
# 浏览器访问 http://127.0.0.1:8000/
```

演示账号（统一密码 `demo123456`）：

| 账号 | 角色 | 可见功能 |
| --- | --- | --- |
| `admin` | 系统管理员 | 全部功能 + 角色权限 + 用户管理 |
| `service` | 服务主管 | 养生服务管理、会员档案、查询统计 |
| `clerk` | 订单专员 | 套餐订单、会员档案、服务查询 |
| `therapist` | 健康顾问 | 服务预约、服务查询、订单查看 |
| `reporter` | 报表专员 | 查询统计、统计报表、操作日志、导出 |
| `member01` | 会员 | 会员中心（本人档案、订单、预约） |

> 密码统一为 `demo123456`；如需重置数据：`python manage.py seed_demo --reset`。

## 二、切换 MySQL

```bash
mysql -u root -p < scripts/init_mysql.sql
set DB_ENGINE=mysql
set DB_NAME=tcm_health
set DB_USER=root
set DB_PASSWORD=你的密码
python manage.py migrate
python manage.py seed_demo
```

## 三、自检与测试

```bash
python manage.py check                          # 框架级检查
python manage.py selfcheck                      # 40 个页面/权限检查点
python manage.py test accounts services orders appointments reports   # 62 条功能测试
```

## 四、目录结构

```
tcm_health_system/
├── config/                 项目配置（settings / urls / wsgi）
├── core/                   公共支撑：菜单、操作日志、首页工作台、权限混入、工具与自检命令
│   ├── management/commands/seed_demo.py     演示数据初始化
│   └── management/commands/selfcheck.py     页面与权限自检
├── accounts/               学生 1：用户与会员管理
├── services/               学生 2：养生服务管理
├── orders/                 学生 3：套餐订单管理
├── appointments/           学生 4：服务预约管理
├── reports/                学生 5：查询统计与日志（datasets / statistics）
├── templates/              页面模板（base 布局 + 各模块）
├── static/                 CSS / JS / Bootstrap / ECharts（本地化）
├── fixtures/demo_data.json 演示数据快照（loaddata 可用）
├── scripts/                init_mysql.sql、数据库设计文档生成脚本
└── docs/                   项目说明、数据库设计、测试用例、演示脚本
```

## 五、文档索引

| 文档 | 内容 |
| --- | --- |
| `docs/项目说明.md` | 功能清单、角色权限矩阵、URL 与视图对照表、业务闭环说明 |
| `docs/数据库设计.md` | 15 张业务表字段明细与表关系（由模型自动生成） |
| `docs/测试用例.md` | 62 条测试用例（按 5 名学生分组，含验证点） |
| `docs/演示脚本.md` | 5 名学生各自的演示步骤与讲解要点 |

## 六、说明

- 本系统为教学实践项目，使用模拟业务数据，不含真实患者隐私信息。
- 默认 `DEBUG=True`、SQLite、`ALLOWED_HOSTS=["*"]`，方便本地演示；如需对外部署，请设置环境变量
  `DJANGO_DEBUG=0`、`DJANGO_SECRET_KEY=<随机串>`，并补齐 `SESSION_COOKIE_SECURE` / `CSRF_COOKIE_SECURE` 与
  `ALLOWED_HOSTS`（`python manage.py check --deploy` 会给出完整清单）。
- 附件上传限制：5MB，允许 `.pdf/.png/.jpg/.jpeg/.doc/.docx/.txt`。
- 演示数据可用 `python manage.py seed_demo --reset` 反复重置；`fixtures/demo_data.json` 为同一份数据的快照
  （`python manage.py loaddata fixtures/demo_data.json` 亦可导入）。

### 关于仓库内的 `db.sqlite3`

本仓库**故意提交了 `db.sqlite3`**（约 450 KB），克隆下来不用建库、不用造数，直接
`python manage.py runserver` 就能看到完整数据：

| 表 | 记录数 | 表 | 记录数 |
|---|---|---|---|
| 用户 `accounts_user` | 7 | 会员 `accounts_member` | 12 |
| 服务分类 / 项目 | 5 / 14 | 套餐 / 套餐明细 | 5 / 11 |
| 订单 / 订单明细 | 24 / 56 | 订单状态流水 | 45 |
| 预约 / 预约附件 | 34 / 6 | 预约历史 / 操作日志 | 65 / 94 |

- 想恢复出厂数据：`python manage.py seed_demo --reset`（会清空业务表后重新造数）。
- 想切到 MySQL：按第二节建库后设置 `DB_ENGINE=mysql`，再执行 `migrate` + `seed_demo` 即可，
  SQLite 文件不会被读取，可保留存档。
- 演示账号（初始密码均为 `demo123456`）：`admin` 超级管理员、`service` 店长、`clerk` 前台、
  `therapist` / `therapist2` 技师、`reporter` 统计员、`member01` 会员端。

## 七、多端呈现

除本 Django 全栈系统外，同一套业务规则还做了两个纯静态版本，用于演示与答辩：

> 说明：本仓库只收录 Django 系统本体（含数据库与文档）。下面两个静态演示版是本地演示材料，
> 未纳入本仓库，路径以课程交付包为准。

| 版本 | 目录 | 定位 |
|---|---|---|
| 手机 H5（小程序风格） | `../mini_app` | 底部 TabBar + 卡片列表，零依赖双击即开，适合手机扫码与投屏。详见 `../mini_app/README.md` |
| 电脑网页版（后台管理） | `../pc_app` | 左侧导航 + 顶栏 + 数据表格 + 图表看板 + 弹窗表单，适合坐在电脑前完整演示。详见 `../pc_app/README.md` |

两版均内置同一份演示数据（12 会员 / 14 服务 / 5 套餐 / 40 订单 / 40 预约 / 20 日志），
数据存于浏览器 localStorage，与 Django 版的数据互不影响。三端可作为
「同一系统的 Web 端 + 移动端呈现」写进报告。
