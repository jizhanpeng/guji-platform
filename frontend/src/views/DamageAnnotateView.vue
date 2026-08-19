<script setup lang="ts">
/**
 * 破损标注页（方法一）：笔刷描画破损区域 → 保存为 DamageRegion（服务端光栅化 mask）。
 * 快捷键：B 笔刷开关、E 橡皮、Ctrl+Z 撤销草稿一笔、←/→ 前后页。
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  NButton, NEmpty, NInputNumber, NScrollbar, NSelect, NSlider, NSpin,
  NSwitch, NTag, useMessage,
} from 'naive-ui'
import DamageCanvas, { type RegionView } from '../components/DamageCanvas.vue'
import { api, type DamageRegion, type ImageItem, type Stroke } from '../api'

const route = useRoute()
const router = useRouter()
const message = useMessage()

const imageId = ref(Number(route.params.id))
const image = ref<ImageItem | null>(null)
const regions = ref<DamageRegion[]>([])
const draft = ref<Stroke[]>([])
const damageType = ref('paper_damage')
const brushing = ref(true)
const erasing = ref(false)
const radius = ref(12)
const loading = ref(true)
const projectImages = ref<ImageItem[]>([])

const scale = ref(1)
const imageUrl = ref('')

const TYPE_OPTIONS = [
  { label: '缺字 character_missing', value: 'character_missing' },
  { label: '纸损 paper_damage', value: 'paper_damage' },
  { label: '墨迹侵蚀 ink_erosion', value: 'ink_erosion' },
]
const TYPE_LABEL: Record<string, string> = {
  character_missing: '缺字', paper_damage: '纸损', ink_erosion: '墨迹',
}
const TYPE_TAG: Record<string, 'warning' | 'error' | 'info'> = {
  character_missing: 'warning', paper_damage: 'error', ink_erosion: 'info',
}

const regionViews = computed<RegionView[]>(() =>
  regions.value.map(r => ({
    id: r.id,
    damage_type: r.damage_type,
    strokes: r.strokes_json ? JSON.parse(r.strokes_json) : [],
  })),
)

function probeSize(url: string): Promise<{ width: number; height: number }> {
  return new Promise((resolve, reject) => {
    const img = new Image()
    img.onload = () => resolve({ width: img.naturalWidth, height: img.naturalHeight })
    img.onerror = reject
    img.src = url
  })
}

async function loadAll() {
  loading.value = true
  draft.value = []
  try {
    image.value = await api.getImage(imageId.value)
    regions.value = await api.listDamage(imageId.value)
    imageUrl.value = api.imageFileUrl(imageId.value, 'display')
    const disp = await probeSize(imageUrl.value)
    scale.value = image.value.width / disp.width
    const list = await api.listImages({ project_id: image.value.project_id, page_size: 10000 })
    projectImages.value = list.items
  } finally {
    loading.value = false
  }
}

function go(delta: number) {
  const ids = projectImages.value.map(i => i.id)
  const idx = ids.indexOf(imageId.value)
  const next = ids[idx + delta]
  if (next != null) router.push(`/damage/${next}`)
  else message.info(delta > 0 ? '已是最后一页' : '已是第一页')
}

function onAddStroke(s: Stroke) {
  draft.value = [...draft.value, s]
}

function undoDraft() {
  draft.value = draft.value.slice(0, -1)
}

async function saveDraft() {
  if (!draft.value.length) return message.info('草稿为空，先画几笔')
  const region = await api.createDamage(imageId.value, {
    damage_type: damageType.value,
    strokes: draft.value,
  })
  regions.value.push(region)
  draft.value = []
  message.success(`已保存 ${TYPE_LABEL[region.damage_type]} 区域`)
}

async function retype(r: DamageRegion, t: string) {
  const updated = await api.patchDamage(r.id, { damage_type: t })
  const idx = regions.value.findIndex(x => x.id === r.id)
  if (idx >= 0) regions.value[idx] = updated
}

async function removeRegion(r: DamageRegion) {
  await api.deleteDamage(r.id)
  regions.value = regions.value.filter(x => x.id !== r.id)
}

function onKeydown(e: KeyboardEvent) {
  const tag = (e.target as HTMLElement).tagName
  if (tag === 'INPUT' || tag === 'TEXTAREA') return
  if (e.key === 'b' || e.key === 'B') brushing.value = !brushing.value
  else if (e.key === 'e' || e.key === 'E') erasing.value = !erasing.value
  else if ((e.ctrlKey || e.metaKey) && (e.key === 'z' || e.key === 'Z')) {
    e.preventDefault()
    undoDraft()
  } else if (e.key === 'ArrowLeft') go(-1)
  else if (e.key === 'ArrowRight') go(1)
}

onMounted(() => {
  loadAll()
  window.addEventListener('keydown', onKeydown)
})
watch(() => route.params.id, id => {
  if (id != null && Number(id) !== imageId.value) {
    imageId.value = Number(id)
    imageUrl.value = ''
    loadAll()
  }
})
onBeforeUnmount(() => window.removeEventListener('keydown', onKeydown))
</script>

<template>
  <div class="damage-view">
    <div class="toolbar">
      <NButton @click="router.push(`/annotate/${imageId}`)">返回字标注</NButton>
      <span class="filename">{{ image?.filename ?? '' }}</span>
      <NSelect v-model:value="damageType" :options="TYPE_OPTIONS" style="width: 220px" size="small" />
      <span style="font-size: 12px">笔刷</span>
      <NSlider v-model:value="radius" :min="2" :max="80" style="width: 120px" />
      <NInputNumber v-model:value="radius" :min="2" :max="80" size="small" style="width: 70px" />
      <label class="toggle"><NSwitch v-model:value="erasing" /> 橡皮 (E)</label>
      <span class="spacer" />
      <label class="toggle"><NSwitch v-model:value="brushing" /> 笔刷 (B)</label>
      <NButton size="small" :disabled="!draft.length" @click="undoDraft">撤销一笔</NButton>
      <NButton size="small" @click="go(-1)">← 上一页</NButton>
      <NButton size="small" @click="go(1)">下一页 →</NButton>
      <NButton size="small" type="primary" :disabled="!draft.length" @click="saveDraft">
        保存区域（{{ draft.length }} 笔）
      </NButton>
    </div>
    <div class="body">
      <NSpin :show="loading" class="canvas-wrap">
        <DamageCanvas
          v-if="imageUrl"
          :image-url="imageUrl"
          :scale="scale"
          :regions="regionViews"
          :draft="draft"
          :brushing="brushing"
          :brush-radius="radius"
          :brush-erase="erasing"
          @add-stroke="onAddStroke"
        />
      </NSpin>
      <div class="sidebar">
        <NScrollbar>
          <div v-if="!regions.length && !loading" class="empty">
            <NEmpty description="暂无破损区域，直接动笔" />
          </div>
          <div v-for="r in regions" :key="r.id" class="region-row">
            <NTag size="small" :type="TYPE_TAG[r.damage_type]">
              {{ TYPE_LABEL[r.damage_type] ?? r.damage_type }}
            </NTag>
            <span class="rid">#{{ r.id }}</span>
            <NSelect
              size="tiny" :value="r.damage_type" :options="TYPE_OPTIONS"
              style="width: 150px" @update:value="(v: string) => retype(r, v)"
            />
            <NButton size="tiny" quaternary @click="removeRegion(r)">✕</NButton>
          </div>
        </NScrollbar>
      </div>
    </div>
  </div>
</template>

<style scoped>
.damage-view { display: flex; flex-direction: column; height: 100%; }
.toolbar {
  display: flex; align-items: center; gap: 8px;
  padding: 8px 12px; border-bottom: 1px solid #eee; flex-shrink: 0;
}
.filename { font-weight: 600; }
.spacer { flex: 1; }
.toggle { display: flex; align-items: center; gap: 4px; cursor: pointer; font-size: 13px; }
.body { display: flex; flex: 1; min-height: 0; }
.canvas-wrap { flex: 1; min-width: 0; }
.sidebar {
  width: 300px; flex-shrink: 0; border-left: 1px solid #eee;
  display: flex; flex-direction: column;
}
.empty { padding: 40px 0; }
.region-row {
  display: flex; align-items: center; gap: 6px;
  padding: 6px 8px; border-bottom: 1px solid #f5f5f5;
}
.rid { font-size: 12px; color: #999; }
</style>
