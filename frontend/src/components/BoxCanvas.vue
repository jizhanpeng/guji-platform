<script setup lang="ts">
/**
 * 字符框标注画布（Konva）。
 * - 展示图坐标系 = 原图坐标 × scale；对外收发一律用原图坐标
 * - 画框模式：mousedown 拖出新框；非画框模式：拖动平移、滚轮缩放、点选/变换框
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

export interface AnnoBox {
  id: number
  x1: number
  y1: number
  x2: number
  y2: number
  char: string | null
  status: string
}

const props = defineProps<{
  imageUrl: string
  scale: number          // 展示图 / 原图
  annotations: AnnoBox[]
  selectedId: number | null
  drawing: boolean
}>()

const emit = defineEmits<{
  select: [id: number | null]
  updateBox: [id: number, box: { x1: number; y1: number; x2: number; y2: number }]
  createBox: [box: { x1: number; y1: number; x2: number; y2: number }]
}>()

const STATUS_COLOR: Record<string, string> = {
  auto: '#f0a020',
  confirmed: '#18a058',
  edited: '#2080f0',
}

const containerRef = ref<HTMLDivElement>()
const stageRef = ref<any>()
const imageObj = ref<HTMLImageElement | null>(null)
const stageSize = ref({ width: 800, height: 600 })
const stageScale = ref(1)
const stagePos = ref({ x: 0, y: 0 })

// 正在绘制的新框（stage 坐标）
const draft = ref<{ x: number; y: number; w: number; h: number } | null>(null)

const displayBoxes = computed(() =>
  props.annotations.map(a => ({
    id: a.id,
    x: a.x1 * props.scale,
    y: a.y1 * props.scale,
    w: (a.x2 - a.x1) * props.scale,
    h: (a.y2 - a.y1) * props.scale,
    stroke: STATUS_COLOR[a.status] ?? '#999',
  })),
)

function loadImage() {
  const img = new window.Image()
  img.src = props.imageUrl
  img.onload = () => {
    imageObj.value = img
    fitToContainer()
  }
  img.onerror = () => (imageObj.value = null)
}

function fitToContainer() {
  if (!imageObj.value || !containerRef.value) return
  const cw = containerRef.value.clientWidth
  const ch = containerRef.value.clientHeight
  stageSize.value = { width: cw, height: ch }
  const s = Math.min(cw / imageObj.value.width, ch / imageObj.value.height) * 0.98
  stageScale.value = s
  stagePos.value = {
    x: (cw - imageObj.value.width * s) / 2,
    y: (ch - imageObj.value.height * s) / 2,
  }
}

function onWheel(e: any) {
  e.evt.preventDefault()
  const stage = stageRef.value?.getNode()
  if (!stage) return
  const pointer = stage.getPointerPosition()
  if (!pointer) return
  const old = stageScale.value
  const factor = e.evt.deltaY > 0 ? 0.9 : 1.1
  const next = Math.min(20, Math.max(0.05, old * factor))
  const world = {
    x: (pointer.x - stagePos.value.x) / old,
    y: (pointer.y - stagePos.value.y) / old,
  }
  stageScale.value = next
  stagePos.value = { x: pointer.x - world.x * next, y: pointer.y - world.y * next }
}

function pointerInStage(): { x: number; y: number } | null {
  const stage = stageRef.value?.getNode()
  if (!stage) return null
  const p = stage.getPointerPosition()
  if (!p) return null
  return {
    x: (p.x - stagePos.value.x) / stageScale.value,
    y: (p.y - stagePos.value.y) / stageScale.value,
  }
}

function onMouseDown() {
  if (!props.drawing) return
  const p = pointerInStage()
  if (p) draft.value = { x: p.x, y: p.y, w: 0, h: 0 }
}

function onMouseMove() {
  if (!props.drawing || !draft.value) return
  const p = pointerInStage()
  if (!p) return
  draft.value.w = p.x - draft.value.x
  draft.value.h = p.y - draft.value.y
}

function onMouseUp() {
  if (!props.drawing || !draft.value) return
  const d = draft.value
  draft.value = null
  const x = Math.min(d.x, d.x + d.w)
  const y = Math.min(d.y, d.y + d.h)
  const w = Math.abs(d.w)
  const h = Math.abs(d.h)
  if (w < 5 || h < 5) return  // 误触忽略
  emit('createBox', {
    x1: Math.round(x / props.scale),
    y1: Math.round(y / props.scale),
    x2: Math.round((x + w) / props.scale),
    y2: Math.round((y + h) / props.scale),
  })
}

function onBoxDragEnd(id: number, e: any) {
  const n = e.target
  emit('updateBox', id, {
    x1: Math.round(n.x() / props.scale),
    y1: Math.round(n.y() / props.scale),
    x2: Math.round((n.x() + n.width()) / props.scale),
    y2: Math.round((n.y() + n.height()) / props.scale),
  })
}

function onBoxTransformEnd(id: number, e: any) {
  const n = e.target
  // 把缩放烘进宽高并复位
  const w = n.width() * n.scaleX()
  const h = n.height() * n.scaleY()
  n.scaleX(1)
  n.scaleY(1)
  emit('updateBox', id, {
    x1: Math.round(n.x() / props.scale),
    y1: Math.round(n.y() / props.scale),
    x2: Math.round((n.x() + w) / props.scale),
    y2: Math.round((n.y() + h) / props.scale),
  })
}

const transformerRef = ref<any>()

function syncTransformer() {
  const tr = transformerRef.value?.getNode()
  const stage = stageRef.value?.getNode()
  if (!tr || !stage) return
  if (props.selectedId == null) {
    tr.nodes([])
    return
  }
  const node = stage.findOne(`#box-${props.selectedId}`)
  tr.nodes(node ? [node] : [])
}

watch(() => props.selectedId, syncTransformer)
watch(() => props.annotations, syncTransformer, { deep: true })
watch(() => props.imageUrl, loadImage)

let ro: ResizeObserver | null = null
onMounted(() => {
  loadImage()
  if (containerRef.value) {
    ro = new ResizeObserver(fitToContainer)
    ro.observe(containerRef.value)
  }
})
onBeforeUnmount(() => ro?.disconnect())
</script>

<template>
  <div ref="containerRef" class="box-canvas">
    <v-stage
      ref="stageRef"
      :config="{
        width: stageSize.width,
        height: stageSize.height,
        scaleX: stageScale,
        scaleY: stageScale,
        x: stagePos.x,
        y: stagePos.y,
        draggable: !drawing,
      }"
      @wheel="onWheel"
      @mousedown="onMouseDown"
      @mousemove="onMouseMove"
      @mouseup="onMouseUp"
      @dragend="stagePos = { x: $event.target.x(), y: $event.target.y() }"
    >
      <v-layer :listening="false">
        <v-image v-if="imageObj" :config="{ image: imageObj }" />
      </v-layer>
      <v-layer>
        <v-rect
          v-for="b in displayBoxes"
          :key="b.id"
          :config="{
            id: `box-${b.id}`,
            x: b.x,
            y: b.y,
            width: b.w,
            height: b.h,
            stroke: b.stroke,
            strokeWidth: 2,
            strokeScaleEnabled: false,
            draggable: !drawing,
            opacity: b.id === selectedId ? 1 : 0.75,
          }"
          @mousedown.stop="!drawing && emit('select', b.id)"
          @dragend="onBoxDragEnd(b.id, $event)"
          @transformend="onBoxTransformEnd(b.id, $event)"
        />
        <v-rect
          v-if="draft"
          :config="{
            x: draft.x, y: draft.y, width: draft.w, height: draft.h,
            stroke: '#ff4d4f', strokeWidth: 2, strokeScaleEnabled: false,
            dash: [6, 4], listening: false,
          }"
        />
        <v-transformer ref="transformerRef" :config="{ rotateEnabled: false, keepRatio: false }" />
      </v-layer>
    </v-stage>
  </div>
</template>

<style scoped>
.box-canvas {
  width: 100%;
  height: 100%;
  background: #1f1f1f;
  overflow: hidden;
}
</style>
