<script setup lang="ts">
/**
 * 字符标注页：左侧 Konva 画布，右侧标注列表（竖排阅读顺序：x1 降序、y1 升序）。
 * 快捷键：D 画框模式、Delete 删除选中、Enter 确认选中、←/→ 前后页。
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NButton, NEmpty, NInput, NScrollbar, NSpin, NSwitch, NTag, useMessage } from 'naive-ui'
import BoxCanvas, { type AnnoBox } from '../components/BoxCanvas.vue'
import { api, type Annotation, type ImageItem } from '../api'

const route = useRoute()
const router = useRouter()
const message = useMessage()

const imageId = ref(Number(route.params.id))
const image = ref<ImageItem | null>(null)
const annotations = ref<Annotation[]>([])
const selectedId = ref<number | null>(null)
const drawing = ref(false)
const loading = ref(true)
const projectImages = ref<ImageItem[]>([])  // 用于前后页导航

const selected = computed(() => annotations.value.find(a => a.id === selectedId.value) ?? null)
const boxes = computed<AnnoBox[]>(() => annotations.value.map(a => ({ ...a })))

const scale = ref(1)
const imageUrl = ref('')

const counts = computed(() => {
  const c = { auto: 0, confirmed: 0, edited: 0 }
  for (const a of annotations.value) if (a.status in c) c[a.status as keyof typeof c]++
  return c
})

/** 拉取展示图的实际像素尺寸（浏览器解码后），用于换算 原图/展示图 比例。 */
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
  selectedId.value = null
  try {
    image.value = await api.getImage(imageId.value)
    annotations.value = await api.listAnnotations(imageId.value)
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
  if (next != null) router.push(`/annotate/${next}`)
  else message.info(delta > 0 ? '已是最后一页' : '已是第一页')
}

async function onCreateBox(box: { x1: number; y1: number; x2: number; y2: number }) {
  const anno = await api.createAnnotation(imageId.value, box)
  annotations.value.push(anno)
  selectedId.value = anno.id
  message.success('已添加标注')
}

async function onUpdateBox(id: number, box: { x1: number; y1: number; x2: number; y2: number }) {
  const anno = await api.patchAnnotation(id, box)
  const idx = annotations.value.findIndex(a => a.id === id)
  if (idx >= 0) annotations.value[idx] = anno
}

async function onCharInput(id: number, char: string) {
  const anno = await api.patchAnnotation(id, { char })
  const idx = annotations.value.findIndex(a => a.id === id)
  if (idx >= 0) annotations.value[idx] = anno
}

async function confirmOne(id: number) {
  const anno = await api.patchAnnotation(id, { status: 'confirmed' })
  const idx = annotations.value.findIndex(a => a.id === id)
  if (idx >= 0) annotations.value[idx] = anno
}

async function removeOne(id: number) {
  await api.deleteAnnotation(id)
  annotations.value = annotations.value.filter(a => a.id !== id)
  if (selectedId.value === id) selectedId.value = null
}

async function confirmAll() {
  const ids = annotations.value.filter(a => a.status !== 'confirmed').map(a => a.id)
  if (!ids.length) return message.info('没有待确认的标注')
  const r = await api.bulkStatus(ids, 'confirmed')
  annotations.value = annotations.value.map(a =>
    ids.includes(a.id) ? { ...a, status: 'confirmed' } : a)
  message.success(`已确认 ${r.count} 条`)
}

async function runOcr() {
  if (!image.value) return
  await api.startOcr(image.value.project_id, [imageId.value])
  message.success('OCR 任务已提交（约 40 秒/页，完成后刷新本页）')
}

const STATUS_TYPE: Record<string, 'warning' | 'success' | 'info'> = {
  auto: 'warning', confirmed: 'success', edited: 'info',
}
const STATUS_LABEL: Record<string, string> = {
  auto: '自动', confirmed: '已确认', edited: '已修改',
}

function onKeydown(e: KeyboardEvent) {
  const tag = (e.target as HTMLElement).tagName
  if (tag === 'INPUT' || tag === 'TEXTAREA') return
  if (e.key === 'd' || e.key === 'D') drawing.value = !drawing.value
  else if (e.key === 'Delete' && selectedId.value != null) removeOne(selectedId.value)
  else if (e.key === 'Enter' && selectedId.value != null) confirmOne(selectedId.value)
  else if (e.key === 'ArrowLeft') go(-1)
  else if (e.key === 'ArrowRight') go(1)
}

onMounted(() => {
  loadAll()
  window.addEventListener('keydown', onKeydown)
})
// 同组件内切换页面（上一页/下一页）时重载
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
  <div class="annotate-view">
    <div class="toolbar">
      <NButton @click="router.back()">返回</NButton>
      <span class="filename">{{ image?.filename ?? '' }}</span>
      <NTag :type="STATUS_TYPE[a] ?? 'default'" v-for="(n, a) in counts" :key="a">
        {{ STATUS_LABEL[a] }} {{ n }}
      </NTag>
      <span class="spacer" />
      <label class="draw-toggle">
        <NSwitch v-model:value="drawing" /> 画框 (D)
      </label>
      <NButton size="small" @click="go(-1)">← 上一页</NButton>
      <NButton size="small" @click="go(1)">下一页 →</NButton>
      <NButton size="small" @click="runOcr">OCR 本页</NButton>
      <NButton size="small" @click="router.push(`/damage/${imageId}`)">破损标注 →</NButton>
      <NButton size="small" type="primary" @click="confirmAll">整页确认</NButton>
    </div>
    <div class="body">
      <NSpin :show="loading" class="canvas-wrap">
        <BoxCanvas
          v-if="imageUrl"
          :image-url="imageUrl"
          :scale="scale"
          :annotations="boxes"
          :selected-id="selectedId"
          :drawing="drawing"
          @select="id => (selectedId = id)"
          @update-box="onUpdateBox"
          @create-box="onCreateBox"
        />
      </NSpin>
      <div class="sidebar">
        <NScrollbar>
          <div v-if="!annotations.length && !loading" class="empty">
            <NEmpty description="暂无标注，按 D 画框" />
          </div>
          <div
            v-for="a in annotations"
            :key="a.id"
            class="anno-row"
            :class="{ active: a.id === selectedId }"
            @click="selectedId = a.id"
          >
            <NTag size="small" :type="STATUS_TYPE[a.status] ?? 'default'">
              {{ STATUS_LABEL[a.status] ?? a.status }}
            </NTag>
            <NInput
              size="small"
              class="char-input"
              :value="a.char ?? ''"
              placeholder="字"
              @update:value="v => onCharInput(a.id, v)"
            />
            <span class="coord">{{ a.x2 - a.x1 }}×{{ a.y2 - a.y1 }}</span>
            <NButton size="tiny" quaternary @click.stop="confirmOne(a.id)">✓</NButton>
            <NButton size="tiny" quaternary @click.stop="removeOne(a.id)">✕</NButton>
          </div>
        </NScrollbar>
      </div>
    </div>
  </div>
</template>

<style scoped>
.annotate-view { display: flex; flex-direction: column; height: 100%; }
.toolbar {
  display: flex; align-items: center; gap: 8px;
  padding: 8px 12px; border-bottom: 1px solid #eee; flex-shrink: 0;
}
.filename { font-weight: 600; }
.spacer { flex: 1; }
.draw-toggle { display: flex; align-items: center; gap: 4px; cursor: pointer; }
.body { display: flex; flex: 1; min-height: 0; }
.canvas-wrap { flex: 1; min-width: 0; }
.sidebar {
  width: 320px; flex-shrink: 0; border-left: 1px solid #eee;
  display: flex; flex-direction: column;
}
.empty { padding: 40px 0; }
.anno-row {
  display: flex; align-items: center; gap: 6px;
  padding: 4px 8px; cursor: pointer; border-bottom: 1px solid #f5f5f5;
}
.anno-row:hover { background: #f8f8f8; }
.anno-row.active { background: #e8f0fe; }
.char-input { width: 56px; }
.coord { font-size: 12px; color: #999; flex: 1; }
</style>
