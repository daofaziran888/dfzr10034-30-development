# 治数工坊 · 数据治理与生命周期管理平台

面向资产注册、元数据索引与搜索、质量规则引擎、数据画像与分级、脱敏与操作日志、生命周期策略、冷热归档、血缘追踪、影响分析、变更捕获与契约治理的数据治理与生命周期管理平台。

这是一个前后端分离的管理平台：前端 Vue 3 + Vite + TypeScript，后端 FastAPI（Python）。
两边各自独立启动，前端 dev server 已关掉自动打开页面，启动后按终端打印的地址手工打开。

## 目录结构

```text
.
├── frontend/                 Vue 3 + Vite + TypeScript 前端
│   ├── src/views/WorkbenchView.vue|tsx  全部模块共享工作台
│   ├── src/data/modules.ts              18个业务模块配置
│   ├── src/api/              统一请求封装
│   └── vite.config.ts        dev server 配置（open: false）
├── backend/                  FastAPI（Python） 后端
│   ├── app/routers/resource.py  通用查询/导出/登记/动作接口
│   ├── app/services/<key>.py    每个模块独立领域逻辑
│   ├── app/services/base.py     共享服务骨架
│   └── app/store.py          内存数据仓库与示例数据
├── .gitignore
└── docker-compose.yml
```

## 启动

### 后端

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
./run.sh
```

健康检查：`curl http://127.0.0.1:8000/api/health`

### 前端

```bash
cd frontend
npm ci
npm run dev
```

前端默认监听 `http://127.0.0.1:5173/`，dev server 不会自动打开浏览器，
需要自己访问。`/api` 由 vite 代理到后端 `http://127.0.0.1:8000`。

## 业务模块

| 模块 | 目录 | 业务对象 | 主要字段 |
| --- | --- | --- | --- |
| 资产注册 | `asset_registry` | 数据资产 | 资产编号、资产名称、资产类型 |
| 元数据索引 | `metadata_index` | 元数据条目 | 条目编号、所属资产、字段名称 |
| 质量规则 | `quality_rule` | 质量检查 | 规则编号、目标资产、检查类型 |
| 数据画像 | `profile_stats` | 数据画像 | 画像编号、目标资产、行数统计 |
| 数据分级 | `classification` | 分级标签 | 标签编号、目标字段、敏感等级 |
| 生命周期 | `lifecycle_policy` | 生命周期策略 | 策略编号、目标资产、创建阶段 |
| 冷热归档 | `cold_archive` | 归档任务 | 任务编号、源资产、归档条件 |
| 保留清理 | `retention_job` | 清理计划 | 计划编号、目标资产、保留天数 |
| 脱敏引擎 | `data_anonym` | 脱敏规则 | 规则编号、目标字段、脱敏算法 |
| 操作日志 | `operation_log` | 操作记录 | 记录编号、目标资产、操作人 |
| 变更捕获 | `change_capture` | 变更记录 | 记录编号、目标资产、变更类型 |
| 血缘追踪 | `lineage_track` | 血缘关系 | 关系编号、上游资产、下游资产 |
| 影响分析 | `impact_analysis` | 影响报告 | 报告编号、变更资产、影响下游 |
| 标签体系 | `tag_registry` | 业务标签 | 标签编号、标签名称、标签层级 |
| 治理评分 | `govern_score` | 评分任务 | 任务编号、评估对象、评分维度 |
| 数据契约 | `data_contract` | 契约定义 | 契约编号、数据资产、签署版本、Schema约束 |
| 字段目录 | `field_catalog` | 字段版本 | 字段编号、所属资产、字段名称、字段版本 |
| 消费方字段授权 | `contract_grant` | 列级授权 | 授权编号、契约编号、签署版本、字段标识 |
| 交付清单 | `delivery_note` | 交付分区 | 清单编号、分区编号、分区类型、可读字段 |
| 合规扫描 | `compliance_scan` | 扫描任务 | 任务编号、目标资产、合规条款 |
| 问题追踪 | `issue_track` | 治理问题 | 问题编号、关联资产、问题类型 |
| 版本履历 | `version_history` | 版本快照 | 快照编号、目标资产、版本标签 |
| 调度治理 | `schedule_job` | 治理调度 | 作业编号、治理类型、目标资产 |
| 差异报告 | `diff_report` | 差异记录 | 记录编号、比较对象、比较维度 |
| 负责人管理 | `owner_mgr` | 责任人 | 指派编号、目标资产、负责角色 |

## 约定

- 全部模块共享`frontend/src/views/WorkbenchView.vue|tsx`和一套资源路由。
- 每个模块仍保留独立`backend/app/services/<模块>.py`；纯前端保留
  `frontend/src/domain/<模块>.ts`，用于承载真实业务差异并维持36题位容量。
- 列表接口统一返回 `{ items, total, page, size }`，动作接口统一返回 `{ ok, message }`。
- 状态流转只允许在 `app/services` 里改，路由层不做业务判断。

## 契约消费方字段授权（列级授权）

数据契约之外，发数人员通过 `/api/column-authorization/*` 完成列级授权闭环：

- **签署版本**：`data_contract` 每份契约带签署版本（v1.0、v2.0 ……）和签约字段，
  签署时调用负责人管理核验资产指派，结果随契约留痕。
- **字段版本**：`field_catalog` 按资产发布字段，同名字段重新发布自动递增版本
  （`资产.字段名@vN`），旧版本保留可追溯。
- **列级授权**：`contract_grant` 按签署版本把消费方声明关联到实际字段。越权申请
  （契约未签署、消费方不符、字段未在该签署版本声明、字段未发布）按资产和签署
  版本拒绝并留痕；其他消费方的历史凭据不能授予新列。
- **授权冲突**：同一名称被两个消费方绑定到不同字段版本时进入「冲突待处理」，
  发数人员可保留原版本、切换新版本或撤回授权。
- **交付清单**：`delivery_note` 登记旧/新分区并固化分区字段版本，领取时按字段
  版本计算消费方实际可读列并回写每列的契约签署依据；财务独有金额不会随同名单号
  泄到售后清单，已发出的旧版分区始终可追溯。
- 前端「列级授权工作台」（`/column-authorization`）串起指派、发布、签署、授权、
  冲突处理与分区领取全流程；三个新模块同时登记在通用工作台导航中。

领域：数据工程
子方向：数仓与数据湖
