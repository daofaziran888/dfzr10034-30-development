<template>
  <div class="app-shell">
    <aside class="app-side">
      <h1 class="app-title">治数工坊 · 数据治理与生命周期管理平台</h1>
      <nav class="nav-list">
        <RouterLink v-for="item in navItems" :key="item.path" :to="item.path" class="nav-item">
          {{ item.label }}
        </RouterLink>
      </nav>
    </aside>    <main class="app-main">
      <header class="app-head">
        <span class="head-desc">面向资产注册、元数据索引与搜索、质量规则引擎、数据画像与分级、脱敏与操作日志、生命周期策略、冷热归档、血缘追踪、影响分析、变更捕获与契约治理的数据治理与生命周期管理平台。</span>
        <span class="head-user">当前值班：数据工程组</span>
      </header>
      <RouterView />
    </main>
  </div>
</template>

<script setup lang="ts">
const navItems = [{ label: "运营概览", path: "/" }, { label: "列级授权工作台", path: "/column-authorization" }, { label: "资产注册", path: "/asset_registry" }, { label: "元数据索引", path: "/metadata_index" }, { label: "质量规则", path: "/quality_rule" }, { label: "数据画像", path: "/profile_stats" }, { label: "数据分级", path: "/classification" }, { label: "生命周期", path: "/lifecycle_policy" }, { label: "冷热归档", path: "/cold_archive" }, { label: "保留清理", path: "/retention_job" }, { label: "脱敏引擎", path: "/data_anonym" }, { label: "操作日志", path: "/operation_log" }, { label: "变更捕获", path: "/change_capture" }, { label: "血缘追踪", path: "/lineage_track" }, { label: "影响分析", path: "/impact_analysis" }, { label: "标签体系", path: "/tag_registry" }, { label: "治理评分", path: "/govern_score" }, { label: "数据契约", path: "/data_contract" }, { label: "消费方字段授权", path: "/contract_grant" }, { label: "字段目录", path: "/field_catalog" }, { label: "交付清单", path: "/delivery_note" }, { label: "合规扫描", path: "/compliance_scan" }, { label: "问题追踪", path: "/issue_track" }, { label: "版本履历", path: "/version_history" }, { label: "调度治理", path: "/schedule_job" }, { label: "差异报告", path: "/diff_report" }, { label: "负责人管理", path: "/owner_mgr" }]
</script>
