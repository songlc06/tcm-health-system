-- =====================================================================
-- 中医养生会员与服务预约管理系统 —— MySQL 初始化脚本
-- 说明：
--   1. 本脚本负责“建库 + 建账号 + 授权”，业务表由 Django 迁移创建，
--      避免手写 DDL 与模型不一致（迁移文件本身就是受版本管理的建表脚本）。
--   2. 表结构说明见 docs/数据库设计.md（由模型自动生成，共 15 张业务表）。
-- 执行：
--   mysql -u root -p < scripts/init_mysql.sql
-- =====================================================================

CREATE DATABASE IF NOT EXISTS `tcm_health`
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_general_ci;

-- 教学环境可直接用 root；如单独建账号，取消下面两行注释
-- CREATE USER IF NOT EXISTS 'tcm'@'localhost' IDENTIFIED BY 'Tcm@2026';
-- GRANT ALL PRIVILEGES ON `tcm_health`.* TO 'tcm'@'localhost';

USE `tcm_health`;

-- ---------------------------------------------------------------------
-- 时区与严格模式（与 settings.py 中 init_command 保持一致）
-- ---------------------------------------------------------------------
SET time_zone = '+08:00';
SET sql_mode = 'STRICT_TRANS_TABLES';

-- ---------------------------------------------------------------------
-- 建表（在项目根目录执行，二选一）
--   A. 推荐：DB_ENGINE=mysql python manage.py migrate
--   B. 或直接执行迁移 SQL：
--        DB_ENGINE=mysql python manage.py sqlmigrate accounts 0001
--        DB_ENGINE=mysql python manage.py sqlmigrate services 0001
--        DB_ENGINE=mysql python manage.py sqlmigrate orders 0001
--        DB_ENGINE=mysql python manage.py sqlmigrate appointments 0001
--        DB_ENGINE=mysql python manage.py sqlmigrate core 0001
-- ---------------------------------------------------------------------

-- 业务表清单（migrate 后可用 SHOW TABLES 核对）
--   accounts_user                    系统用户（自建 User 表，替代 auth_user）
--   accounts_member                  会员档案
--   services_servicecategory         服务分类
--   services_healthservice           养生服务项目
--   services_servicepricehistory     服务价格变更留痕
--   orders_package                   养生套餐
--   orders_packageitem               套餐明细（服务 + 次数）
--   orders_order                     套餐订单
--   orders_orderitem                 订单明细（购买/已用次数）
--   orders_orderstatushistory        订单状态流转记录
--   appointments_appointment         服务预约单
--   appointments_appointmenthistory  预约处理记录（全流程留痕）
--   appointments_appointmentattachment 预约附件（体检报告/知情同意书）
--   core_menu                        菜单与菜单级权限
--   core_operationlog                操作日志（业务 + 请求维度）

-- ---------------------------------------------------------------------
-- 初始化演示数据（含菜单、角色权限、演示账号与模拟业务数据）
--   DB_ENGINE=mysql python manage.py seed_demo
-- 演示账号：admin / service / clerk / therapist / reporter / member01
-- 统一密码：demo123456
-- ---------------------------------------------------------------------
