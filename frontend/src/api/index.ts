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
}
