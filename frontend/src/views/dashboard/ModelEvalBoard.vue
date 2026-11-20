<template>
  <section class="eval-board">
    <header class="panel-head">
      <div>
        <h3>分组评估视图</h3>
        <p class="panel-desc">
          用模型评估结果数据集计算分组差值。主比较采用共同覆盖准确率，只统计两个版本都给出预测的样本；
          辅助比较采用全评估集正确响应占比，弃答计入分母且不算正确。
        </p>
      </div>
      <div class="panel-actions">
        <label class="inline-field">
          <span>评估批次</span>
          <select v-model.number="batchId" @change="onBatchChange">
            <option v-for="batch in batches" :key="batch.id" :value="batch.id">
              {{ batch.批次编号 }} · {{ batch.评估集名称 }}
            </option>
          </select>
        </label>
        <button class="btn" type="button" :disabled="!batchId" @click="calculate">重新计算</button>
        <button class="btn primary" type="button" :disabled="!canCompare" @click="saveComparison">
          留存比较结果
        </button>
      </div>
    </header>

    <div class="form-row selector-row">
      <label class="inline-field">
        <span>版本 A</span>
        <select v-model="versionA" @change="calculate">
          <option value="">请选择</option>
          <option v-for="item in versionOptions" :key="`a-${keyOf(item)}`" :value="keyOf(item)">
            {{ item.模型编号 }} {{ item.模型版本 }}（覆盖 {{ formatRatio(item.覆盖率) }}）
          </option>
        </select>
      </label>
      <label class="inline-field">
        <span>版本 B</span>
        <select v-model="versionB" @change="calculate">
          <option value="">请选择</option>
          <option v-for="item in versionOptions" :key="`b-${keyOf(item)}`" :value="keyOf(item)">
            {{ item.模型编号 }} {{ item.模型版本 }}（覆盖 {{ formatRatio(item.覆盖率) }}）
          </option>
        </select>
      </label>
    </div>

    <p v-if="errorMessage" class="error-text">{{ errorMessage }}</p>
    <p v-if="!view" class="empty-state">选择两个模型版本后计算分组差值</p>

    <template v-else>
      <div class="compare-summary">
        <div class="compare-card">
          <span class="compare-label">主比较 · {{ view.主比较指标 }}</span>
          <strong class="compare-value" :class="deltaClass(view.主比较?.差值)">
            {{ view.主比较?.可比较 ? formatDelta(view.主比较?.差值) : '无可比差值' }}
          </strong>
          <p class="compare-basis">
            {{ view.主比较?.可比较
              ? `采用人群：${view.主比较.采用人群}；${view.主比较.分母}`
              : view.主比较?.说明 }}
          </p>
          <p class="compare-basis">版本 A（{{ view.版本A }}）{{ formatRatio(view.主比较?.准确率A) }} · 版本 B（{{ view.版本B }}）{{ formatRatio(view.主比较?.准确率B) }}</p>
        </div>
        <div class="compare-card">
          <span class="compare-label">辅助比较 · {{ view.辅助比较指标 }}</span>
          <strong class="compare-value" :class="deltaClass(view.辅助比较?.差值)">
            {{ formatDelta(view.辅助比较?.差值) }}
          </strong>
          <p class="compare-basis">
            采用人群：{{ view.辅助比较?.采用人群 }}；{{ view.辅助比较?.分母 }}
          </p>
          <p class="compare-basis">
            正确答复 {{ view.辅助比较?.正确数A }} / {{ view.辅助比较?.评估集样本总数 }} 对
            {{ view.辅助比较?.正确数B }} / {{ view.辅助比较?.评估集样本总数 }}；
            实际作答 {{ view.辅助比较?.已作答A }} 与 {{ view.辅助比较?.已作答B }} 个样本
          </p>
        </div>
      </div>

      <table class="data-table compact">
        <thead>
          <tr>
            <th>样本分组</th>
            <th>分母（样本数）</th>
            <th>共同覆盖样本数</th>
            <th>共同覆盖准确率 A</th>
            <th>共同覆盖准确率 B</th>
            <th>主比较差值</th>
            <th>比较依据</th>
            <th>可直接比较</th>
            <th>全组正确响应占比 A / B</th>
            <th>预测缺口</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="group in view.分组" :key="group.样本分组">
            <td>{{ group.样本分组 }}</td>
            <td>{{ group.全组分母 }}</td>
            <td>{{ group.共同覆盖样本数 }}</td>
            <td>{{ formatRatio(group.共同覆盖准确率A) }}</td>
            <td>{{ formatRatio(group.共同覆盖准确率B) }}</td>
            <td :class="deltaClass(group.主比较差值)">
              {{ group.可直接比较 ? formatDelta(group.主比较差值) : '无可比差值' }}
            </td>
            <td class="basis-cell">
              {{ group.主比较依据 }}
              <span v-if="group.不可比较原因" class="basis-warn">{{ group.不可比较原因 }}</span>
            </td>
            <td>{{ group.可直接比较 ? '是' : '否' }}</td>
            <td>
              {{ formatRatio(group.全组正确响应占比A) }} /
              {{ formatRatio(group.全组正确响应占比B) }}
              <span class="basis-cell">（分母 {{ group.全组分母 }}）</span>
            </td>
            <td class="gap-cell">
              <span v-if="group.预测缺口.仅A作答.length">仅 A 作答：{{ group.预测缺口.仅A作答.join('、') }}</span>
              <span v-if="group.预测缺口.仅B作答.length">仅 B 作答：{{ group.预测缺口.仅B作答.join('、') }}</span>
              <span v-if="group.预测缺口.两者弃答.length">两者弃答：{{ group.预测缺口.两者弃答.join('、') }}</span>
              <span v-if="!hasGap(group)" class="muted">无预测缺口</span>
            </td>
          </tr>
        </tbody>
      </table>
      <p class="hint-text">
        可直接比较的类别：{{ view.可直接比较分组.join('、') || '无' }}；
        存在预测缺口的类别：{{ view.预测缺口分组.join('、') || '无' }}。
        主比较差值方向为版本 A - 版本 B，分母随所选版本的实际共同覆盖变化。
      </p>

      <h4 class="sub-head">已留存的比较结果</h4>
      <p class="hint-text">
        切换版本不会改变已留存记录；重新打开时按记录自身的评估批次与样本覆盖回查。
      </p>
      <table class="data-table compact">
        <thead>
          <tr>
            <th>比较编号</th>
            <th>评估批次</th>
            <th>版本 A</th>
            <th>版本 B</th>
            <th>主比较差值</th>
            <th>共同覆盖</th>
            <th>正确响应占比 A / B</th>
            <th>计算时间</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in comparisons" :key="String(item.id)">
            <td>{{ item.比较编号 }}</td>
            <td>{{ item.评估批次 }}</td>
            <td>{{ item.模型A }} {{ item.版本A }}</td>
            <td>{{ item.模型B }} {{ item.版本B }}</td>
            <td :class="deltaClass(item.主比较差值)">
              {{ item.主比较可比较 ? formatDelta(item.主比较差值) : '无可比差值' }}
            </td>
            <td>{{ item.共同覆盖样本数 }}</td>
            <td>{{ formatRatio(item.正确响应占比A) }} / {{ formatRatio(item.正确响应占比B) }}</td>
            <td>{{ item.计算时间 }}</td>
            <td>
              <button class="link" type="button" @click="openComparison(item.id)">打开</button>
            </td>
          </tr>
          <tr v-if="!comparisons.length">
            <td colspan="9" class="empty-state">还没有留存比较结果</td>
          </tr>
        </tbody>
      </table>

      <section v-if="opened" class="opened-record">
        <header class="panel-head">
          <div>
            <h4 class="sub-head">重新打开：{{ opened.比较编号 }}</h4>
            <p class="panel-desc">
              该记录采自评估批次 {{ opened.评估批次 }}（{{ opened.评估集编号 }}，评估集样本 {{ opened.评估集样本总数 }} 个），
              版本 {{ opened.模型A }} {{ opened.版本A }} 对 {{ opened.模型B }} {{ opened.版本B }}。
            </p>
          </div>
          <button class="btn ghost" type="button" @click="opened = null">收起</button>
        </header>
        <div class="metric-line">
          <span>主比较分母：{{ opened.样本覆盖?.分母说明?.主比较 }}</span>
          <span>辅助比较分母：{{ opened.样本覆盖?.分母说明?.辅助比较 }}</span>
          <span>共同覆盖样本：{{ opened.样本覆盖?.共同覆盖?.join('、') || '无' }}</span>
          <span>仅 A 作答：{{ opened.样本覆盖?.仅A作答?.join('、') || '无' }}</span>
          <span>仅 B 作答：{{ opened.样本覆盖?.仅B作答?.join('、') || '无' }}</span>
        </div>
        <table class="data-table compact">
          <thead>
            <tr>
              <th>样本分组</th>
              <th>分母</th>
              <th>共同覆盖</th>
              <th>主比较差值</th>
              <th>可比</th>
              <th>预测缺口</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="group in opened.分组" :key="`open-${group.样本分组}`">
              <td>{{ group.样本分组 }}</td>
              <td>{{ group.全组分母 }}</td>
              <td>{{ group.共同覆盖样本数 }}</td>
              <td :class="deltaClass(group.主比较差值)">
                {{ group.可直接比较 ? formatDelta(group.主比较差值) : '无可比差值' }}
              </td>
              <td>{{ group.可直接比较 ? '是' : '否' }}</td>
              <td class="gap-cell">
                <span v-if="group.预测缺口.仅A作答.length">仅 A：{{ group.预测缺口.仅A作答.join('、') }}</span>
                <span v-if="group.预测缺口.仅B作答.length">仅 B：{{ group.预测缺口.仅B作答.join('、') }}</span>
                <span v-if="group.预测缺口.两者弃答.length">两者弃答：{{ group.预测缺口.两者弃答.join('、') }}</span>
              </td>
            </tr>
          </tbody>
        </table>
      </section>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'

type AnyRecord = Record<string, any>

const ENDPOINT = '/api/model_eval'
const batches = ref<AnyRecord[]>([])
const batchId = ref<number | null>(null)
const versionOptions = ref<AnyRecord[]>([])
const versionA = ref('')
const versionB = ref('')
const view = ref<AnyRecord | null>(null)
const comparisons = ref<AnyRecord[]>([])
const opened = ref<AnyRecord | null>(null)
const errorMessage = ref('')

const canCompare = computed(() => Boolean(
  view.value && versionA.value && versionB.value && versionA.value !== versionB.value,
))

function keyOf(item: AnyRecord) {
  return `${item.模型编号}|${item.模型版本}`
}

function splitKey(key: string) {
  const [model, version] = key.split('|')
  return { model, version }
}

function formatRatio(value: number | null | undefined) {
  if (value === null || value === undefined) return '—'
  return `${(Number(value) * 100).toFixed(1)}%`
}

function formatDelta(value: number | null | undefined) {
  if (value === null || value === undefined) return '—'
  return `${value > 0 ? '+' : ''}${(Number(value) * 100).toFixed(1)}%`
}

function deltaClass(value: number | null | undefined) {
  if (value === null || value === undefined || value === 0) return 'delta-zero'
  return value > 0 ? 'delta-up' : 'delta-down'
}

function hasGap(group: AnyRecord) {
  const gap = group.预测缺口 ?? {}
  return Boolean(gap.仅A作答?.length || gap.仅B作答?.length || gap.两者弃答?.length)
}

async function readJson(response: Response, fallback: string) {
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(payload.detail || payload.message || fallback)
  }
  return payload
}

async function loadBatches() {
  const response = await request(`${ENDPOINT}/batches`)
  const payload = await readJson(response, '评估批次读取失败')
  batches.value = payload.items ?? []
  if (!batchId.value && batches.value.length) {
    batchId.value = batches.value[0].id
  }
  if (batchId.value) {
    await loadVersions()
  }
}

async function loadVersions() {
  if (!batchId.value) return
  const response = await request(`${ENDPOINT}/batches/${batchId.value}/versions`)
  const payload = await readJson(response, '版本清单读取失败')
  versionOptions.value = payload.items ?? []
  const keys = versionOptions.value.map(keyOf)
  if (!keys.includes(versionA.value)) versionA.value = keys[0] ?? ''
  if (!keys.includes(versionB.value) || versionB.value === versionA.value) {
    versionB.value = keys.find((key) => key !== versionA.value) ?? ''
  }
  await calculate()
}

async function onBatchChange() {
  versionA.value = ''
  versionB.value = ''
  view.value = null
  await loadVersions()
}

async function calculate() {
  errorMessage.value = ''
  if (!batchId.value || !versionA.value || !versionB.value || versionA.value === versionB.value) {
    view.value = null
    return
  }
  const a = splitKey(versionA.value)
  const b = splitKey(versionB.value)
  const query = new URLSearchParams({
    model_a: a.model ?? '',
    version_a: a.version ?? '',
    model_b: b.model ?? '',
    version_b: b.version ?? '',
  })
  try {
    const response = await request(`${ENDPOINT}/batches/${batchId.value}/group-view?${query.toString()}`)
    view.value = await readJson(response, '分组评估视图读取失败')
  } catch (error) {
    view.value = null
    errorMessage.value = error instanceof Error ? error.message : '分组评估视图读取失败'
  }
}

async function loadComparisons() {
  try {
    const response = await request(`${ENDPOINT}/comparisons`)
    const payload = await readJson(response, '留存比较结果读取失败')
    comparisons.value = payload.items ?? []
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '留存比较结果读取失败'
  }
}

async function saveComparison() {
  if (!batchId.value || !versionA.value || !versionB.value) return
  errorMessage.value = ''
  const a = splitKey(versionA.value)
  const b = splitKey(versionB.value)
  try {
    const response = await request(`${ENDPOINT}/compare`, {
      method: 'POST',
      body: JSON.stringify({
        values: {
          批次ID: batchId.value,
          模型A: a.model,
          版本A: a.version,
          模型B: b.model,
          版本B: b.version,
          留存: true,
        },
      }),
    })
    const payload = await readJson(response, '比较结果留存失败')
    if (!payload.ok) throw new Error(payload.message || '比较结果留存失败')
    await loadComparisons()
    if (payload.entry?.id) {
      await openComparison(payload.entry.id)
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '比较结果留存失败'
  }
}

async function openComparison(id: number) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/comparisons/${id}`)
    opened.value = await readJson(response, '比较结果读取失败')
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '比较结果读取失败'
  }
}

onMounted(async () => {
  try {
    await loadBatches()
    await loadComparisons()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '看板数据读取失败'
  }
})
</script>
