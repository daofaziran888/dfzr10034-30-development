"""契约消费方字段授权领域服务：发数人员使用的列级授权台账。

把数据契约中消费方在「签署版本」里声明的字段，关联到字段目录里的实际字段
（资产 + 字段名 + 字段版本），形成消费方真正能读取的列。

关键规则：
- 越权申请按资产和签署版本拒绝：契约不存在/未签署、资产不符、消费方与契约
  约定不符、字段未在该签署版本声明，一律拒绝并留痕。
- 一个消费方不能拿另一个消费方契约的历史凭据给新列授权。
- 资产交接后同名字段重新发布为新版本，两个消费方把同一名称绑到不同字段
  版本时产生授权冲突，发数人员可保留原版本、切换新版本或撤回授权。
- 授权绑定字段标识（资产.字段名@vN），旧版分区已经发出的授权不会被同名
  新列覆盖，始终可追溯。
"""
from __future__ import annotations

import time as _time
from typing import Any

from app.services.base import BaseModuleService
from app.services.field_catalog import FieldCatalogService
from app.store import store

# 仍然有效的授权状态（已拒绝、已解除的历史凭据不再产生可读列）
EFFECTIVE_STATUSES = ("已授权", "冲突待处理")


class ContractGrantService(BaseModuleService):
    MODULE = "contract_grant"
    ENTITY = "消费方字段授权"
    OPERATION_TERM = "核验"
    LIST_FIELDS = [
        "授权编号", "数据资产", "契约编号", "签署版本", "消费方",
        "字段名称", "字段标识", "字段版本", "授权依据", "授权时间",
    ]
    REQUIRED_FIELDS = ["授权编号", "数据资产", "消费方", "字段名称"]
    STATUS_ORDER = ["待核验", "已授权", "冲突待处理", "已拒绝", "已解除"]
    ACTION_RULES = {
        "核验授权": "已授权",
        "标记冲突": "冲突待处理",
        "驳回授权": "已拒绝",
        "解除授权": "已解除",
    }
    NEGATIVE_ACTIONS = ["驳回授权", "解除授权"]

    def __init__(self) -> None:
        self.field_catalog = FieldCatalogService()

    # ── 列级授权 ──────────────────────────────────────────────

    def grant_field(
        self,
        contract_id: int,
        consumer: str,
        field_name: str,
        field_version: str | None = None,
    ) -> dict[str, Any]:
        """按契约签署版本把消费方声明的字段关联到实际字段并授权。

        成功返回 ``{"ok": True, "grant": ..., "conflict": bool}``；
        越权返回 ``{"ok": False, "reason": ..., "grant": 拒绝留痕行}``。
        """
        contract = store.find("data_contract", contract_id)
        # 越权拒绝也写入台账留痕，先把拒绝行准备好。
        def _reject(reason: str, asset_code: str = "", signed_version: str = "") -> dict[str, Any]:
            grant = self._append_grant(
                asset_code=asset_code or "",
                contract=contract,
                signed_version=signed_version,
                consumer=consumer,
                field_name=field_name,
                field_key="",
                field_ver="",
                basis="",
                status="已拒绝",
                reason=reason,
            )
            return {"ok": False, "reason": reason, "grant": grant, "conflict": False}

        if contract is None:
            return _reject(f"契约#{contract_id}不存在，无法按签署版本授权")
        if contract.get("status") != "已签署":
            return _reject(
                f"契约{contract.get('契约编号', '')}未签署，授权申请拒绝",
                contract.get("数据资产", ""), contract.get("签署版本", ""),
            )

        asset_code = str(contract.get("数据资产", ""))
        signed_version = str(contract.get("签署版本", ""))

        # 越权规则 1：消费方必须与契约约定的消费方一致，不能拿别人的契约凭据申请。
        if str(contract.get("消费方", "")) != str(consumer):
            return _reject(
                f"消费方{consumer}与契约{contract.get('契约编号', '')}约定的"
                f"消费方{contract.get('消费方', '')}不符，禁止借用历史凭据申请新列",
                asset_code, signed_version,
            )

        # 越权规则 2：字段必须在该契约签署版本的声明范围内。
        signed_fields = self._signed_fields(contract)
        if field_name not in signed_fields:
            return _reject(
                f"字段{field_name}未在契约{contract.get('契约编号', '')}"
                f"签署版本{signed_version}中声明（声明字段：{','.join(signed_fields) or '无'}），越权申请拒绝",
                asset_code, signed_version,
            )

        # 关联字段目录里的实际字段版本。
        field_key = self.field_catalog.resolve_field_key(asset_code, field_name, field_version)
        if field_key is None:
            return _reject(
                f"资产{asset_code}未发布字段{field_name}"
                + (f"的{field_version}版本" if field_version else ""),
                asset_code, signed_version,
            )
        field_entry = self.field_catalog.get_field(field_key)
        field_ver = str(field_entry["字段版本"])
        basis = (
            f"{contract.get('契约编号', '')} {signed_version} 声明字段{field_name}"
        )

        # 幂等：同一消费方对同一字段版本已有有效授权时直接返回，不重复建台账，
        # 避免可读列清单出现重复列。
        existing = next(
            (
                row for row in store.rows(self.MODULE)
                if row.get("数据资产") == asset_code
                and row.get("消费方") == consumer
                and row.get("字段标识") == field_key
                and row.get("status") in EFFECTIVE_STATUSES
            ),
            None,
        )
        if existing is not None:
            return {
                "ok": True,
                "grant": existing,
                "conflict": existing.get("status") == "冲突待处理",
                "duplicated": True,
            }

        # 冲突检测：同一资产同一字段名，其他消费方已绑定到不同字段标识（不同字段）。
        conflict = self._find_conflict(asset_code, field_name, field_key, consumer)

        status = "冲突待处理" if conflict else "已授权"
        grant = self._append_grant(
            asset_code=asset_code,
            contract=contract,
            signed_version=signed_version,
            consumer=consumer,
            field_name=field_name,
            field_key=field_key,
            field_ver=field_ver,
            basis=basis,
            status=status,
            reason="",
        )
        if conflict:
            grant["冲突说明"] = (
                f"同名字段{field_name}已由消费方{conflict['消费方']}绑定到"
                f"{conflict['字段标识']}，本次申请绑定到{field_key}，需发数人员处理"
            )
            grant["冲突授权编号"] = conflict["授权编号"]
            store.log_change(
                self.MODULE, grant["id"], "列级授权冲突",
                before=conflict["字段标识"], after=field_key,
                source="grant", scope=f"asset:{asset_code};field:{field_name}"
            )
        else:
            store.log_change(
                self.MODULE, grant["id"], "列级授权通过",
                before=None, after=field_key,
                source="grant", scope=f"contract:{contract_id}"
            )

        self.emit_event("column_granted", {
            "grant_id": grant["id"],
            "contract_id": contract_id,
            "asset_code": asset_code,
            "consumer": consumer,
            "field_key": field_key,
            "conflict": bool(conflict),
        })
        return {"ok": True, "grant": grant, "conflict": bool(conflict)}

    def _append_grant(
        self,
        asset_code: str,
        contract: dict[str, Any] | None,
        signed_version: str,
        consumer: str,
        field_name: str,
        field_key: str,
        field_ver: str,
        basis: str,
        status: str,
        reason: str,
    ) -> dict[str, Any]:
        grant_id = store.next_id(self.MODULE)
        grant = {
            "id": grant_id,
            "授权编号": f"GRAN-{grant_id:04d}",
            "数据资产": asset_code,
            "契约编号": contract.get("契约编号", "") if contract else "",
            "契约ID": contract["id"] if contract else None,
            "签署版本": signed_version,
            "消费方": consumer,
            "字段名称": field_name,
            "字段标识": field_key,
            "字段版本": field_ver,
            "授权依据": basis,
            "拒绝原因": reason,
            "冲突说明": "",
            "冲突授权编号": "",
            "处理结论": "",
            "授权时间": _time.strftime("%Y-%m-%d %H:%M:%S"),
            "status": status,
            "pending": status in ("待核验", "冲突待处理"),
            "abnormal": status in ("冲突待处理", "已拒绝"),
            "created_at": _time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        store.rows(self.MODULE).append(grant)
        return grant

    @staticmethod
    def _signed_fields(contract: dict[str, Any]) -> list[str]:
        """提取契约签署版本声明的字段清单。"""
        declared = contract.get("签约字段")
        if isinstance(declared, list) and declared:
            return [str(item).strip() for item in declared if str(item).strip()]
        # 兼容只写了 Schema约束 摘要的旧契约：按逗号拆分。
        summary = str(contract.get("Schema约束", ""))
        return [part.strip() for part in summary.replace("，", ",").split(",") if part.strip()]

    def _find_conflict(
        self, asset_code: str, field_name: str, field_key: str, consumer: str
    ) -> dict[str, Any] | None:
        for row in store.rows(self.MODULE):
            if (
                row.get("数据资产") == asset_code
                and row.get("字段名称") == field_name
                and row.get("消费方") != consumer
                and row.get("status") in EFFECTIVE_STATUSES
                and row.get("字段标识")
                and row.get("字段标识") != field_key
            ):
                return row
        return None

    # ── 冲突处理 ──────────────────────────────────────────────

    def detect_conflicts(self, asset_code: str | None = None) -> list[dict[str, Any]]:
        """列出待处理的同名异字段授权冲突。"""
        rows = store.rows(self.MODULE)
        if asset_code:
            rows = [row for row in rows if row.get("数据资产") == asset_code]
        return [row for row in rows if row.get("status") == "冲突待处理"]

    def resolve_conflict(self, grant_id: int, resolution: str,
                         target_field_key: str | None = None) -> dict[str, Any]:
        """处理授权冲突。

        resolution 取值：
        - ``保留原版本``：维持当前绑定的字段版本，授权生效；
        - ``切换新版本``：改绑到 target_field_key（不传则取同名字段最新版本）；
        - ``撤回授权``：解除该消费方对这一列的授权。
        """
        grant = self.get_entry(grant_id)
        if grant is None:
            return {"ok": False, "message": f"授权 {grant_id} 不存在"}
        if grant.get("status") != "冲突待处理":
            return {"ok": False, "message": f"授权{grant.get('授权编号')}不在冲突待处理状态"}

        if resolution == "保留原版本":
            grant["处理结论"] = "保留原版本：维持绑定 " + str(grant.get("字段标识"))
            grant["status"] = "已授权"
            grant["pending"] = False
            grant["abnormal"] = False
        elif resolution == "切换新版本":
            asset_code = str(grant.get("数据资产", ""))
            field_name = str(grant.get("字段名称", ""))
            new_key = target_field_key or (
                self.field_catalog.latest_field(asset_code, field_name) or {}
            ).get("字段标识")
            new_field = self.field_catalog.get_field(new_key) if new_key else None
            if new_field is None:
                return {"ok": False, "message": f"切换目标字段{new_key}不存在"}
            grant["字段标识"] = new_field["字段标识"]
            grant["字段版本"] = new_field["字段版本"]
            grant["授权依据"] = (
                f"{grant.get('契约编号', '')} {grant.get('签署版本', '')} "
                f"声明字段{field_name}，冲突处理后切换至{new_field['字段版本']}"
            )
            grant["处理结论"] = f"切换新版本：改绑到 {new_field['字段标识']}"
            grant["status"] = "已授权"
            grant["pending"] = False
            grant["abnormal"] = False
        elif resolution == "撤回授权":
            grant["处理结论"] = "撤回授权：解除该消费方对本列的读取权限"
            grant["status"] = "已解除"
            grant["pending"] = False
            grant["abnormal"] = True
        else:
            return {"ok": False, "message": f"不支持的冲突处理方式：{resolution}"}

        grant["授权时间"] = grant.get("授权时间", _time.strftime("%Y-%m-%d %H:%M:%S"))
        store.log_change(
            self.MODULE, grant_id, "处理授权冲突",
            before="冲突待处理", after=grant["status"],
            source="grant", scope=resolution
        )
        return {"ok": True, "grant": grant, "message": f"冲突已按「{resolution}」处理"}

    # ── 可读列与追溯 ──────────────────────────────────────────

    def get_grants_by_consumer(self, asset_code: str, consumer: str) -> list[dict[str, Any]]:
        return [
            row for row in store.rows(self.MODULE)
            if row.get("数据资产") == asset_code
            and row.get("消费方") == consumer
            and row.get("status") in EFFECTIVE_STATUSES
        ]

    def get_grants_by_contract(self, contract_id: int) -> list[dict[str, Any]]:
        return [
            row for row in store.rows(self.MODULE)
            if row.get("契约ID") == contract_id
        ]

    def trace_grants(self, asset_code: str, consumer: str | None = None) -> list[dict[str, Any]]:
        """追溯资产上已发出的全部授权（含已拒绝、已解除的历史凭据）。"""
        rows = [
            row for row in store.rows(self.MODULE)
            if row.get("数据资产") == asset_code
        ]
        if consumer:
            rows = [row for row in rows if row.get("消费方") == consumer]
        return rows

    def readable_columns(
        self,
        asset_code: str,
        consumer: str,
        field_versions: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        """按字段版本计算消费方在某分区上实际可读的列及签署依据。

        ``field_versions`` 为分区内字段名 -> 字段版本（如 ``{"ticket_no": "v1"}``）；
        不传版本时按授权绑定的字段标识匹配。只有有效授权且字段标识与分区
        字段版本一致的列才会返回，财务独有金额不会因为同名单号泄到售后清单。
        """
        field_versions = field_versions or {}
        columns: list[dict[str, Any]] = []
        for grant in self.get_grants_by_consumer(asset_code, consumer):
            field_name = str(grant.get("字段名称", ""))
            bound_key = str(grant.get("字段标识", ""))
            if field_name in field_versions:
                label = field_versions[field_name]
                label = label if str(label).startswith("v") else f"v{label}"
                expected_key = f"{asset_code}.{field_name}@{label}"
                if bound_key != expected_key:
                    # 分区里的字段版本与该消费方授权绑定的版本不是同一个字段，不可读。
                    continue
            columns.append({
                "字段名称": field_name,
                "字段版本": grant.get("字段版本", ""),
                "字段标识": bound_key,
                "契约编号": grant.get("契约编号", ""),
                "签署版本": grant.get("签署版本", ""),
                "授权编号": grant.get("授权编号", ""),
                "授权依据": grant.get("授权依据", ""),
            })
        return columns
