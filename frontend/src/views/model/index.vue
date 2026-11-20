<template>
  <section class="page" data-module="model">
    <header class="page-head">
      <div>
        <h2>分析模型管理</h2>
        <p class="page-desc">维护模型配置，并在同一评估集上汇入逐样本结果，核对混淆计数、分组命中率与人工复核清单。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记模型配置</button>
        <button class="btn" type="button" @click="exportRows">导出分析模型清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td class="row-actions">
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
            <button class="link" type="button" @click="focusEvaluation(String(row['模型编号']))">
              评估结果
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无分析模型数据，可先登记模型配置</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条分析模型记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <section ref="evalPanel" class="eval-panel">
      <header class="panel-head">
        <div>
          <h3>模型评估结果数据集</h3>
          <p class="panel-desc">
            同一评估集内的每个模型版本都按样本编号登记真实分类与预测分类；预测留空即弃答，弃答计入覆盖率分母但不计为正确。
          </p>
        </div>
        <div class="panel-actions">
          <label class="inline-field">
            <span>评估批次</span>
            <select v-model.number="selectedBatchId" @change="loadBatch">
              <option v-for="batch in batches" :key="batch.id" :value="batch.id">
                {{ batch.批次编号 }} · {{ batch.评估集名称 }}
              </option>
            </select>
          </label>
          <button class="btn primary" type="button" :disabled="!selectedBatchId" @click="openImport">
            汇入评估结果
          </button>
          <button class="btn" type="button" :disabled="!selectedBatchId" @click="loadBatch">刷新</button>
        </div>
      </header>

      <p v-if="!selectedBatchId" class="empty-state">暂无可用的评估批次</p>

      <template v-else>
        <div class="stat-row">
          <article v-for="card in evalStats" :key="card.label" class="stat-card">
            <span class="stat-label">{{ card.label }}</span>
            <strong class="stat-value">{{ card.value }}</strong>
          </article>
        </div>

        <div class="panel-grid">
          <div>
            <h4 class="sub-head">各版本覆盖与正确答复</h4>
            <table class="data-table compact">
              <thead>
                <tr>
                  <th>模型版本</th>
                  <th>样本总数</th>
                  <th>已作答</th>
                  <th>弃答</th>
                  <th>覆盖率</th>
                  <th>命中率</th>
                  <th>正确响应占比</th>
                  <th>待复核</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="version in versions"
                  :key="`${version.模型编号}-${version.模型版本}`"
                  :class="{ selected: isSelectedVersion(version) }"
                  @click="selectVersion(version)"
                >
                  <td>{{ version.模型编号 }} {{ version.模型版本 }}</td>
                  <td>{{ version.样本总数 }}</td>
                  <td>{{ version.已作答 }}</td>
                  <td>{{ version.弃答 }}</td>
                  <td>{{ formatRatio(version.覆盖率) }}</td>
                  <td>{{ formatRatio(version.命中率) }}</td>
                  <td>{{ formatRatio(version.正确响应占比) }}</td>
                  <td>{{ version.人工复核 }}</td>
                </tr>
                <tr v-if="!versions.length">
                  <td colspan="8" class="empty-state">该批次尚未汇入任何模型版本的结果</td>
                </tr>
              </tbody>
            </table>
            <p class="hint-text">
              命中率 = 正确数 / 已作答；正确响应占比 = 正确数 / 评估集样本总数，弃答计入分母且不算正确。
            </p>
          </div>

          <div>
            <h4 class="sub-head">
              版本明细
              <span v-if="selectedVersion" class="sub-note">
                {{ selectedVersion.模型编号 }} {{ selectedVersion.模型版本 }} · {{ selectedVersion.评估批次 }}
              </span>
            </h4>
            <template v-if="versionDetail">
              <div class="metric-line">
                <span>已作答 {{ versionDetail.已作答 }}</span>
                <span>弃答 {{ versionDetail.弃答 }}</span>
                <span>正确 {{ versionDetail.正确 }}</span>
                <span>错误 {{ versionDetail.错误 }}</span>
              </div>
              <p class="hint-text">{{ versionDetail.混淆分母 }}</p>
              <table class="data-table compact">
                <thead>
                  <tr>
                    <th>真实分类</th>
                    <th>预测分布</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(dist, truth) in versionDetail.混淆计数" :key="truth">
                    <td>{{ truth }}</td>
                    <td>
                      <span v-for="(count, pred) in dist" :key="pred" class="tag">
                        {{ pred }}：{{ count }}
                      </span>
                    </td>
                  </tr>
                  <tr v-if="!Object.keys(versionDetail.混淆计数).length">
                    <td colspan="2" class="empty-state">没有已作答样本，混淆计数为空</td>
                  </tr>
                </tbody>
              </table>

              <table class="data-table compact">
                <thead>
                  <tr>
                    <th>样本分组</th>
                    <th>样本总数</th>
                    <th>已作答</th>
                    <th>弃答</th>
                    <th>命中率（已作答分母）</th>
                    <th>正确响应占比（分组分母）</th>
                    <th>少数类别弃答</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="group in versionDetail.分组" :key="group.样本分组">
                    <td>{{ group.样本分组 }}</td>
                    <td>{{ group.样本总数 }}</td>
                    <td>{{ group.已作答 }}</td>
                    <td>{{ group.弃答 }}</td>
                    <td>{{ formatRatio(group.命中率) }}</td>
                    <td>{{ formatRatio(group.正确响应占比) }}</td>
                    <td>{{ group.少数类别弃答.join('、') || '—' }}</td>
                  </tr>
                </tbody>
              </table>
            </template>
            <p v-else class="empty-state">选择一个版本查看混淆计数与分组命中率</p>
          </div>
        </div>

        <h4 class="sub-head">人工应复核样本</h4>
        <div class="metric-line">
          <span>待复核 {{ reviewSummary.待复核总数 }} 条</span>
          <span>弃答 {{ reviewSummary.弃答 }}</span>
          <span>少数类别弃答 {{ reviewSummary.少数类别弃答 }}</span>
          <span>金标人工复核 {{ reviewSummary.金标人工复核 }}</span>
        </div>
        <table class="data-table compact">
          <thead>
            <tr>
              <th>评估批次</th>
              <th>模型版本</th>
              <th>样本编号</th>
              <th>真实分类</th>
              <th>预测分类</th>
              <th>复核原因</th>
              <th>复核结论</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in reviewItems" :key="String(row.id)">
              <td>{{ row.评估批次 }}</td>
              <td>{{ row.模型编号 }} {{ row.模型版本 }}</td>
              <td>{{ row.样本编号 }}</td>
              <td>{{ row.真实分类 }}</td>
              <td>{{ row.预测分类 || '弃答' }}</td>
              <td>{{ row.复核原因 }}</td>
              <td class="row-actions">
                <input v-model="reviewNotes[row.id]" class="mini-input" placeholder="填写复核结论" />
                <button class="link" type="button" @click="submitReview(row)">登记</button>
              </td>
            </tr>
            <tr v-if="!reviewItems.length">
              <td colspan="7" class="empty-state">当前批次没有待人工复核的样本</td>
            </tr>
          </tbody>
        </table>
        <p class="hint-text">
          弃答样本不做「未预测即正确」处理；少数类别指真实分类占比低于 30% 的类别，其弃答会单独计数。
        </p>
      </template>
    </section>

    <Teleport to="body">
      <div v-if="showCreateModal" class="modal-overlay" @click.self="showCreateModal = false">
        <div class="modal-card">
          <header class="modal-head">
            <h3>登记模型配置</h3>
            <button class="btn ghost" type="button" @click="showCreateModal = false">&times;</button>
          </header>
          <form class="modal-body" @submit.prevent="submitCreate">
            <label v-for="field in columns.slice(0, 3)" :key="field" class="modal-field">
              <span>{{ field }}</span>
              <input v-model="createFields[field]" :placeholder="`请输入${field}`" required />
            </label>
            <footer class="modal-foot">
              <button class="btn" type="button" @click="showCreateModal = false">取消</button>
              <button class="btn primary" type="submit">提交登记</button>
            </footer>
          </form>
        </div>
      </div>

      <div v-if="showImportModal" class="modal-overlay" @click.self="showImportModal = false">
        <div class="modal-card wide">
          <header class="modal-head">
            <h3>从评估集汇入结果</h3>
            <button class="btn ghost" type="button" @click="showImportModal = false">&times;</button>
          </header>
          <form class="modal-body" @submit.prevent="submitImport">
            <div class="form-row">
              <label class="modal-field">
                <span>评估批次</span>
                <input :value="importBatchCode" disabled />
              </label>
              <label class="modal-field">
                <span>模型编号</span>
                <input v-model="importForm.model" placeholder="如 MODE-0001" required />
              </label>
              <label class="modal-field">
                <span>模型版本</span>
                <input v-model="importForm.version" placeholder="如 v1.2" required />
              </label>
            </div>
            <p class="hint-text">
              评估集共 {{ importSamples.length }} 个样本。真实分类由评估集带出；预测分类留空表示模型弃答，仍需逐条登记。
            </p>
            <table class="data-table compact">
              <thead>
                <tr>
                  <th>样本编号</th>
                  <th>样本分组</th>
                  <th>真实分类</th>
                  <th>预测分类</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="sample in importSamples" :key="sample.样本编号">
                  <td>{{ sample.样本编号 }}</td>
                  <td>{{ sample.样本分组 }}</td>
                  <td>{{ sample.真实分类 }}</td>
                  <td>
                    <input
                      v-model="importForm.predictions[sample.样本编号]"
                      class="mini-input"
                      placeholder="留空 = 弃答"
                      :list="`classes-${selectedBatchId}`"
                    />
                  </td>
                </tr>
              </tbody>
            </table>
            <datalist :id="`classes-${selectedBatchId}`">
              <option v-for="label in batchClasses" :key="label" :value="label" />
            </datalist>
            <label class="check-line">
              <input v-model="importForm.overwrite" type="checkbox" />
              <span>覆盖该版本已有结果</span>
            </label>
            <p v-if="importMessage" class="error-text">{{ importMessage }}</p>
            <footer class="modal-foot">
              <button class="btn" type="button" @click="showImportModal = false">取消</button>
              <button class="btn primary" type="submit">汇入并计算</button>
            </footer>
          </form>
        </div>
      </div>
    </Teleport>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>
type AnyRecord = Record<string, any>

const ENDPOINT = '/api/model'
const EVAL_ENDPOINT = '/api/model_eval'
const columns = ["模型编号", "模型名称", "模型类型", "训练数据集", "特征字段", "目标字段", "评估指标", "模型状态"]
const actions = ["提交训练", "启动评估", "部署模型"]
const statuses = ["草稿", "已训练", "评估中", "已部署", "已下线"]
const stats = [{"label": "已部署模型", "value": 0}, {"label": "评估中模型", "value": 0}, {"label": "已下线模型", "value": 0}]

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)
const showCreateModal = ref(false)
const createFields = ref<Record<string, string>>({})

const batches = ref<AnyRecord[]>([])
const selectedBatchId = ref<number | null>(null)
const batchDetail = ref<AnyRecord | null>(null)
const versions = ref<AnyRecord[]>([])
const selectedVersionKey = ref('')
const versionDetail = ref<AnyRecord | null>(null)
const reviewItems = ref<AnyRecord[]>([])
const reviewSummary = ref<Record<string, number>>({ 待复核总数: 0, 弃答: 0, 少数类别弃答: 0, 金标人工复核: 0 })
const reviewNotes = ref<Record<string, string>>({})
const evalPanel = ref<HTMLElement | null>(null)
const evalModelFilter = ref('')

const showImportModal = ref(false)
const importForm = ref({ model: '', version: '', overwrite: false, predictions: {} as Record<string, string> })
const importMessage = ref('')

const selectedVersion = computed(() => {
  if (!selectedVersionKey.value) return null
  return versions.value.find((item) => `${item.模型编号}-${item.模型版本}` === selectedVersionKey.value) ?? null
})
const importSamples = computed<AnyRecord[]>(() => batchDetail.value?.样本 ?? [])
const importBatchCode = computed(() => String(batchDetail.value?.批次编号 ?? ''))
const batchClasses = computed<string[]>(() => Object.keys(batchDetail.value?.真实分类分布 ?? {}))
const evalStats = computed(() => [
  { label: '评估集样本', value: batchDetail.value?.样本总数 ?? 0 },
  { label: '已汇入版本', value: versions.value.length },
  { label: '少数类别', value: (batchDetail.value?.少数类别 ?? []).join('、') || '无' },
  { label: '待人工复核', value: reviewSummary.value.待复核总数 ?? 0 },
])

function updateStats() {
  const data = rows.value
  stats.length > 0 && (stats[0].value = data.filter((r: Row) => r.status === statuses[1] || r.pending).length)
  stats.length > 1 && (stats[1].value = data.filter((r: Row) => r.status && !r.pending && !r.abnormal).length)
  stats.length > 2 && (stats[2].value = data.filter((r: Row) => r.abnormal).length)
}

function formatRatio(value: number | null | undefined) {
  if (value === null || value === undefined) return '—'
  return `${(Number(value) * 100).toFixed(1)}%`
}

async function readJson(response: Response, fallback: string) {
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(payload.detail || payload.message || fallback)
  }
  return payload
}

function resetFilters() {
  filters.value = {}
  evalModelFilter.value = ''
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = ''
  createFields.value = {}
  showCreateModal.value = true
}

async function submitCreate() {
  errorMessage.value = ''
  try {
    const response = await request(ENDPOINT, {
      method: 'POST',
      body: JSON.stringify({ values: createFields.value }),
    })
    const data = await readJson(response, '登记失败')
    if (!data.ok) throw new Error(data.message || '登记失败')
    showCreateModal.value = false
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '登记失败'
  }
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    await readJson(response, '分析模型动作未生效，请稍后重试')
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '分析模型操作失败'
  }
}

async function focusEvaluation(modelCode: string) {
  evalModelFilter.value = modelCode
  evalPanel.value?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  const match = versions.value.find((item) => String(item.模型编号) === modelCode)
  if (match) {
    await selectVersion(match)
  }
}

async function loadBatches() {
  try {
    const response = await request(`${EVAL_ENDPOINT}/batches`)
    const payload = await readJson(response, '评估批次读取失败')
    batches.value = payload.items ?? []
    if (!selectedBatchId.value && batches.value.length) {
      selectedBatchId.value = batches.value[0].id
    }
    if (selectedBatchId.value) {
      await loadBatch()
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '评估批次读取失败'
  }
}

async function loadBatch() {
  if (!selectedBatchId.value) return
  errorMessage.value = ''
  try {
    const [batchResponse, versionResponse, reviewResponse] = await Promise.all([
      request(`${EVAL_ENDPOINT}/batches/${selectedBatchId.value}`),
      request(`${EVAL_ENDPOINT}/batches/${selectedBatchId.value}/versions`),
      request(`${EVAL_ENDPOINT}/review-queue?batch_id=${selectedBatchId.value}`),
    ])
    batchDetail.value = await readJson(batchResponse, '评估集读取失败')
    const versionPayload = await readJson(versionResponse, '版本指标读取失败')
    versions.value = versionPayload.items ?? []
    const reviewPayload = await readJson(reviewResponse, '复核清单读取失败')
    reviewItems.value = reviewPayload.items ?? []
    reviewSummary.value = reviewPayload.summary ?? reviewSummary.value

    const stillExists = versions.value.some(
      (item) => `${item.模型编号}-${item.模型版本}` === selectedVersionKey.value,
    )
    if (!stillExists) {
      const preferred: AnyRecord | undefined = evalModelFilter.value
        ? versions.value.find((item) => String(item.模型编号) === evalModelFilter.value)
        : versions.value[0]
      selectedVersionKey.value = preferred ? `${preferred.模型编号}-${preferred.模型版本}` : ''
    }
    if (selectedVersion.value) {
      await loadVersionDetail(selectedVersion.value)
    } else {
      versionDetail.value = null
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '评估结果读取失败'
  }
}

function isSelectedVersion(version: AnyRecord) {
  return `${version.模型编号}-${version.模型版本}` === selectedVersionKey.value
}

async function selectVersion(version: AnyRecord) {
  selectedVersionKey.value = `${version.模型编号}-${version.模型版本}`
  await loadVersionDetail(version)
}

async function loadVersionDetail(version: AnyRecord) {
  try {
    const query = new URLSearchParams({
      batch_id: String(selectedBatchId.value),
      model: String(version.模型编号),
      version: String(version.模型版本),
    })
    const response = await request(`${EVAL_ENDPOINT}/versions/detail?${query.toString()}`)
    versionDetail.value = await readJson(response, '版本明细读取失败')
  } catch (error) {
    versionDetail.value = null
    errorMessage.value = error instanceof Error ? error.message : '版本明细读取失败'
  }
}

function openImport() {
  importMessage.value = ''
  const baseModel = evalModelFilter.value || String(rows.value[0]?.['模型编号'] ?? '')
  importForm.value = { model: baseModel, version: '', overwrite: false, predictions: {} }
  showImportModal.value = true
}

async function submitImport() {
  importMessage.value = ''
  const results = importSamples.value.map((sample) => ({
    样本编号: sample.样本编号,
    真实分类: sample.真实分类,
    预测分类: (importForm.value.predictions[sample.样本编号] ?? '').trim(),
  }))
  try {
    const response = await request(`${EVAL_ENDPOINT}/import`, {
      method: 'POST',
      body: JSON.stringify({
        values: {
          评估批次: importBatchCode.value,
          模型编号: importForm.value.model.trim(),
          模型版本: importForm.value.version.trim(),
          results,
          覆盖已有: importForm.value.overwrite,
        },
      }),
    })
    const payload = await readJson(response, '汇入失败')
    if (!payload.ok) throw new Error(payload.message || '汇入失败')
    showImportModal.value = false
    await loadBatch()
  } catch (error) {
    importMessage.value = error instanceof Error ? error.message : '汇入失败'
  }
}

async function submitReview(row: AnyRecord) {
  const conclusion = (reviewNotes.value[row.id] ?? '').trim()
  if (!conclusion) {
    errorMessage.value = '请填写复核结论后再登记'
    return
  }
  try {
    const response = await request(`${EVAL_ENDPOINT}/results/${row.id}/review`, {
      method: 'POST',
      body: JSON.stringify({ values: { 复核结论: conclusion } }),
    })
    const payload = await readJson(response, '复核结论登记失败')
    if (!payload.ok) throw new Error(payload.message || '复核结论登记失败')
    delete reviewNotes.value[row.id]
    await loadBatch()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '复核结论登记失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
    if (!response.ok) {
      throw new Error('模型配置列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
    updateStats()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '分析模型列表读取失败'
  }
}

onMounted(async () => {
  await reload()
  await loadBatches()
})
</script>
