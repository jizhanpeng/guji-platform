<script setup lang="ts">
/**
 * 风格管理/复查页（方法二）：风格列表 + 联系表 + 成员缩略图 + 移动/改名/锁定/细分。
 */
import { computed, onMounted, ref } from 'vue'
import {
  NButton, NCard, NEmpty, NForm, NFormItem, NGrid, NGi, NInput, NInputNumber,
  NModal, NScrollbar, NSelect, NSpace, NSpin, NSwitch, NTag, useMessage,
} from 'naive-ui'
import { api, type ImageItem, type Project, type Style } from '../api'

const message = useMessage()

const projects = ref<Project[]>([])
const projectId = ref<number | null>(null)
const styles = ref<Style[]>([])
const currentId = ref<number | null>(null)
const members = ref<ImageItem[]>([])
const loadingStyles = ref(false)
const loadingMembers = ref(false)

const current = computed(() => styles.value.find(s => s.id === currentId.value) ?? null)

// 聚类参数弹窗
const showCluster = ref(false)
const clusterForm = ref({
  threshold: 0.25, merge_radius: 0.5, max_cluster_pages: 0,
  dino_only: false, split_policy: 'guard',
})
// 细分弹窗
const showSub = ref(false)
const subForm = ref({ threshold: 0.3, dino_only: true })
// 改名
const renameValue = ref('')

async function loadProjects() {
  projects.value = await api.listProjects()
  if (!projectId.value && projects.value.length) projectId.value = projects.value[0].id
}

async function loadStyles() {
  if (!projectId.value) return
  loadingStyles.value = true
  try {
    styles.value = await api.listStyles(projectId.value)
    if (currentId.value && !styles.value.some(s => s.id === currentId.value)) {
      currentId.value = null
      members.value = []
    }
  } finally {
    loadingStyles.value = false
  }
}

async function selectStyle(s: Style) {
  currentId.value = s.id
  renameValue.value = s.name
  loadingMembers.value = true
  try {
    const res = await api.listImages({ project_id: projectId.value!, page: 1, page_size: 500 })
    members.value = res.items.filter(i => i.style_id === s.id)
  } finally {
    loadingMembers.value = false
  }
}

async function runEmbed() {
  if (!projectId.value) return
  await api.startEmbed(projectId.value)
  message.success('特征提取任务已提交（任务中心查看进度）')
}

async function runCluster() {
  await api.startCluster({ project_id: projectId.value!, ...clusterForm.value })
  showCluster.value = false
  message.success('聚类任务已提交；完成后点「刷新」')
}

async function runSubcluster() {
  if (!current.value) return
  await api.startSubcluster(current.value.id, subForm.value.threshold, subForm.value.dino_only)
  showSub.value = false
  message.success('细分任务已提交；完成后点「刷新」')
}

async function renameStyle() {
  if (!current.value || !renameValue.value || renameValue.value === current.value.name) return
  try {
    await api.patchStyle(current.value.id, { name: renameValue.value })
    message.success('已改名')
    loadStyles()
  } catch (e: any) {
    message.error(e.message)
  }
}

async function toggleLock(split: string | null) {
  if (!current.value) return
  try {
    await api.patchStyle(current.value.id, { locked_split: split })
    message.success(split ? `已锁定 ${split} 划分` : '已解除锁定')
    loadStyles()
  } catch (e: any) {
    message.error(e.message)
  }
}

async function moveMember(img: ImageItem, styleId: number | null, force = false) {
  try {
    await api.moveImageStyle(img.id, styleId, force)
    message.success('已移动')
    selectStyle(current.value!)
    loadStyles()
  } catch (e: any) {
    if (String(e.message).includes('409')) {
      if (confirm('目标风格划分锁定不匹配，是否随迁该页划分？')) {
        moveMember(img, styleId, true)
      }
    } else {
      message.error(e.message)
    }
  }
}

const SPLIT_TAG: Record<string, 'success' | 'warning' | 'error'> = {
  train: 'success', val: 'warning', test: 'error',
}

onMounted(async () => {
  await loadProjects()
  await loadStyles()
})
</script>

<template>
  <div class="styles-view">
    <n-space style="margin-bottom: 12px" align="center">
      <n-select
        v-model:value="projectId"
        :options="projects.map(p => ({ label: p.name, value: p.id }))"
        style="width: 200px"
        @update:value="() => { currentId = null; members = []; loadStyles() }"
      />
      <n-button :disabled="!projectId" @click="runEmbed">提取特征</n-button>
      <n-button type="primary" :disabled="!projectId" @click="showCluster = true">重新聚类</n-button>
      <n-button @click="loadStyles">刷新</n-button>
    </n-space>

    <div class="body">
      <div class="style-list">
        <n-spin :show="loadingStyles">
          <n-scrollbar style="max-height: calc(100vh - 140px)">
            <n-empty v-if="!styles.length" description="暂无风格，先「提取特征」再「重新聚类」" />
            <div
              v-for="s in styles" :key="s.id"
              class="style-row" :class="{ active: s.id === currentId }"
              @click="selectStyle(s)"
            >
              <span class="name">{{ s.name }}</span>
              <n-tag size="tiny">{{ s.image_count }}页</n-tag>
              <n-tag v-if="s.locked_split" size="tiny" :type="SPLIT_TAG[s.locked_split]">
                🔒{{ s.locked_split }}
              </n-tag>
              <n-tag v-if="Object.keys(s.splits).length > 1" size="tiny" type="error">跨划分</n-tag>
            </div>
          </n-scrollbar>
        </n-spin>
      </div>

      <div class="detail">
        <n-empty v-if="!current" description="选择左侧风格查看成员" />
        <template v-else>
          <n-space align="center" style="margin-bottom: 8px">
            <n-input v-model:value="renameValue" size="small" style="width: 200px" />
            <n-button size="small" @click="renameStyle">改名</n-button>
            <n-select
              size="small" style="width: 130px"
              :value="current.locked_split"
              :options="[
                { label: '不锁定', value: '' },
                { label: '锁 train', value: 'train' },
                { label: '锁 val', value: 'val' },
                { label: '锁 test', value: 'test' },
              ]"
              @update:value="(v: string) => toggleLock(v || null)"
            />
            <n-button size="small" :disabled="current.image_count < 3" @click="showSub = true">
              二次细分
            </n-button>
          </n-space>

          <n-card size="small" title="联系表（抽样拼图）" style="margin-bottom: 8px">
            <img :src="api.styleSheetUrl(current.id)" style="max-width: 100%; background: #f5f5f5" />
          </n-card>

          <n-spin :show="loadingMembers">
            <n-grid :cols="6" :x-gap="8" :y-gap="8">
              <n-gi v-for="m in members" :key="m.id">
                <n-card size="small">
                  <template #cover>
                    <img :src="api.imageFileUrl(m.id, 'thumb')"
                      style="width: 100%; height: 120px; object-fit: contain; background: #f5f5f5" />
                  </template>
                  <div style="font-size: 12px">
                    {{ m.filename }}
                    <n-tag v-if="m.official_split" size="tiny" :type="SPLIT_TAG[m.official_split]">
                      {{ m.official_split }}
                    </n-tag>
                  </div>
                  <n-select
                    size="tiny" placeholder="移到…"
                    :options="styles.filter(s => s.id !== currentId).map(s => ({ label: s.name, value: s.id }))"
                    @update:value="(v: number) => moveMember(m, v)"
                  />
                </n-card>
              </n-gi>
            </n-grid>
          </n-spin>
        </template>
      </div>
    </div>

    <n-modal v-model:show="showCluster" preset="card" title="重新聚类（全项目）" style="width: 460px">
      <n-form label-placement="left" label-width="140">
        <n-form-item label="距离阈值">
          <n-input-number v-model:value="clusterForm.threshold" :step="0.05" :min="0.05" :max="1" />
        </n-form-item>
        <n-form-item label="单页归并半径">
          <n-input-number v-model:value="clusterForm.merge_radius" :step="0.05" :min="0" :max="1" />
        </n-form-item>
        <n-form-item label="大簇解散上限">
          <n-input-number v-model:value="clusterForm.max_cluster_pages" :min="0" />
        </n-form-item>
        <n-form-item label="仅 DINO 特征">
          <n-switch v-model:value="clusterForm.dino_only" />
        </n-form-item>
        <n-form-item label="划分策略">
          <n-select v-model:value="clusterForm.split_policy" :options="[
            { label: '守卫：跨划分组整体迁移', value: 'guard' },
            { label: '保持原划分（仅告警）', value: 'keep' },
          ]" />
        </n-form-item>
      </n-form>
      <template #footer>
        <n-button type="primary" @click="runCluster">提交聚类任务</n-button>
      </template>
    </n-modal>

    <n-modal v-model:show="showSub" preset="card" :title="`细分 ${current?.name ?? ''}`" style="width: 400px">
      <n-form label-placement="left" label-width="120">
        <n-form-item label="距离阈值">
          <n-input-number v-model:value="subForm.threshold" :step="0.05" :min="0.05" :max="1" />
        </n-form-item>
        <n-form-item label="仅 DINO 特征">
          <n-switch v-model:value="subForm.dino_only" />
        </n-form-item>
      </n-form>
      <template #footer>
        <n-button type="primary" @click="runSubcluster">提交细分任务</n-button>
      </template>
    </n-modal>
  </div>
</template>

<style scoped>
.body { display: flex; gap: 12px; }
.style-list { width: 300px; flex-shrink: 0; border-right: 1px solid #eee; padding-right: 8px; }
.style-row {
  display: flex; align-items: center; gap: 6px; padding: 6px 8px;
  cursor: pointer; border-radius: 4px;
}
.style-row:hover { background: #f8f8f8; }
.style-row.active { background: #e8f0fe; }
.style-row .name { flex: 1; font-size: 13px; }
.detail { flex: 1; min-width: 0; }
</style>
