<script setup lang="ts">
/**
 * 裁剪复查页（方法二）：筛选网格 + 确认/驳回 + 字表 + 数据流水线入口。
 */
import { computed, onMounted, ref, watch } from 'vue'
import {
  NButton, NEmpty, NGrid, NGi, NInput, NInputNumber, NModal, NPagination,
  NSelect, NSpace, NSpin, NTab, NTabs, NTag, useMessage,
} from 'naive-ui'
import { api, type CharsetEntry, type Crop, type Project, type Style } from '../api'

const message = useMessage()

const projects = ref<Project[]>([])
const projectId = ref<number | null>(null)
const styles = ref<Style[]>([])

// ---- 裁剪网格 ----
const crops = ref<Crop[]>([])
const total = ref(0)
const page = ref(1)
const per = 96
const loading = ref(false)
const filterStatus = ref<string | null>(null)
const filterStyle = ref<number | null>(null)
const filterChar = ref('')
const stats = ref<Record<string, number>>({})
const selected = ref<Set<number>>(new Set())

// ---- 字表 ----
const charset = ref<CharsetEntry[]>([])
const charsetTotal = ref(0)
const charsetPage = ref(1)
const loadingCharset = ref(false)

// ---- 任务弹窗 ----
const showCharsetJob = ref(false)
const minInstances = ref(20)

const STATUS_TYPE: Record<string, 'warning' | 'success' | 'error'> = {
  auto: 'warning', confirmed: 'success', rejected: 'error',
}
const STATUS_LABEL: Record<string, string> = {
  auto: '待复查', confirmed: '已确认', rejected: '已驳回',
}

const styleOptions = computed(() =>
  styles.value.map(s => ({ label: `${s.name}（${s.image_count}页）`, value: s.id })))

async function loadProjects() {
  projects.value = await api.listProjects()
  if (!projectId.value && projects.value.length) projectId.value = projects.value[0].id
}

async function loadStyles() {
  if (!projectId.value) return
  styles.value = await api.listStyles(projectId.value)
}

async function loadCrops() {
  if (!projectId.value) return
  loading.value = true
  try {
    const res = await api.listCrops({
      project_id: projectId.value,
      status: filterStatus.value ?? undefined,
      style_id: filterStyle.value ?? undefined,
      char: filterChar.value || undefined,
      page: page.value, per,
    })
    crops.value = res.items
    total.value = res.total
    selected.value = new Set()
  } finally {
    loading.value = false
  }
}

async function loadStats() {
  if (!projectId.value) return
  stats.value = await api.cropStats(projectId.value)
}

async function loadCharset() {
  if (!projectId.value) return
  loadingCharset.value = true
  try {
    const res = await api.listCharset(projectId.value, charsetPage.value, 200)
    charset.value = res.items
    charsetTotal.value = res.total
  } finally {
    loadingCharset.value = false
  }
}

function toggleSelect(c: Crop) {
  const s = new Set(selected.value)
  if (s.has(c.id)) s.delete(c.id)
  else s.add(c.id)
  selected.value = s
}

function selectAllOnPage() {
  const s = new Set(selected.value)
  const allIn = crops.value.every(c => s.has(c.id))
  if (allIn) crops.value.forEach(c => s.delete(c.id))
  else crops.value.forEach(c => s.add(c.id))
  selected.value = s
}

async function setStatus(ids: number[], status: string) {
  if (!ids.length) return
  await api.bulkCropStatus(ids, status)
  message.success(`已${STATUS_LABEL[status]} ${ids.length} 个`)
  loadCrops()
  loadStats()
}

async function runJob(fn: () => Promise<unknown>, label: string) {
  if (!projectId.value) return
  await fn()
  message.success(`${label}任务已提交（任务中心查看进度）`)
}

watch([filterStatus, filterStyle], () => { page.value = 1; loadCrops() })
watch(page, loadCrops)
watch(projectId, () => {
  page.value = 1
  filterStyle.value = null
  loadStyles(); loadCrops(); loadStats(); loadCharset()
})

onMounted(async () => {
  await loadProjects()
  await loadStyles()
  await loadCrops()
  await loadStats()
  await loadCharset()
})
</script>

<template>
  <div>
    <n-space style="margin-bottom: 12px" align="center" wrap>
      <n-select
        v-model:value="projectId"
        :options="projects.map(p => ({ label: p.name, value: p.id }))"
        style="width: 200px"
      />
      <n-button :disabled="!projectId" @click="runJob(() => api.startAutoCrop(projectId!), '自动裁剪')">
        自动裁剪
      </n-button>
      <n-button :disabled="!projectId" @click="showCharsetJob = true">重建字表</n-button>
      <n-button :disabled="!projectId" @click="runJob(api.startRender, '渲染字模')">渲染字模</n-button>
      <n-button
        type="primary" :disabled="!projectId"
        @click="runJob(() => api.startFontDatasetExport(projectId!), 'FontDataset 导出')"
      >
        导出 FontDataset
      </n-button>
      <n-button @click="() => { loadCrops(); loadStats(); loadCharset() }">刷新</n-button>
      <n-tag v-for="(n, s) in stats" :key="s" :type="STATUS_TYPE[s]" size="small">
        {{ STATUS_LABEL[s] ?? s }} {{ n }}
      </n-tag>
    </n-space>

    <n-tabs type="line">
      <n-tab name="crops" tab="裁剪复查">
        <n-space style="margin: 8px 0" align="center" wrap>
          <n-select
            v-model:value="filterStatus" clearable placeholder="状态"
            :options="Object.entries(STATUS_LABEL).map(([value, label]) => ({ label, value }))"
            style="width: 120px"
          />
          <n-select
            v-model:value="filterStyle" clearable filterable placeholder="风格"
            :options="styleOptions" style="width: 220px"
          />
          <n-input
            v-model:value="filterChar" placeholder="单字过滤" maxlength="1"
            style="width: 100px" @update:value="() => { page = 1; loadCrops() }"
          />
          <n-button size="small" @click="selectAllOnPage">全选/反选本页</n-button>
          <n-button
            size="small" type="success" :disabled="!selected.size"
            @click="setStatus([...selected], 'confirmed')"
          >
            确认所选（{{ selected.size }}）
          </n-button>
          <n-button
            size="small" type="error" :disabled="!selected.size"
            @click="setStatus([...selected], 'rejected')"
          >
            驳回所选
          </n-button>
        </n-space>

        <n-spin :show="loading">
          <n-empty v-if="!crops.length" description="暂无裁剪，先提交「自动裁剪」任务" />
          <n-grid :cols="8" :x-gap="8" :y-gap="8">
            <n-gi v-for="c in crops" :key="c.id">
              <div
                class="crop-card" :class="{ picked: selected.has(c.id) }"
                @click="toggleSelect(c)"
              >
                <img :src="api.cropImageUrl(c.id)" loading="lazy" />
                <div class="meta">
                  <span class="char">{{ c.char }}</span>
                  <n-tag size="tiny" :type="STATUS_TYPE[c.status]">{{ STATUS_LABEL[c.status] }}</n-tag>
                </div>
              </div>
            </n-gi>
          </n-grid>
          <n-pagination
            v-model:page="page" :item-count="total" :page-size="per"
            style="margin-top: 12px; justify-content: center"
          />
        </n-spin>
      </n-tab>

      <n-tab name="charset" :tab="`字表（${charsetTotal}）`">
        <n-spin :show="loadingCharset">
          <n-empty v-if="!charset.length" description="暂无字表，先「重建字表」" />
          <n-grid :cols="10" :x-gap="8" :y-gap="8">
            <n-gi v-for="e in charset" :key="e.char">
              <div class="char-card">
                <img v-if="e.renderable" :src="api.contentImageUrl(e.char)" loading="lazy" />
                <div v-else class="no-render">✕</div>
                <div class="meta">
                  <span class="char">{{ e.char }}</span>
                  <span style="font-size: 11px; color: #888">×{{ e.instance_count }}</span>
                </div>
                <div style="display: flex; gap: 2px; justify-content: center">
                  <n-tag v-if="e.in_trainset" size="tiny" type="success">训</n-tag>
                  <n-tag v-if="e.is_holdout" size="tiny" type="warning">留</n-tag>
                </div>
              </div>
            </n-gi>
          </n-grid>
          <n-pagination
            v-model:page="charsetPage" :item-count="charsetTotal" :page-size="200"
            style="margin-top: 12px; justify-content: center"
            @update:page="loadCharset"
          />
        </n-spin>
      </n-tab>
    </n-tabs>

    <n-modal v-model:show="showCharsetJob" preset="card" title="重建字表" style="width: 380px">
      <n-space vertical>
        <div>
          最小实例数（进入训练集阈值）：
          <n-input-number v-model:value="minInstances" :min="1" style="width: 120px" />
        </div>
        <n-button
          type="primary"
          @click="() => { showCharsetJob = false; runJob(() => api.startCharset(projectId!, minInstances), '字表重建') }"
        >
          提交任务
        </n-button>
      </n-space>
    </n-modal>
  </div>
</template>

<style scoped>
.crop-card {
  border: 2px solid transparent; border-radius: 4px; cursor: pointer;
  padding: 4px; background: #fafafa; text-align: center;
}
.crop-card:hover { border-color: #91caff; }
.crop-card.picked { border-color: #2080f0; background: #e8f0fe; }
.crop-card img { width: 64px; height: 64px; image-rendering: auto; }
.char-card { padding: 4px; background: #fafafa; border-radius: 4px; text-align: center; }
.char-card img { width: 64px; height: 64px; }
.no-render {
  width: 64px; height: 64px; line-height: 64px; margin: 0 auto;
  color: #ccc; font-size: 24px;
}
.meta { display: flex; justify-content: center; align-items: center; gap: 4px; margin-top: 2px; }
.char { font-size: 14px; font-weight: 600; }
</style>
