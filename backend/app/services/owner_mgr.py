"""负责人管理领域服务：数据资产的责任人指派、备份安排和交接记录管理。

维护资产的责任所有权分配，支持交接和过期管理。
"""
from __future__ import annotations

import time as _time
from typing import Any

from app.services.base import BaseModuleService
from app.store import store


class OwnerMgrService(BaseModuleService):
    MODULE = "owner_mgr"
    ENTITY = "责任人"
    OPERATION_TERM = "校验"
    LIST_FIELDS = ["指派编号", "目标资产", "负责角色", "责任人", "备份人", "生效日期", "交接记录", "最后确认"]
    REQUIRED_FIELDS = ["指派编号", "目标资产", "负责角色"]
    STATUS_ORDER = ["待确认", "已生效", "交接中", "已过期"]
    ACTION_RULES = {"确认指派": "已生效", "发起交接": "交接中", "标记过期": "已过期"}
    NEGATIVE_ACTIONS = ["标记过期"]

    def assign_owner(self, asset_code: str, role: str, owner: str, backup: str = "") -> dict[str, Any]:
        """为资产指派负责人。"""
        assign_id = store.next_id(self.MODULE)
        assignment = {
            "id": assign_id,
            "指派编号": f"OWNE-{assign_id:04d}",
            "目标资产": asset_code,
            "负责角色": role,
            "责任人": owner,
            "备份人": backup,
            "生效日期": _time.strftime("%Y-%m-%d"),
            "交接记录": "",
            "最后确认": _time.strftime("%Y-%m-%d %H:%M:%S"),
            "status": "已生效",
            "pending": False,
            "abnormal": False,
            "created_at": _time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        store.rows(self.MODULE).append(assignment)

        self.emit_event("owner_assigned", {
            "assignment_id": assign_id,
            "asset_code": asset_code,
            "owner": owner,
            "role": role,
        })

        return assignment

    def handover(self, assign_id: int, new_owner: str) -> dict[str, Any] | None:
        """负责人交接。"""
        assignment = self.get_entry(assign_id)
        if not assignment:
            return None

        old_owner = assignment.get("责任人", "")
        assignment["交接记录"] = f"从{old_owner}交接到{new_owner} ({_time.strftime('%Y-%m-%d %H:%M:%S')})"
        assignment["责任人"] = new_owner
        assignment["最后确认"] = _time.strftime("%Y-%m-%d %H:%M:%S")
        assignment["status"] = "交接中"
        assignment["pending"] = True

        store.log_change(
            self.MODULE, assign_id, "负责人交接",
            before=old_owner, after=new_owner,
            source="handover", scope="owner_mgr"
        )

        self.emit_event("owner_handover", {
            "assignment_id": assign_id,
            "asset": assignment.get("目标资产"),
            "from": old_owner,
            "to": new_owner,
        })

        return assignment

    def confirm_assignment(self, assign_id: int) -> dict[str, Any] | None:
        """确认指派已生效。"""
        return self.run_action(assign_id, "确认指派")[0]

    def mark_expired(self, assign_id: int) -> dict[str, Any] | None:
        """标记指派为已过期。"""
        return self.run_action(assign_id, "标记过期")[0]

    def get_owners_by_asset(self, asset_code: str) -> list[dict[str, Any]]:
        """获取资产的所有负责人指派。"""
        return store.find_by_field(self.MODULE, "目标资产", asset_code)

    def get_owners_by_person(self, person: str) -> list[dict[str, Any]]:
        """获取某人负责的所有资产。"""
        return store.find_by_field(self.MODULE, "责任人", person)

    def verify_asset_assignment(self, asset_code: str) -> dict[str, Any]:
        """契约签署/交付时核验资产是否存在生效中的负责人指派。

        核验结果供数据契约签署与交付清单回写复用：
        - 已存在生效（或交接中）指派：核验通过，返回当前责任人；
        - 无任何指派或全部过期：核验未过，要求先完成资产指派。
        """
        assignments = self.get_owners_by_asset(asset_code)
        active = [
            row for row in assignments
            if row.get("status") in ("已生效", "交接中") and row.get("责任人")
        ]
        if active:
            current = sorted(active, key=lambda row: int(row.get("id", 0)))[-1]
            return {
                "passed": True,
                "asset_code": asset_code,
                "owner": current.get("责任人", ""),
                "assignment_id": current.get("id"),
                "指派编号": current.get("指派编号", ""),
                "detail": f"资产{asset_code}存在生效指派{current.get('指派编号', '')}，"
                          f"负责人{current.get('责任人', '')}",
            }
        if assignments:
            return {
                "passed": False,
                "asset_code": asset_code,
                "owner": "",
                "assignment_id": None,
                "指派编号": "",
                "detail": f"资产{asset_code}的负责人指派均已过期，需重新指派",
            }
        return {
            "passed": False,
            "asset_code": asset_code,
            "owner": "",
            "assignment_id": None,
            "指派编号": "",
            "detail": f"资产{asset_code}缺少负责人指派，签署前需先在负责人管理中登记",
        }