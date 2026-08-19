/** API 客户端：轻量 fetch 封装。 */
const BASE = '/api'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(BASE + path, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!resp.ok) {
    const text = await resp.text()
    throw new Error(`${resp.status} ${text}`)
  }
  return resp.json()
}

export interface Project {
  id: number
  name: string
  kind: string
  source_path: string | null
  notes: string | null
  created_at: string
  image_count: number
}

export interface ImageItem {
  id: number
  project_id: number
  filename: string
  width: number
  height: number
  source: string
  official_split: string | null
  style_id: number | null
  status: string
  created_at: string
}

export interface Job {
  id: number
  job_type: string
  payload_json: string
  status: string
  progress: number
  log: string
  created_at: string
  started_at: string | null
  finished_at: string | null
}

export interface Annotation {
  id: number
  image_id: number
  x1: number
  y1: number
  x2: number
  y2: number
  char: string | null
  origin: string
  confidence: number | null
  status: string
}

export interface ExportItem {
  id: number
  kind: string
  params_json: string
  output_path: string | null
  status: string
  created_at: string
}

export interface Style {
  id: number
  name: string
  method: string
  notes: string | null
  locked_split: string | null
  image_count: number
  splits: Record<string, number>
}

export interface Crop {
  id: number
  image_id: number
  char_annotation_id: number | null
  style_id: number | null
  char: string | null
  crop_path: string
  crop_kind: string
  scale_ratio: number
  status: string
  created_at: string
}

export interface CharsetEntry {
  char: string
  instance_count: number
  renderable: boolean
  render_font: string | null
  in_trainset: boolean
  is_holdout: boolean
  median_box_px: number | null
  content_image_path: string | null
}

export interface Stroke {
  points: number[][]
  radius: number
  erase?: boolean
}

export interface DamageRegion {
  id: number
  image_id: number
  damage_type: string
  strokes_json: string | null
  mask_path: string | null
  origin: string
  status: string
  created_at: string
}

export const api = {
  listProjects: () => request<Project[]>('/projects'),
  createProject: (body: { name: string; kind: string; source_path?: string; notes?: string }) =>
    request<Project>('/projects', { method: 'POST', body: JSON.stringify(body) }),
  importFolder: (projectId: number, folder: string, source = 'scan') =>
    request<Job>(`/projects/${projectId}/import-folder`, {
      method: 'POST',
      body: JSON.stringify({ folder, source }),
    }),
  listImages: (params: { project_id?: number; status?: string; page?: number; page_size?: number }) => {
    const qs = new URLSearchParams()
    if (params.project_id) qs.set('project_id', String(params.project_id))
    if (params.status) qs.set('status', params.status)
    qs.set('page', String(params.page ?? 1))
    qs.set('page_size', String(params.page_size ?? 60))
    return request<{ total: number; items: ImageItem[] }>(`/images?${qs}`)
  },
  imageFileUrl: (id: number, variant: 'thumb' | 'display' | 'original' = 'thumb') =>
    `${BASE}/images/${id}/file?variant=${variant}`,
  getImage: (id: number) => request<ImageItem>(`/images/${id}`),
  listJobs: (limit = 50) => request<Job[]>(`/jobs?limit=${limit}`),
  cancelJob: (id: number) => request<{ ok: boolean }>(`/jobs/${id}/cancel`, { method: 'POST' }),
  dummyJob: () => request<Job>('/jobs/dummy', { method: 'POST' }),
  importM5HisDoc: (projectId: number, root: string, subset: string) =>
    request<Job>(`/projects/${projectId}/import-m5hisdoc`, {
      method: 'POST',
      body: JSON.stringify({ root, subset }),
    }),
  listAnnotations: (imageId: number) => request<Annotation[]>(`/images/${imageId}/char-annotations`),
  createAnnotation: (imageId: number, box: { x1: number; y1: number; x2: number; y2: number; char?: string }) =>
    request<Annotation>(`/images/${imageId}/char-annotations`, {
      method: 'POST',
      body: JSON.stringify(box),
    }),
  patchAnnotation: (id: number, patch: Partial<{ x1: number; y1: number; x2: number; y2: number; char: string; status: string }>) =>
    request<Annotation>(`/char-annotations/${id}`, { method: 'PATCH', body: JSON.stringify(patch) }),
  deleteAnnotation: (id: number) =>
    request<{ ok: boolean }>(`/char-annotations/${id}`, { method: 'DELETE' }),
  bulkStatus: (ids: number[], status: string) =>
    request<{ ok: boolean; count: number }>('/char-annotations/bulk-status', {
      method: 'POST',
      body: JSON.stringify({ ids, status }),
    }),
  listExports: () => request<ExportItem[]>('/exports'),
  exportCsv: (imageIds: number[]) =>
    request<ExportItem>('/exports/m5hisdoc-csv', {
      method: 'POST',
      body: JSON.stringify({ image_ids: imageIds }),
    }),
  listStyles: (projectId: number) => request<Style[]>(`/projects/${projectId}/styles`),
  createStyle: (projectId: number, name: string) =>
    request<Style>(`/projects/${projectId}/styles`, {
      method: 'POST',
      body: JSON.stringify({ name }),
    }),
  patchStyle: (id: number, patch: Partial<{ name: string; notes: string; locked_split: string | null }>) =>
    request<Style>(`/styles/${id}`, { method: 'PATCH', body: JSON.stringify(patch) }),
  moveImageStyle: (imageId: number, styleId: number | null, force = false) =>
    request<{ ok: boolean }>(`/images/${imageId}/style`, {
      method: 'POST',
      body: JSON.stringify({ style_id: styleId, force }),
    }),
  styleSheetUrl: (id: number, per = 16) => `${BASE}/styles/${id}/sheet?per=${per}`,
  startEmbed: (projectId: number) =>
    request<Job>('/jobs/embed', { method: 'POST', body: JSON.stringify({ project_id: projectId }) }),
  startCluster: (params: {
    project_id: number; threshold?: number; max_cluster_pages?: number
    merge_radius?: number; dino_only?: boolean; split_policy?: string
  }) => request<Job>('/jobs/cluster', { method: 'POST', body: JSON.stringify(params) }),
  startSubcluster: (styleId: number, threshold: number, dinoOnly = true) =>
    request<Job>(`/styles/${styleId}/subcluster`, {
      method: 'POST',
      body: JSON.stringify({ threshold, dino_only: dinoOnly }),
    }),
  // ---- 方法二：裁剪复查 / 字表 / 数据流水线 ----
  listCrops: (params: {
    project_id: number; status?: string; style_id?: number; char?: string
    page?: number; per?: number
  }) => {
    const qs = new URLSearchParams()
    if (params.status) qs.set('status', params.status)
    if (params.style_id) qs.set('style_id', String(params.style_id))
    if (params.char) qs.set('char', params.char)
    qs.set('page', String(params.page ?? 1))
    qs.set('per', String(params.per ?? 96))
    return request<{ total: number; page: number; per: number; items: Crop[] }>(
      `/projects/${params.project_id}/crops?${qs}`)
  },
  cropStats: (projectId: number) =>
    request<Record<string, number>>(`/projects/${projectId}/crops/stats`),
  cropImageUrl: (id: number) => `${BASE}/crops/${id}/image`,
  patchCrop: (id: number, status: string) =>
    request<Crop>(`/crops/${id}`, { method: 'PATCH', body: JSON.stringify({ status }) }),
  bulkCropStatus: (ids: number[], status: string) =>
    request<{ ok: boolean; count: number }>('/crops/bulk-status', {
      method: 'POST',
      body: JSON.stringify({ ids, status }),
    }),
  listCharset: (projectId: number, page = 1, per = 200) =>
    request<{ total: number; items: CharsetEntry[] }>(
      `/projects/${projectId}/charset?page=${page}&per=${per}`),
  contentImageUrl: (char: string) => `${BASE}/content/${encodeURIComponent(char)}/image`,
  startAutoCrop: (projectId: number) =>
    request<Job>('/jobs/auto_crop', { method: 'POST', body: JSON.stringify({ project_id: projectId }) }),
  startCharset: (projectId: number, minInstances = 20) =>
    request<Job>('/jobs/charset_rebuild', {
      method: 'POST',
      body: JSON.stringify({ project_id: projectId, min_instances: minInstances }),
    }),
  startRender: () =>
    request<Job>('/jobs/render_content', { method: 'POST', body: JSON.stringify({ only_missing: true }) }),
  startFontDatasetExport: (projectId: number) =>
    request<Job>('/jobs/export_fontdataset', {
      method: 'POST',
      body: JSON.stringify({ project_id: projectId }),
    }),
  // ---- 方法一：破损区域 ----
  listDamage: (imageId: number) => request<DamageRegion[]>(`/images/${imageId}/damage-regions`),
  createDamage: (imageId: number, body: { damage_type: string; strokes: Stroke[] }) =>
    request<DamageRegion>(`/images/${imageId}/damage-regions`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  patchDamage: (id: number, patch: Partial<{ damage_type: string; strokes: Stroke[]; status: string }>) =>
    request<DamageRegion>(`/damage-regions/${id}`, { method: 'PATCH', body: JSON.stringify(patch) }),
  deleteDamage: (id: number) =>
    request<{ ok: boolean }>(`/damage-regions/${id}`, { method: 'DELETE' }),
  startOcr: (projectId: number, imageIds?: number[]) =>
    request<Job>('/jobs/ocr', {
      method: 'POST',
      body: JSON.stringify({ project_id: projectId, image_ids: imageIds ?? null }),
    }),
}
