<script setup lang="ts">
/**
 * 仪表盘：项目数据总览（页面/标注/裁剪/风格/破损）+ 最近任务与导出 + 备份。
 */
import { onMounted, ref } from 'vue'
import {
  NButton, NCard, NEmpty, NGrid, NGi, NProgress, NSpace, NStatistic,
  NTable, NTag, useMessage,
} from 'naive-ui'
import { api, type Stats } from '../api'

const message = useMessage()
const data = ref<Stats | null>(null)
const backingUp = ref(false)

const PAGE_STATUS_LABEL: Record<string, string> = {
  unannotated: '未标注', auto_labeled: '自动标注', in_review: '复查中',
  reviewed: '已复查', exported: '已导出',
}
const JOB_STATUS_TYPE: Record<string, 'success' | 'warning' | 'error' | 'info' | 'default'> = {
  done: 'success', running: 'warning', pending: 'info',
  failed: 'error', canceled: 'default',
}

function sum(obj: Record<string, number>) {
  return Object.values(obj).reduce((a, b) => a + b, 0)
}

async function load() {
  data.value = await api.getStats()
}

async function doBackup() {
  backingUp.value = true
  try {
    const r = await api.backup()
    message.success(`已备份 data/${r.path}（${r.size_mb} MB）`)
  } finally {
    backingUp.value = false
  }
}

onMounted(load)
</script>

<template>
  <div>
    <n-space style="margin-bottom: 12px" align="center">
      <h3 style="margin: 0">数据总览</h3>
      <n-button @click="load">刷新</n-button>
      <n-button type="primary" :loading="backingUp" @click="doBackup">备份数据库</n-button>
    </n-space>

    <n-empty v-if="!data" description="加载中…" />
    <n-grid v-else :cols="2" :x-gap="12" :y-gap="12">
      <n-gi v-for="p in data.projects" :key="p.id">
        <n-card :title="`#${p.id} ${p.name}`" size="small">
          <n-space>
            <n-statistic label="页面" :value="sum(p.images)" />
            <n-statistic label="标注" :value="sum(p.annotations)" />
            <n-statistic label="裁剪" :value="sum(p.crops)" />
            <n-statistic label="风格" :value="p.styles" />
            <n-statistic label="破损区域" :value="p.damage_regions" />
          </n-space>
          <n-table size="small" style="margin-top: 8px" :bordered="false">
            <tbody>
              <tr>
                <td>页面状态</td>
                <td>
                  <n-tag v-for="(n, s) in p.images" :key="s" size="tiny" style="margin-right: 4px">
                    {{ PAGE_STATUS_LABEL[s] ?? s }} {{ n }}
                  </n-tag>
                </td>
              </tr>
              <tr>
                <td>官方划分</td>
                <td>
                  <n-tag v-for="(n, s) in p.splits" :key="s" size="tiny" style="margin-right: 4px">
                    {{ s }} {{ n }}
                  </n-tag>
                </td>
              </tr>
              <tr>
                <td>标注来源</td>
                <td>
                  <n-tag v-for="(n, s) in p.annotation_origins" :key="s" size="tiny" style="margin-right: 4px">
                    {{ s }} {{ n }}
                  </n-tag>
                </td>
              </tr>
              <tr>
                <td>标注状态</td>
                <td>
                  <n-tag v-for="(n, s) in p.annotations" :key="s" size="tiny" style="margin-right: 4px">
                    {{ s }} {{ n }}
                  </n-tag>
                </td>
              </tr>
            </tbody>
          </n-table>
        </n-card>
      </n-gi>

      <n-gi>
        <n-card title="最近任务" size="small">
          <div v-for="j in data.recent_jobs" :key="j.id" class="job-row">
            <span class="jid">#{{ j.id }}</span>
            <span class="jtype">{{ j.job_type }}</span>
            <n-tag size="tiny" :type="JOB_STATUS_TYPE[j.status]">{{ j.status }}</n-tag>
            <n-progress
              v-if="j.status === 'running'" type="line" :percentage="Math.round(j.progress * 100)"
              style="flex: 1" :height="10"
            />
            <span v-else style="flex: 1" />
            <span class="jtime">{{ j.created_at.slice(5, 16) }}</span>
          </div>
        </n-card>
      </n-gi>
      <n-gi>
        <n-card title="最近导出" size="small">
          <div v-for="e in data.recent_exports" :key="e.id" class="job-row">
            <span class="jid">#{{ e.id }}</span>
            <span class="jtype">{{ e.kind }}</span>
            <n-tag size="tiny" :type="e.status === 'done' ? 'success' : 'error'">{{ e.status }}</n-tag>
            <span style="flex: 1; font-size: 12px; color: #888">{{ e.output_path }}</span>
            <span class="jtime">{{ e.created_at.slice(5, 16) }}</span>
          </div>
        </n-card>
      </n-gi>
    </n-grid>
  </div>
</template>

<style scoped>
.job-row { display: flex; align-items: center; gap: 8px; padding: 3px 0; }
.jid { color: #999; font-size: 12px; width: 36px; }
.jtype { width: 150px; font-size: 13px; }
.jtime { color: #999; font-size: 12px; }
</style>
