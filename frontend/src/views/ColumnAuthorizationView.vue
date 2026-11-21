<template>
  <section class="page column-auth-page">
    <header class="page-head">
      <div>
        <h2>契约消费方字段授权工作台</h2>
        <p class="page-desc">
          按签署版本把消费方字段声明关联到实际字段版本，处理同名授权冲突，
          领取旧/新分区时回写消费方实际可读列与契约签署依据。
        </p>
      </div>
    </header>

    <form class="filter-bar" @submit.prevent="loadAll">
      <label class="filter-item">
        <span>数据资产编号</span>
        <input v-model="assetCode" data-testid="asset-input" placeholder="如 ORD-001" required />
      </label>
      <button class="btn primary" data-testid="load-asset" type="submit">载入资产</button>
      <span v-if="ownerCheckResult" :class="ownerCheckResult.passed ? 'ok-text' : 'error-text'">
        负责人核验：{{ ownerCheckResult.passed ? '通过' : '未通过' }}（{{ ownerCheckResult.detail }}）
      </span>
    </form>

    <div class="auth-grid">
      <!-- 1. 负责人指派与交接 -->
      <article class="auth-card">
        <h3>① 负责人指派 / 交接</h3>
        <form class="inline-form" @submit.prevent="onAssignOwner">
          <input v-model="ownerForm.owner" placeholder="责任人" data-testid="owner-name" required />
          <input v-model="ownerForm.backup" placeholder="备份人（可选）" />
          <button class="btn" type="submit">指派负责人</button>
        </form>
        <table class="data-table mini">
          <thead><tr><th>指派编号</th><th>责任人</th><th>状态</th><th>交接</th></tr></thead>
          <tbody>
            <tr v-for="row in ownerRows" :key="row.id">
              <td>{{ row.指派编号 }}</td>
              <td>{{ row.责任人 }}</td>
              <td>{{ row.status }}</td>
              <td>
                <button class="link" type="button" @click="onHandover(row.id)">交接给赵七</button>
              </td>
            </tr>
            <tr v-if="!ownerRows.length"><td colspan="4" class="empty-state">暂无指派</td></tr>
          </tbody>
        </table>
      </article>

      <!-- 2. 字段目录与字段版本 -->
      <article class="auth-card">
        <h3>② 字段发布（同名再发布生成新版本）</h3>
        <form class="inline-form" @submit.prevent="onPublishField">
          <input v-model="fieldForm.name" placeholder="字段名，如 ticket_no" data-testid="field-name" required />
          <select v-model="fieldForm.type">
            <option value="string">string</option>
            <option value="decimal">decimal</option>
            <option value="bigint">bigint</option>
          </select>
          <input v-model="fieldForm.meaning" placeholder="业务含义" />
          <button class="btn" type="submit">发布字段</button>
        </form>
        <table class="data-table mini">
          <thead><tr><th>字段标识</th><th>类型</th><th>含义</th><th>状态</th></tr></thead>
          <tbody>
            <tr v-for="row in fieldRows" :key="row.id">
              <td>{{ row.字段标识 }}</td>
              <td>{{ row.字段类型 }}</td>
              <td>{{ row.业务含义 || '—' }}</td>
              <td>{{ row.status }}</td>
            </tr>
            <tr v-if="!fieldRows.length"><td colspan="4" class="empty-state">暂无字段版本</td></tr>
          </tbody>
        </table>
      </article>

      <!-- 3. 契约签署版本 -->
      <article class="auth-card">
        <h3>③ 契约签署（按版本声明消费方可读字段）</h3>
        <form class="inline-form" @submit.prevent="onSignContract">
          <input v-model="contractForm.consumer" placeholder="消费方，如 售后订阅者"
                 data-testid="contract-consumer" required />
          <input v-model="contractForm.fields" placeholder="声明字段，逗号分隔，如 ticket_no"
                 data-testid="contract-fields" required />
          <button class="btn" type="submit">签署契约</button>
        </form>
        <table class="data-table mini">
          <thead><tr><th>契约编号</th><th>签署版本</th><th>消费方</th><th>签约字段</th><th>负责人核验</th></tr></thead>
          <tbody>
            <tr v-for="row in contractRows" :key="row.id">
              <td>{{ row.契约编号 }}</td>
              <td>{{ row.签署版本 }}</td>
              <td>{{ row.消费方 }}</td>
              <td>{{ (row.签约字段 || []).join(',') }}</td>
              <td>{{ row.负责人核验 }}</td>
            </tr>
            <tr v-if="!contractRows.length"><td colspan="5" class="empty-state">暂无签署版本</td></tr>
          </tbody>
        </table>
      </article>

      <!-- 4. 列级授权申请 -->
      <article class="auth-card">
        <h3>④ 列级授权申请（越权按资产+签署版本拒绝）</h3>
        <form class="inline-form" @submit.prevent="onGrant">
          <select v-model.number="grantForm.contractId" data-testid="grant-contract" required>
            <option :value="0" disabled>选择契约签署版本</option>
            <option v-for="row in contractRows" :key="row.id" :value="row.id">
              {{ row.契约编号 }} {{ row.签署版本 }} · {{ row.消费方 }}
            </option>
          </select>
          <input v-model="grantForm.consumer" placeholder="申请消费方" data-testid="grant-consumer" required />
          <input v-model="grantForm.field" placeholder="申请字段名" data-testid="grant-field" required />
          <input v-model="grantForm.version" placeholder="字段版本（可选，如 v2）" />
          <button class="btn primary" type="submit">提交授权</button>
        </form>
        <p v-if="grantMessage" :class="grantOk ? 'ok-text' : 'error-text'">{{ grantMessage }}</p>
      </article>

      <!-- 5. 授权冲突处理 -->
      <article class="auth-card">
        <h3>⑤ 同名异字段授权冲突处理</h3>
        <button class="btn ghost" type="button" @click="loadConflicts">刷新冲突</button>
        <table class="data-table mini">
          <thead><tr><th>授权编号</th><th>消费方</th><th>字段</th><th>冲突说明</th><th>处理</th></tr></thead>
          <tbody>
            <tr v-for="row in conflictRows" :key="row.id">
              <td>{{ row.授权编号 }}</td>
              <td>{{ row.消费方 }}</td>
              <td>{{ row.字段标识 }}</td>
              <td>{{ row.冲突说明 }}</td>
              <td class="row-actions">
                <button class="link" type="button" @click="onResolve(row.id, '保留原版本')">保留原版本</button>
                <button class="link" type="button" @click="onResolve(row.id, '切换新版本')">切换新版本</button>
                <button class="link" type="button" @click="onResolve(row.id, '撤回授权')">撤回</button>
              </td>
            </tr>
            <tr v-if="!conflictRows.length"><td colspan="5" class="empty-state">无待处理冲突</td></tr>
          </tbody>
        </table>
      </article>

      <!-- 6. 分区登记与领取 -->
      <article class="auth-card wide">
        <h3>⑥ 分区登记 / 领取（按字段版本回写可读列）</h3>
        <form class="inline-form" @submit.prevent="onRegisterPartition">
          <input v-model="partitionForm.code" placeholder="分区编号，如 P-OLD"
                 data-testid="partition-code" required />
          <select v-model="partitionForm.type">
            <option>旧分区</option>
            <option>新分区</option>
          </select>
          <input v-model="partitionForm.versions"
                 placeholder="分区字段版本，如 ticket_no:v1,invoice_total:v1"
                 data-testid="partition-versions" required />
          <button class="btn" type="submit">登记分区</button>
        </form>
        <form class="inline-form" @submit.prevent="onClaim">
          <input v-model="claimForm.partition" placeholder="领取分区编号" data-testid="claim-partition" required />
          <input v-model="claimForm.consumer" placeholder="领取消费方" data-testid="claim-consumer" required />
          <input v-model="claimForm.operator" placeholder="办单人员" />
          <button class="btn primary" type="submit">领取并核验</button>
        </form>
        <div v-if="lastClaim" class="claim-result" data-testid="claim-result">
          <p :class="lastClaim.ok ? 'ok-text' : 'error-text'">
            {{ lastClaim.partition_code }}（{{ lastClaim.partition_type }}）交付给
            {{ lastClaim.consumer }}：可读 {{ lastClaim.readable_columns.length }} 列；
            负责人核验 {{ lastClaim.owner_check.passed ? '通过' : '未过' }}
          </p>
          <table class="data-table mini">
            <thead><tr><th>可读字段</th><th>字段版本</th><th>字段标识</th><th>签署依据</th></tr></thead>
            <tbody>
              <tr v-for="col in lastClaim.readable_columns" :key="col.字段标识">
                <td>{{ col.字段名称 }}</td>
                <td>{{ col.字段版本 }}</td>
                <td>{{ col.字段标识 }}</td>
                <td>{{ col.授权依据 }}</td>
              </tr>
              <tr v-if="!lastClaim.readable_columns.length">
                <td colspan="4" class="empty-state">该消费方在此分区无匹配授权的可读列</td>
              </tr>
            </tbody>
          </table>
        </div>
      </article>

      <!-- 7. 授权与分区追溯 -->
      <article class="auth-card wide">
        <h3>⑦ 授权与旧版分区追溯</h3>
        <div class="row-actions">
          <button class="btn" type="button" @click="loadGrantTrace">追溯全部授权凭据</button>
          <button class="btn" type="button" @click="loadPartitions">追溯已交付分区</button>
        </div>
        <table v-if="grantTrace.length" class="data-table mini">
          <thead><tr><th>授权编号</th><th>消费方</th><th>字段标识</th><th>签署版本</th><th>状态</th><th>依据/原因</th></tr></thead>
          <tbody>
            <tr v-for="row in grantTrace" :key="row.id">
              <td>{{ row.授权编号 }}</td>
              <td>{{ row.消费方 }}</td>
              <td>{{ row.字段标识 || '—' }}</td>
              <td>{{ row.签署版本 || '—' }}</td>
              <td>{{ row.status }}</td>
              <td>{{ row.拒绝原因 || row.授权依据 || row.处理结论 }}</td>
            </tr>
          </tbody>
        </table>
        <table v-if="partitionRows.length" class="data-table mini">
          <thead><tr><th>清单编号</th><th>分区</th><th>类型</th><th>消费方</th><th>可读字段</th><th>核验结果</th><th>负责人</th></tr></thead>
          <tbody>
            <tr v-for="row in partitionRows" :key="row.id">
              <td>{{ row.清单编号 }}</td>
              <td>{{ row.分区编号 }}</td>
              <td>{{ row.分区类型 }}</td>
              <td>{{ row.消费方 || '—' }}</td>
              <td>{{ row.可读字段 || '—' }}</td>
              <td>{{ row.核验结果 }}</td>
              <td>{{ row.负责人 }}</td>
            </tr>
          </tbody>
        </table>
      </article>
    </div>

    <footer class="page-foot">
      <span v-if="message" :class="messageOk ? 'ok-text' : 'error-text'">{{ message }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { listEntries } from '@/api/backend-service'
import {
  assignOwner,
  claimPartition,
  grantField,
  handoverOwner,
  listConflicts,
  listContractVersions,
  ownerCheck,
  publishField,
  registerPartition,
  resolveConflict,
  signContract,
  traceGrants,
  tracePartitions,
} from '@/api/column-authorization'
import type {
  ClaimResult,
  ContractVersion,
  DeliveryRow,
  FieldVersion,
  GrantRow,
} from '@/api/column-authorization'

const assetCode = ref('ORD-001')
const message = ref('')
const messageOk = ref(true)

const ownerRows = ref<EntryRowLite[]>([])
const fieldRows = ref<FieldVersion[]>([])
const contractRows = ref<ContractVersion[]>([])
const conflictRows = ref<GrantRow[]>([])
const grantTrace = ref<GrantRow[]>([])
const partitionRows = ref<DeliveryRow[]>([])
const ownerCheckResult = ref<{ passed: boolean; detail: string } | null>(null)
const lastClaim = ref<ClaimResult | null>(null)

const ownerForm = ref({ owner: '', backup: '' })
const fieldForm = ref({ name: '', type: 'string', meaning: '' })
const contractForm = ref({ consumer: '', fields: '' })
const grantForm = ref({ contractId: 0, consumer: '', field: '', version: '' })
const grantMessage = ref('')
const grantOk = ref(true)
const partitionForm = ref({ code: '', type: '旧分区', versions: '' })
const claimForm = ref({ partition: '', consumer: '', operator: '' })

type EntryRowLite = { id: number; 指派编号: string; 责任人: string; status: string }

function notify(text: string, ok = true) {
  message.value = text
  messageOk.value = ok
}

function parseVersions(raw: string): Record<string, string> {
  const result: Record<string, string> = {}
  raw.split(/[,，]/).map((part) => part.trim()).filter(Boolean).forEach((part) => {
    const [name, version] = part.split(':').map((item) => item.trim())
    if (name && version) result[name] = version
  })
  return result
}

async function loadAll() {
  if (!assetCode.value.trim()) return
  try {
    const [owners, fields, contracts, check] = await Promise.all([
      listEntries('owner_mgr', { 目标资产: assetCode.value }),
      listEntries('field_catalog', { 所属资产: assetCode.value }),
      listContractVersions(assetCode.value),
      ownerCheck(assetCode.value),
    ])
    ownerRows.value = owners.items as unknown as EntryRowLite[]
    fieldRows.value = fields.items as unknown as FieldVersion[]
    contractRows.value = contracts.items
    ownerCheckResult.value = check
    await loadConflicts()
    await loadPartitions()
    notify('资产数据已载入')
  } catch (error) {
    notify(error instanceof Error ? error.message : '载入失败', false)
  }
}

async function onAssignOwner() {
  await assignOwner({ asset_code: assetCode.value, owner: ownerForm.value.owner, backup: ownerForm.value.backup })
  notify('负责人已指派')
  await loadAll()
}

async function onHandover(assignmentId: number) {
  await handoverOwner(assignmentId, '赵七')
  notify('负责人交接已发起')
  await loadAll()
}

async function onPublishField() {
  await publishField({
    asset_code: assetCode.value,
    field_name: fieldForm.value.name,
    field_type: fieldForm.value.type,
    biz_meaning: fieldForm.value.meaning,
  })
  notify(`字段 ${fieldForm.value.name} 已发布`)
  await loadAll()
}

async function onSignContract() {
  const signedFields = contractForm.value.fields.split(/[,，]/).map((item) => item.trim()).filter(Boolean)
  const result = await signContract({
    asset_code: assetCode.value,
    consumer: contractForm.value.consumer,
    signed_fields: signedFields,
  })
  notify(`契约 ${result.contract.契约编号} 已签署（${result.contract.签署版本}），负责人核验：${result.contract.负责人核验}`)
  await loadAll()
}

async function onGrant() {
  try {
    const result = await grantField({
      contract_id: grantForm.value.contractId,
      consumer: grantForm.value.consumer,
      field_name: grantForm.value.field,
      field_version: grantForm.value.version || undefined,
    })
    grantOk.value = result.ok
    if (result.ok) {
      grantMessage.value = result.conflict
        ? `授权已登记但存在同名冲突：${result.grant.冲突说明}`
        : `授权通过：${result.grant.字段标识}`
    } else {
      grantMessage.value = `越权拒绝：${result.reason}`
    }
    await loadConflicts()
    await loadGrantTrace()
  } catch (error) {
    grantOk.value = false
    grantMessage.value = error instanceof Error ? error.message : '授权申请失败'
  }
}

async function loadConflicts() {
  const result = await listConflicts(assetCode.value)
  conflictRows.value = result.items
}

async function onResolve(grantId: number, resolution: string) {
  const result = await resolveConflict(grantId, resolution)
  notify(result.message, result.ok)
  await loadConflicts()
  await loadGrantTrace()
}

async function loadGrantTrace() {
  const result = await traceGrants(assetCode.value)
  grantTrace.value = result.items
}

async function onRegisterPartition() {
  await registerPartition({
    asset_code: assetCode.value,
    partition_code: partitionForm.value.code,
    field_versions: parseVersions(partitionForm.value.versions),
    partition_type: partitionForm.value.type,
  })
  notify(`分区 ${partitionForm.value.code} 已登记`)
  await loadPartitions()
}

async function onClaim() {
  lastClaim.value = await claimPartition(
    claimForm.value.partition,
    claimForm.value.consumer,
    claimForm.value.operator,
  )
  notify(lastClaim.value.ok ? '分区领取核验通过' : '分区领取核验未过', lastClaim.value.ok)
  await loadPartitions()
}

async function loadPartitions() {
  const result = await tracePartitions(assetCode.value)
  partitionRows.value = result.items
}

onMounted(loadAll)
</script>

<style scoped>
.auth-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}
.auth-card {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px 14px;
}
.auth-card.wide {
  grid-column: 1 / -1;
}
.auth-card h3 {
  margin: 0 0 10px;
  font-size: 14px;
}
.inline-form {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 10px;
}
.inline-form input,
.inline-form select {
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 6px 8px;
  min-width: 120px;
}
.data-table.mini th,
.data-table.mini td {
  padding: 6px 8px;
  font-size: 12px;
}
.ok-text {
  color: #067647;
}
.claim-result {
  margin-top: 10px;
  border-top: 1px dashed var(--border);
  padding-top: 10px;
}
@media (max-width: 1100px) {
  .auth-grid {
    grid-template-columns: 1fr;
  }
}
</style>
