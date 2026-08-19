<script setup lang="ts">
import { onMounted, ref } from 'vue'
import {
  NButton, NCard, NEmpty, NForm, NFormItem, NGrid, NGi, NInput, NModal,
  NPagination, NSelect, NSpace, NTag, useMessage,
} from 'naive-ui'
import { api, type ImageItem, type Project } from '../api'

const message = useMessage()

const projects = ref<Project[]>([])
const currentProjectId = ref<number | null>(null)
const images = ref<ImageItem[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 60
const statusFilter = ref<string | null>(null)
const loading = ref(false)

const showCreate = ref(false)
const createForm = ref({ name: '', kind: 'scans', notes: '' })
const showImport = ref(false)
const importForm = ref({ folder: '', source: 'scan' })

const statusOptions = [
  { label: '全部', value: '' },
  { label: '未标注', value: 'unannotated' },
  { label: '已自动标注', value: 'auto_labeled' },
  { label: '已复查', value: 'reviewed' },
  { label: '已导出', value: 'exported' },
]

async function loadProjects() {
  projects.value = await api.listProjects()
  if (!currentProjectId.value && projects.value.length) {
    currentProjectId.value = projects.value[0].id
  }
}

async function loadImages() {
  loading.value = true
  try {
    const res = await api.listImages({
      project_id: currentProjectId.value ?? undefined,
      status: statusFilter.value || undefined,
      page: page.value,
      page_size: pageSize,
    })
    images.value = res.items
    total.value = res.total
  } finally {
    loading.value = false
  }
}

async function createProject() {
  if (!createForm.value.name) return message.warning('请填写项目名')
  await api.createProject({ ...createForm.value })
  showCreate.value = false
  createForm.value = { name: '', kind: 'scans', notes: '' }
  await loadProjects()
  message.success('项目已创建')
}

async function importFolder() {
  if (!currentProjectId.value) return message.warning('请先选择项目')
  if (!importForm.value.folder) return message.warning('请填写文件夹路径')
  try {
    await api.importFolder(currentProjectId.value, importForm.value.folder, importForm.value.source)
    showImport.value = false
    message.success('导入任务已提交，请到「任务中心」查看进度')
  } catch (e: any) {
    message.error(e.message)
  }
}

function onProjectChange() {
  page.value = 1
  loadImages()
}

onMounted(async () => {
  await loadProjects()
  await loadImages()
})
</script>

<template>
  <div>
    <n-space style="margin-bottom: 12px" align="center">
      <n-select
        v-model:value="currentProjectId"
        :options="projects.map(p => ({ label: `${p.name} (${p.image_count})`, value: p.id }))"
        placeholder="选择项目"
        style="width: 240px"
        @update:value="onProjectChange"
      />
      <n-button @click="showCreate = true">新建项目</n-button>
      <n-button type="primary" :disabled="!currentProjectId" @click="showImport = true">
        导入文件夹
      </n-button>
      <n-select
        v-model:value="statusFilter"
        :options="statusOptions"
        style="width: 140px"
        @update:value="(v: string) => { statusFilter = v || null; page = 1; loadImages() }"
      />
      <n-button :loading="loading" @click="loadImages">刷新</n-button>
    </n-space>

    <n-empty v-if="!images.length && !loading" description="暂无图像，点击「导入文件夹」开始" />

    <n-grid :cols="6" :x-gap="12" :y-gap="12">
      <n-gi v-for="img in images" :key="img.id">
        <n-card size="small" :title="img.filename" :header-style="{ fontSize: '12px' }">
          <template #cover>
            <img :src="api.imageFileUrl(img.id, 'thumb')" style="width: 100%; height: 160px; object-fit: contain; background: #f5f5f5" />
          </template>
          <n-space size="small">
            <n-tag size="small">{{ img.status }}</n-tag>
            <span style="font-size: 12px; color: #999">{{ img.width }}×{{ img.height }}</span>
          </n-space>
        </n-card>
      </n-gi>
    </n-grid>

    <n-pagination
      v-model:page="page"
      :item-count="total"
      :page-size="pageSize"
      style="margin-top: 16px; justify-content: center"
      @update:page="loadImages"
    />

    <n-modal v-model:show="showCreate" preset="card" title="新建项目" style="width: 480px">
      <n-form>
        <n-form-item label="项目名"><n-input v-model:value="createForm.name" /></n-form-item>
        <n-form-item label="类型">
          <n-select v-model:value="createForm.kind" :options="[
            { label: '自有扫描件', value: 'scans' },
            { label: 'M5HisDoc', value: 'm5hisdoc' },
            { label: '其他', value: 'other' },
          ]" />
        </n-form-item>
        <n-form-item label="备注"><n-input v-model:value="createForm.notes" type="textarea" /></n-form-item>
      </n-form>
      <template #footer><n-button type="primary" @click="createProject">创建</n-button></template>
    </n-modal>

    <n-modal v-model:show="showImport" preset="card" title="导入文件夹" style="width: 520px">
      <n-form>
        <n-form-item label="文件夹路径（服务器本机绝对路径）">
          <n-input v-model:value="importForm.folder" placeholder="D:\path\to\pages" />
        </n-form-item>
        <n-form-item label="来源">
          <n-select v-model:value="importForm.source" :options="[
            { label: '自有扫描件', value: 'scan' },
            { label: '其他', value: 'other' },
          ]" />
        </n-form-item>
      </n-form>
      <template #footer><n-button type="primary" @click="importFolder">提交导入任务</n-button></template>
    </n-modal>
  </div>
</template>
