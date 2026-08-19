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
  listJobs: (limit = 50) => request<Job[]>(`/jobs?limit=${limit}`),
  cancelJob: (id: number) => request<{ ok: boolean }>(`/jobs/${id}/cancel`, { method: 'POST' }),
  dummyJob: () => request<Job>('/jobs/dummy', { method: 'POST' }),
}
