"""契约消费方字段授权测试：列级授权、同名冲突、越权拒绝与分区交付。

场景对应业务题面：
- 两份契约分别约定售后订阅者读取 ticket_no、财务订阅者读取 ticket_no + invoice_total；
- 资产交接当日同名字段重新发布为新版本，两个消费方把同名 ticket_no 用于不同字段；
- 发数人员处理授权冲突并追溯已发出的旧版分区；
- 越权申请按资产和签署版本拒绝，历史凭据不能授予新列；
- 负责人管理校验签署时的资产指派，核验结果回写交付清单；
- 两次取数（旧分区/新分区）核对字段清单，财务独有金额不泄到售后清单。
"""
import app.store as store_mod
from app.services.owner_mgr import OwnerMgrService
from app.services.field_catalog import FieldCatalogService
from app.services.data_contract import DataContractService
from app.services.contract_grant import ContractGrantService
from app.services.delivery_note import DeliveryNoteService


def _fresh():
    store_mod.store.reset()
    return {
        "owner": OwnerMgrService(),
        "catalog": FieldCatalogService(),
        "contract": DataContractService(),
        "grant": ContractGrantService(),
        "delivery": DeliveryNoteService(),
    }


def _setup_asset(s, asset_code):
    """准备：负责人指派 + 两份签署契约 + 交接前字段 v1 + 旧分区登记。"""
    s["owner"].assign_owner(asset_code, "数据负责人", "张三", backup="李四")
    after_contract = s["contract"].define_contract(
        asset_code, {"summary": "ticket_no"}, "99.9%可用性", "每日更新",
        "张三", "售后订阅者", signed_fields=["ticket_no"],
    )["contract"]
    finance_contract = s["contract"].define_contract(
        asset_code, {"summary": "ticket_no,invoice_total"}, "99.5%可用性", "每日更新",
        "张三", "财务订阅者", signed_fields=["ticket_no", "invoice_total"],
    )["contract"]

    ticket_v1 = s["catalog"].publish_field(asset_code, "ticket_no", "string", "工单号")
    invoice_v1 = s["catalog"].publish_field(asset_code, "invoice_total", "decimal", "发票金额")

    old_partition = s["delivery"].register_partition(
        asset_code, f"{asset_code}-pt-old",
        {"ticket_no": "v1", "invoice_total": "v1"},
        partition_type="旧分区", owner="张三",
    )
    return {
        "after_contract": after_contract,
        "finance_contract": finance_contract,
        "ticket_v1": ticket_v1,
        "invoice_v1": invoice_v1,
        "old_partition": old_partition,
    }


# ── 签署版本与负责人指派核验 ──────────────────────────────────────

class TestContractSignedVersionAndOwnerCheck:

    def test_contracts_get_distinct_signed_versions(self):
        s = _fresh()
        setup = _setup_asset(s, "ORD-V1")
        assert setup["after_contract"]["签署版本"] == "v1.0"
        assert setup["finance_contract"]["签署版本"] == "v2.0"
        assert setup["after_contract"]["签约字段"] == ["ticket_no"]
        assert setup["finance_contract"]["签约字段"] == ["ticket_no", "invoice_total"]

    def test_signed_contract_carries_owner_verification(self):
        s = _fresh()
        setup = _setup_asset(s, "ORD-V2")
        check = setup["after_contract"]["负责人核验"]
        assert check == "通过"
        assert "张三" in setup["after_contract"]["核验说明"]

    def test_owner_check_fails_when_no_assignment(self):
        s = _fresh()
        result = s["owner"].verify_asset_assignment("ORD-NO-OWNER")
        assert result["passed"] is False
        contract = s["contract"].define_contract(
            "ORD-NO-OWNER", {"summary": "ticket_no"}, "SLA", "每日",
            "张三", "售后订阅者", signed_fields=["ticket_no"],
        )
        assert contract["contract"]["负责人核验"] == "未通过"
        assert contract["owner_check"]["passed"] is False

    def test_expired_assignment_fails_verification(self):
        s = _fresh()
        assignment = s["owner"].assign_owner("ORD-EXPIRED", "数据负责人", "王五")
        s["owner"].mark_expired(assignment["id"])
        result = s["owner"].verify_asset_assignment("ORD-EXPIRED")
        assert result["passed"] is False


# ── 列级授权：按签署版本把声明关联到实际字段 ──────────────────────

class TestColumnLevelGrant:

    def test_grant_binds_signed_field_to_actual_field_version(self):
        s = _fresh()
        setup = _setup_asset(s, "ORD-G1")
        result = s["grant"].grant_field(
            setup["after_contract"]["id"], "售后订阅者", "ticket_no"
        )
        assert result["ok"] is True
        grant = result["grant"]
        assert grant["字段标识"] == "ORD-G1.ticket_no@v1"
        assert grant["字段版本"] == "v1"
        assert grant["签署版本"] == "v1.0"
        assert "CONT" in grant["契约编号"]
        assert grant["status"] == "已授权"

    def test_finance_grant_covers_ticket_and_amount(self):
        s = _fresh()
        setup = _setup_asset(s, "ORD-G2")
        for field in ("ticket_no", "invoice_total"):
            result = s["grant"].grant_field(
                setup["finance_contract"]["id"], "财务订阅者", field
            )
            assert result["ok"] is True
        columns = s["grant"].readable_columns("ORD-G2", "财务订阅者")
        names = {col["字段名称"] for col in columns}
        assert names == {"ticket_no", "invoice_total"}

    def test_unsigned_field_rejected_by_asset_and_signed_version(self):
        s = _fresh()
        setup = _setup_asset(s, "ORD-G3")
        # 售后契约 v1.0 只声明 ticket_no，invoice_total 属于越权申请。
        result = s["grant"].grant_field(
            setup["after_contract"]["id"], "售后订阅者", "invoice_total"
        )
        assert result["ok"] is False
        assert result["grant"]["status"] == "已拒绝"
        assert "签署版本v1.0" in result["reason"]
        # 拒绝留痕不产生可读列。
        assert s["grant"].readable_columns("ORD-G3", "售后订阅者") == []

    def test_other_consumer_credential_cannot_grant_new_column(self):
        s = _fresh()
        setup = _setup_asset(s, "ORD-G4")
        # 售后订阅者拿财务契约（v2.0）的凭据申请金额列，必须被拒绝。
        result = s["grant"].grant_field(
            setup["finance_contract"]["id"], "售后订阅者", "invoice_total"
        )
        assert result["ok"] is False
        assert "消费方" in result["reason"] and "不符" in result["reason"]
        assert result["grant"]["status"] == "已拒绝"

    def test_unsigned_contract_and_unknown_asset_rejected(self):
        s = _fresh()
        setup = _setup_asset(s, "ORD-G5")
        # 不存在的契约。
        result = s["grant"].grant_field(9999, "售后订阅者", "ticket_no")
        assert result["ok"] is False
        # 契约终止后再申请。
        s["contract"].run_action(setup["after_contract"]["id"], "终止契约")
        result = s["grant"].grant_field(
            setup["after_contract"]["id"], "售后订阅者", "ticket_no"
        )
        assert result["ok"] is False
        assert "未签署" in result["reason"]

    def test_duplicate_grant_is_idempotent(self):
        s = _fresh()
        setup = _setup_asset(s, "ORD-G7")
        first = s["grant"].grant_field(
            setup["after_contract"]["id"], "售后订阅者", "ticket_no"
        )
        second = s["grant"].grant_field(
            setup["after_contract"]["id"], "售后订阅者", "ticket_no"
        )
        assert first["grant"]["id"] == second["grant"]["id"]
        assert second.get("duplicated") is True
        columns = s["grant"].readable_columns("ORD-G7", "售后订阅者")
        assert len(columns) == 1

    def test_grant_requires_published_field(self):
        s = _fresh()
        store_mod.store.reset()
        s["owner"].assign_owner("ORD-G6", "数据负责人", "张三")
        contract = s["contract"].define_contract(
            "ORD-G6", {"summary": "ticket_no"}, "SLA", "每日",
            "张三", "售后订阅者", signed_fields=["ticket_no"],
        )["contract"]
        result = s["grant"].grant_field(contract["id"], "售后订阅者", "ticket_no")
        assert result["ok"] is False
        assert "未发布字段" in result["reason"]


# ── 同名新列与授权冲突 ────────────────────────────────────────────

class TestSameNameFieldConflict:

    def _grant_before_handover(self, s, asset, setup):
        s["grant"].grant_field(setup["after_contract"]["id"], "售后订阅者", "ticket_no")
        s["grant"].grant_field(setup["finance_contract"]["id"], "财务订阅者", "ticket_no")
        s["grant"].grant_field(setup["finance_contract"]["id"], "财务订阅者", "invoice_total")

    def test_republish_same_name_creates_new_field_version(self):
        s = _fresh()
        setup = _setup_asset(s, "ORD-C1")
        new_ticket = s["catalog"].publish_field("ORD-C1", "ticket_no", "string", "工单号-新口径")
        assert new_ticket["字段版本"] == "v2"
        assert new_ticket["字段标识"] == "ORD-C1.ticket_no@v2"
        versions = s["catalog"].list_field_versions("ORD-C1", "ticket_no")
        assert [row["字段版本"] for row in versions] == ["v1", "v2"]

    def test_same_name_bound_to_different_fields_raises_conflict(self):
        s = _fresh()
        setup = _setup_asset(s, "ORD-C2")
        self._grant_before_handover(s, "ORD-C2", setup)
        # 交接后重新发布同名 ticket_no（v2 是与 v1 不同的字段）。
        s["catalog"].publish_field("ORD-C2", "ticket_no", "string", "工单号-新口径")
        # 售后订阅者重新签署/按新分区把 ticket_no 绑到 v2；财务仍持有 v1。
        result = s["grant"].grant_field(
            setup["after_contract"]["id"], "售后订阅者", "ticket_no",
            field_version="v2",
        )
        assert result["ok"] is True
        assert result["conflict"] is True
        conflict_rows = s["grant"].detect_conflicts("ORD-C2")
        assert len(conflict_rows) == 1
        assert conflict_rows[0]["消费方"] == "售后订阅者"
        assert conflict_rows[0]["冲突授权编号"]

    def test_conflict_resolution_keep_old_version(self):
        s = _fresh()
        setup = _setup_asset(s, "ORD-C3")
        self._grant_before_handover(s, "ORD-C3", setup)
        s["catalog"].publish_field("ORD-C3", "ticket_no", "string", "工单号-新口径")
        conflict = s["grant"].grant_field(
            setup["after_contract"]["id"], "售后订阅者", "ticket_no", field_version="v2"
        )
        resolved = s["grant"].resolve_conflict(conflict["grant"]["id"], "保留原版本")
        assert resolved["ok"] is True
        assert resolved["grant"]["status"] == "已授权"
        assert resolved["grant"]["字段标识"] == "ORD-C3.ticket_no@v2"
        assert s["grant"].detect_conflicts("ORD-C3") == []

    def test_conflict_resolution_switch_to_latest(self):
        s = _fresh()
        setup = _setup_asset(s, "ORD-C4")
        self._grant_before_handover(s, "ORD-C4", setup)
        s["catalog"].publish_field("ORD-C4", "ticket_no", "string", "工单号-新口径")
        # 财务保持 v1，售后冲突行改绑最新版本。
        conflict = s["grant"].grant_field(
            setup["after_contract"]["id"], "售后订阅者", "ticket_no", field_version="v2"
        )
        resolved = s["grant"].resolve_conflict(conflict["grant"]["id"], "切换新版本")
        assert resolved["grant"]["字段版本"] == "v2"
        finance_cols = s["grant"].readable_columns("ORD-C4", "财务订阅者")
        finance_ticket = next(c for c in finance_cols if c["字段名称"] == "ticket_no")
        assert finance_ticket["字段版本"] == "v1"

    def test_conflict_resolution_revoke(self):
        s = _fresh()
        setup = _setup_asset(s, "ORD-C5")
        self._grant_before_handover(s, "ORD-C5", setup)
        s["catalog"].publish_field("ORD-C5", "ticket_no", "string", "工单号-新口径")
        conflict = s["grant"].grant_field(
            setup["after_contract"]["id"], "售后订阅者", "ticket_no", field_version="v2"
        )
        resolved = s["grant"].resolve_conflict(conflict["grant"]["id"], "撤回授权")
        assert resolved["grant"]["status"] == "已解除"
        # 撤回后追溯仍能看到这条历史凭据。
        trace = s["grant"].trace_grants("ORD-C5", "售后订阅者")
        assert any(row["status"] == "已解除" for row in trace)


# ── 分区领取：两次取数字段清单与金额隔离 ──────────────────────────

class TestPartitionDelivery:

    def _handover_and_grants(self, s, asset, setup):
        # 交接前：售后 ticket_no@v1；财务 ticket_no@v1 + invoice_total@v1。
        s["grant"].grant_field(setup["after_contract"]["id"], "售后订阅者", "ticket_no")
        s["grant"].grant_field(setup["finance_contract"]["id"], "财务订阅者", "ticket_no")
        s["grant"].grant_field(setup["finance_contract"]["id"], "财务订阅者", "invoice_total")
        # 负责人交接 + 同名新列发布 + 冲突处理（售后切到 v2，财务维持 v1）。
        assignment = s["owner"].get_owners_by_asset(asset)[0]
        s["owner"].handover(assignment["id"], "赵七")
        s["catalog"].publish_field(asset, "ticket_no", "string", "工单号-新口径")
        conflict = s["grant"].grant_field(
            setup["after_contract"]["id"], "售后订阅者", "ticket_no", field_version="v2"
        )
        s["grant"].resolve_conflict(conflict["grant"]["id"], "切换新版本")
        s["delivery"].register_partition(
            asset, f"{asset}-pt-new",
            {"ticket_no": "v2", "invoice_total": "v1"},
            partition_type="新分区", owner="赵七",
        )

    def test_old_partition_after_sales_only_reads_ticket_v1(self):
        s = _fresh()
        setup = _setup_asset(s, "ORD-D1")
        self._handover_and_grants(s, "ORD-D1", setup)
        claim = s["delivery"].claim_partition(
            "ORD-D1-pt-old", "售后订阅者", operator="办单员甲"
        )
        assert claim["ok"] is True
        names = [col["字段名称"] for col in claim["readable_columns"]]
        assert names == ["ticket_no"]
        column = claim["readable_columns"][0]
        assert column["字段版本"] == "v1"
        assert column["签署版本"] == "v1.0"
        assert column["契约编号"] == setup["after_contract"]["契约编号"]
        # 财务独有金额不能跟随单号泄到售后清单。
        assert "invoice_total" not in claim["note"]["可读字段"]
        assert claim["note"]["核验结果"] == "核验通过"

    def test_old_partition_finance_reads_ticket_and_amount(self):
        s = _fresh()
        setup = _setup_asset(s, "ORD-D2")
        self._handover_and_grants(s, "ORD-D2", setup)
        claim = s["delivery"].claim_partition("ORD-D2-pt-old", "财务订阅者")
        columns = {col["字段名称"]: col for col in claim["readable_columns"]}
        assert set(columns) == {"ticket_no", "invoice_total"}
        assert columns["ticket_no"]["字段版本"] == "v1"
        assert columns["invoice_total"]["字段版本"] == "v1"
        assert columns["invoice_total"]["签署版本"] == "v2.0"

    def test_new_partition_after_sales_reads_ticket_v2_with_basis(self):
        s = _fresh()
        setup = _setup_asset(s, "ORD-D3")
        self._handover_and_grants(s, "ORD-D3", setup)
        claim = s["delivery"].claim_partition("ORD-D3-pt-new", "售后订阅者")
        assert len(claim["readable_columns"]) == 1
        column = claim["readable_columns"][0]
        assert column["字段名称"] == "ticket_no"
        assert column["字段版本"] == "v2"
        assert column["字段标识"] == "ORD-D3.ticket_no@v2"
        assert "v1.0" in column["授权依据"]
        assert "invoice_total" not in claim["note"]["可读字段"]

    def test_new_partition_finance_ticket_stays_v1_and_amount_kept(self):
        s = _fresh()
        setup = _setup_asset(s, "ORD-D4")
        self._handover_and_grants(s, "ORD-D4", setup)
        claim = s["delivery"].claim_partition("ORD-D4-pt-new", "财务订阅者")
        columns = {col["字段名称"]: col for col in claim["readable_columns"]}
        # 新分区里 ticket_no 已是 v2，财务授权绑定的是 v1，版本不匹配 → 单号不可读；
        # 金额列版本未变，仍然可读，且不会出现在售后清单。
        assert "ticket_no" not in columns
        assert "invoice_total" in columns
        assert columns["invoice_total"]["字段版本"] == "v1"

    def test_two_fetches_field_lists_are_traceable(self):
        s = _fresh()
        setup = _setup_asset(s, "ORD-D5")
        self._handover_and_grants(s, "ORD-D5", setup)
        old_claim = s["delivery"].claim_partition("ORD-D5-pt-old", "售后订阅者")
        new_claim = s["delivery"].claim_partition("ORD-D5-pt-new", "售后订阅者")
        old_names = [c["字段标识"] for c in old_claim["readable_columns"]]
        new_names = [c["字段标识"] for c in new_claim["readable_columns"]]
        assert old_names == ["ORD-D5.ticket_no@v1"]
        assert new_names == ["ORD-D5.ticket_no@v2"]
        # 旧版分区在交付清单中可追溯。
        traced = s["delivery"].trace_partitions("ORD-D5")
        codes = {note["分区编号"] for note in traced}
        assert {"ORD-D5-pt-old", "ORD-D5-pt-new"} <= codes

    def test_delivery_note_records_owner_verification(self):
        s = _fresh()
        setup = _setup_asset(s, "ORD-D6")
        s["grant"].grant_field(setup["after_contract"]["id"], "售后订阅者", "ticket_no")
        claim = s["delivery"].claim_partition("ORD-D6-pt-old", "售后订阅者")
        assert claim["owner_check"]["passed"] is True
        assert "负责人指派核验：" in claim["note"]["核验说明"]

    def test_claim_unknown_partition_rejected(self):
        s = _fresh()
        result = s["delivery"].claim_partition("NOT-EXIST-PT", "售后订阅者")
        assert result["ok"] is False
