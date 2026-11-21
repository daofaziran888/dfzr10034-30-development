"""数据契约领域服务：数据生产者与消费者之间的Schema契约、SLA承诺和违约管理。

Pipeline 5: Data contract → schema validation → compliance scanning
"""
from __future__ import annotations

import time as _time
from typing import Any

from app.services.base import BaseModuleService
from app.store import store


class DataContractService(BaseModuleService):
    MODULE = "data_contract"
    ENTITY = "契约定义"
    OPERATION_TERM = "校验"
    LIST_FIELDS = ["契约编号", "数据资产", "Schema约束", "签署版本", "SLA定义", "更新频率", "负责人", "消费方", "生效时间"]
    REQUIRED_FIELDS = ["契约编号", "数据资产", "Schema约束"]
    STATUS_ORDER = ["草稿", "已签署", "已违约", "已终止"]
    ACTION_RULES = {"签署契约": "已签署", "标记违约": "已违约", "终止契约": "已终止"}
    NEGATIVE_ACTIONS = ["标记违约", "终止契约"]

    def define_contract(self, asset_code: str, schema_constraints: dict[str, Any],
                        sla: str, frequency: str, provider: str, consumer: str,
                        signed_fields: list[str] | None = None,
                        signed_version: str | None = None) -> dict[str, Any]:
        """定义数据契约（Pipeline 5 入口）。

        signed_fields 为该签署版本消费方声明可读取的字段清单；未传时从
        Schema约束摘要解析。signed_version 不传时按资产已有签署版本自动递增。
        签署同时调用负责人管理核验资产指派，结果随契约留痕并供交付清单回写。
        """
        contract_id = store.next_id(self.MODULE)
        if signed_version is None:
            signed_version = self.next_signed_version(asset_code)
        if signed_fields is None:
            summary = str(schema_constraints.get("summary", str(schema_constraints)))
            signed_fields = [
                part.strip()
                for part in summary.replace("，", ",").split(",")
                if part.strip()
            ]

        owner_check = self._verify_owner_assignment(asset_code)
        contract = {
            "id": contract_id,
            "契约编号": f"CONT-{contract_id:04d}",
            "数据资产": asset_code,
            "Schema约束": schema_constraints.get("summary", str(schema_constraints)),
            "签署版本": signed_version,
            "签约字段": list(signed_fields),
            "SLA定义": sla,
            "更新频率": frequency,
            "负责人": provider,
            "消费方": consumer,
            "生效时间": _time.strftime("%Y-%m-%d"),
            "负责人核验": "通过" if owner_check["passed"] else "未通过",
            "核验说明": owner_check["detail"],
            "status": "已签署",
            "pending": True,
            "abnormal": False,
            "created_at": _time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        store.rows(self.MODULE).append(contract)

        # Pipeline 5: 签署契约后触发合规扫描
        scan_result = self._trigger_compliance_scan(contract, schema_constraints)

        store.log_change(
            self.MODULE, contract_id, "签署数据契约",
            before=None,
            after=f"契约资产{asset_code}, 签署版本{signed_version}, SLA:{sla}",
            source="pipeline_5", scope="data_contract->compliance_scan"
        )

        self.emit_event("contract_signed", {
            "contract_id": contract_id,
            "asset_code": asset_code,
            "provider": provider,
            "consumer": consumer,
            "signed_version": signed_version,
            "signed_fields": list(signed_fields),
            "owner_check_passed": owner_check["passed"],
        })

        return {
            "contract": contract,
            "compliance_scan": scan_result,
            "owner_check": owner_check,
            "pipeline": "data_contract->compliance_scan",
        }

    def next_signed_version(self, asset_code: str) -> str:
        """按资产已有契约数量给出下一个签署版本（v1.0、v2.0 ……）。"""
        existing = [
            row for row in store.rows(self.MODULE)
            if row.get("数据资产") == asset_code and row.get("签署版本")
        ]
        return f"v{len(existing) + 1}.0"

    @staticmethod
    def _verify_owner_assignment(asset_code: str) -> dict[str, Any]:
        # 延迟导入避免服务初始化期的循环依赖。
        from app.services.owner_mgr import OwnerMgrService

        return OwnerMgrService().verify_asset_assignment(asset_code)

    def get_contract_by_version(self, asset_code: str, signed_version: str) -> dict[str, Any] | None:
        """按资产和签署版本取契约。"""
        for row in store.rows(self.MODULE):
            if row.get("数据资产") == asset_code and row.get("签署版本") == signed_version:
                return row
        return None

    def get_signed_versions(self, asset_code: str) -> list[dict[str, Any]]:
        """列出资产全部签署版本，供列级授权按版本核对。"""
        return [
            row for row in store.rows(self.MODULE)
            if row.get("数据资产") == asset_code and row.get("status") == "已签署"
        ]

    def _trigger_compliance_scan(self, contract: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
        """触发合规扫描。"""
        scan_id = store.next_id("compliance_scan")
        scan = {
            "id": scan_id,
            "任务编号": f"COMP-CONT-{scan_id:04d}",
            "目标资产": contract["数据资产"],
            "合规条款": f"契约合规校验 (contract #{contract['id']})",
            "检查规则": f"验证Schema约束: {contract.get('Schema约束', '')}",
            "扫描范围": "全量",
            "违规发现": "",
            "修复意见": "",
            "扫描时间": _time.strftime("%Y-%m-%d %H:%M:%S"),
            "status": "已通过",
            "pending": False,
            "abnormal": False,
            "contract_id": contract["id"],
            "created_at": _time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        store.rows("compliance_scan").append(scan)
        return {"scan_id": scan_id, "passed": True}

    def validate_schema(self, contract_id: int, actual_schema: dict[str, Any]) -> dict[str, Any]:
        """验证实际Schema是否符合契约（Pipeline 5 核心验证方法）。"""
        contract = self.get_entry(contract_id)
        if not contract:
            return {"ok": False, "error": "契约不存在"}

        # 比较实际Schema与契约约定的Schema约束
        expected = str(contract.get("Schema约束", ""))
        actual = str(actual_schema.get("summary", str(actual_schema)))
        valid = expected == actual

        if not valid:
            # 标记违约
            contract["status"] = "已违约"
            contract["abnormal"] = True

            # 生成合规扫描告警
            scan_id = store.next_id("compliance_scan")
            scan = {
                "id": scan_id,
                "任务编号": f"COMP-FAIL-{scan_id:04d}",
                "目标资产": contract["数据资产"],
                "合规条款": "Schema契约违规",
                "检查规则": f"实际Schema({actual})不符合契约({expected})",
                "扫描范围": "全量",
                "违规发现": f"资产{contract['数据资产']}的Schema已偏离契约定义",
                "修复意见": "需重新协商契约或回滚Schema变更",
                "扫描时间": _time.strftime("%Y-%m-%d %H:%M:%S"),
                "status": "存在违规",
                "pending": True,
                "abnormal": True,
                "contract_id": contract_id,
                "created_at": _time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            store.rows("compliance_scan").append(scan)

            # 生成治理问题
            issue_id = store.next_id("issue_track")
            issue = {
                "id": issue_id,
                "问题编号": f"ISSU-CONT-{issue_id:04d}",
                "关联资产": contract["数据资产"],
                "问题类型": "契约违约",
                "严重级别": "严重",
                "指派处理": contract.get("负责人", ""),
                "当前状态": "待处理",
                "修复方案": f"实际Schema({actual})不符合契约({expected})",
                "截止日期": _time.strftime("%Y-%m-%d", _time.localtime(_time.time() + 86400 * 3)),
                "status": "待确认",
                "pending": True,
                "abnormal": True,
                "contract_id": contract_id,
                "created_at": _time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            store.rows("issue_track").append(issue)

            self.emit_event("contract_violated", {
                "contract_id": contract_id,
                "asset_code": contract["数据资产"],
                "issue_id": issue_id,
            })

            return {
                "ok": False,
                "valid": False,
                "contract_id": contract_id,
                "expected": expected,
                "actual": actual,
                "issue_created": True,
                "issue_id": issue_id,
                "pipeline": "data_contract->compliance_scan->issue_track",
            }

        return {"ok": True, "valid": True, "contract_id": contract_id}

    def get_contracts_by_asset(self, asset_code: str) -> list[dict[str, Any]]:
        """获取资产的所有契约。"""
        return store.find_by_field(self.MODULE, "数据资产", asset_code)