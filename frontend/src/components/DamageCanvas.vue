<script setup lang="ts">
/**
 * 破损笔刷画布（Konva）。
 * - 展示图坐标系 = 原图坐标 × scale；对外收发一律用原图坐标
 * - 笔刷模式：mousedown 起笔、move 采样、up 收笔；非笔刷：拖动平移、滚轮缩放
 * - 已保存区域以半透明色线叠加显示；草稿笔画高亮显示
 */
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { Stroke } from '../api'

export interface RegionView {
  id: number
  damage_type: string
  strokes: Stroke[]
}

const props = defineProps<{
  imageUrl: string
  scale: number            // 展示图 / 原图
  regions: RegionView[]    // 已保存区域
  draft: Stroke[]          // 未保存草稿（原图坐标）
  brushing: boolean
  brushRadius: number      // 原图像素
  brushErase: boolean
}>()

const emit = defineEmits<{
  addStroke: [stroke: Stroke]
}>()

const TYPE_COLOR: Record<string, string> = {
  character_missing: '#f0a020',
  paper_damage: '#d03050',
  ink_erosion: '#722ed1',
}

const containerRef = ref<HTMLDivElement>()
const stageRef = ref<any>()
const imageObj = ref<HTMLImageElement | null>(null)
const stageSize = ref({ width: 800, height: 600 })
const stageScale = ref(1)
const stagePos = ref({ x: 0, y: 0 })

// 正在绘制的一笔（展示坐标点列）
const live = ref<number[] | null>(null)

function colorOf(t: string) {
  return TYPE_COLOR[t] ?? '#13c2c2'
}

function toDisplay(strokes: Stroke[]) {
  return strokes.map(s => ({
    points: s.points.flatMap(([x, y]) => [x * props.scale, y * props.scale]),
    width: s.radius * 2 * props.scale,
    erase: !!s.erase,
  }))
}

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
  if (!props.brushing) return
  const p = pointerInStage()
  if (p) live.value = [p.x, p.y]
}

function onMouseMove() {
  if (!props.brushing || !live.value) return
  const p = pointerInStage()
  if (!p) return
  const n = live.value.length
  const dx = p.x - live.value[n - 2]
  const dy = p.y - live.value[n - 1]
  if (dx * dx + dy * dy < 9) return  // 3px 采样间隔（展示坐标）
  live.value.push(p.x, p.y)
}

function onMouseUp() {
  if (!props.brushing || !live.value) return
  const pts = live.value
  live.value = null
  const orig: number[][] = []
  for (let i = 0; i < pts.length; i += 2) {
    orig.push([Math.round(pts[i] / props.scale), Math.round(pts[i + 1] / props.scale)])
  }
  emit('addStroke', { points: orig, radius: props.brushRadius, erase: props.brushErase })
}

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
  <div ref="containerRef" class="damage-canvas">
    <v-stage
      ref="stageRef"
      :config="{
        width: stageSize.width,
        height: stageSize.height,
        scaleX: stageScale,
        scaleY: stageScale,
        x: stagePos.x,
        y: stagePos.y,
        draggable: !brushing,
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
      <v-layer :listening="false">
        <!-- 已保存区域（按类型着色，半透明） -->
        <template v-for="r in regions" :key="r.id">
          <v-line
            v-for="(s, i) in toDisplay(r.strokes)" :key="i"
            :config="{
              points: s.points,
              stroke: colorOf(r.damage_type),
              strokeWidth: s.width,
              opacity: 0.45,
              lineCap: 'round',
              lineJoin: 'round',
              tension: 0.3,
            }"
          />
        </template>
        <!-- 草稿 -->
        <v-line
          v-for="(s, i) in toDisplay(draft)" :key="`d${i}`"
          :config="{
            points: s.points,
            stroke: s.erase ? '#ffffff' : '#ff4d4f',
            strokeWidth: s.width,
            opacity: 0.7,
            lineCap: 'round',
            lineJoin: 'round',
            tension: 0.3,
            dash: s.erase ? [8, 6] : [],
          }"
        />
        <!-- 正在画的一笔 -->
        <v-line
          v-if="live"
          :config="{
            points: live,
            stroke: brushErase ? '#ffffff' : '#ff4d4f',
            strokeWidth: brushRadius * 2 * scale,
            opacity: 0.8,
            lineCap: 'round',
            lineJoin: 'round',
            tension: 0.3,
          }"
        />
      </v-layer>
    </v-stage>
  </div>
</template>

<style scoped>
.damage-canvas {
  width: 100%;
  height: 100%;
  background: #1f1f1f;
  overflow: hidden;
}
</style>
