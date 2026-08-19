<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import {
  NButton, NDataTable, NModal, NProgress, NSpace, NTag, useMessage,
} from 'naive-ui'
import type { DataTableColumns } from 'naive-ui'
import { h } from 'vue'
import { api, type Job } from '../api'

const message = useMessage()
const jobs = ref<Job[]>([])
const logJob = ref<Job | null>(null)
let timer: number | undefined

const statusType: Record<string, 'default' | 'info' | 'success' | 'error' | 'warning'> = {
  pending: 'default', running: 'info', done: 'success', failed: 'error', canceled: 'warning',
}

const columns: DataTableColumns<Job> = [
  { title: 'ID', key: 'id', width: 60 },
  { title: '类型', key: 'job_type', width: 140 },
  {
    title: '状态', key: 'status', width: 100,
    render: (row) => h(NTag, { size: 'small', type: statusType[row.status] ?? 'default' }, { default: () => row.status }),
  },
  {
    title: '进度', key: 'progress', width: 180,
    render: (row) => h(NProgress, { type: 'line', percentage: Math.round(row.progress * 100), height: 14 }),
  },
  { title: '创建时间', key: 'created_at', width: 170 },
  {
    title: '操作', key: 'actions', width: 180,
    render: (row) => h(NSpace, { size: 'small' }, {
      default: () => [
        h(NButton, { size: 'tiny', onClick: () => (logJob.value = row) }, { default: () => '日志' }),
        (row.status === 'pending' || row.status === 'running')
          ? h(NButton, { size: 'tiny', type: 'error', onClick: () => cancel(row) }, { default: () => '取消' })
          : null,
      ],
    }),
  },
]

async function load() {
  jobs.value = await api.listJobs()
}

async function cancel(job: Job) {
  await api.cancelJob(job.id)
  message.info('已请求取消')
  load()
}

async function runDummy() {
  await api.dummyJob()
  message.success('假任务已提交')
  load()
}

onMounted(() => {
  load()
  timer = window.setInterval(load, 2000)
})
onUnmounted(() => window.clearInterval(timer))
</script>

<template>
  <div>
    <n-space style="margin-bottom: 12px">
      <n-button @click="runDummy">提交假任务（冒烟测试）</n-button>
      <n-button @click="load">刷新</n-button>
    </n-space>
    <n-data-table :columns="columns" :data="jobs" :pagination="false" size="small" />

    <n-modal :show="!!logJob" preset="card" :title="`任务 #${logJob?.id} 日志`" style="width: 640px" @update:show="logJob = null">
      <pre style="white-space: pre-wrap; font-size: 12px; max-height: 400px; overflow: auto">{{ logJob?.log || '（暂无日志）' }}</pre>
    </n-modal>
  </div>
</template>
