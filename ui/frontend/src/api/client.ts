import type {
  IdeaOut,
  ContentOut,
  ContentBodyOut,
  PublicationOut,
  TaskStatus,
  MetricsOut,
  PersonaOut,
  DashboardData,
  RecommendBatch,
} from '../types'

const BASE = '/api'

async function get<T>(path: string, params?: Record<string, string | undefined>): Promise<T> {
  const url = new URL(BASE + path, window.location.origin)
  if (params) {
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== '') url.searchParams.set(k, v)
    })
  }
  const res = await fetch(url.toString())
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || res.statusText)
  }
  return res.json()
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(BASE + path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    if (res.status === 409) {
      throw new Error('已达最大并发数（3 个），请稍后再试')
    }
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || res.statusText)
  }
  return res.json()
}

async function patch<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(BASE + path, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || res.statusText)
  }
  return res.json()
}

async function del_<T>(path: string): Promise<T> {
  const res = await fetch(BASE + path, { method: 'DELETE' })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || res.statusText)
  }
  return res.json()
}

async function put<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(BASE + path, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || res.statusText)
  }
  return res.json()
}

export const api = {
  // Personas
  getPersonas: () => get<PersonaOut[]>('/personas'),
  // Dashboard
  getDashboard: (persona_id?: string) => get<DashboardData>('/dashboard', { persona_id }),
  // Ideas
  getIdeas: (status?: string) => get<IdeaOut[]>('/ideas', { status }),
  getIdeaBody: (id: string) => get<{ id: string; title: string; body: string }>(`/ideas/${id}/body`),
  createIdea: (data: { title: string; content: string; tags: string }) => post<IdeaOut>('/ideas', data),
  updateIdea: (id: string, data: { title: string; content: string; tags: string }) => put<IdeaOut>(`/ideas/${id}`, data),
  deleteIdea: (id: string) => del_(`/ideas/${id}`),
  collectIdeas: (source: string) => post<{ task_id: string }>('/tasks/collect', { source }),
  expandIdea: (idea_id: string, instruction: string) => post<{ task_id: string }>('/tasks/expand', { idea_id, instruction }),
  // Contents
  getContents: (params?: { status?: string; platform?: string; persona_id?: string }) => get<ContentOut[]>('/contents', params),
  getContentBody: (id: string) => get<ContentBodyOut>(`/contents/${id}/body`),
  saveContentBody: (id: string, body: string) => put<{ saved: boolean }>(`/contents/${id}/body`, { body }),
  deleteContent: (id: string) => del_(`/contents/${id}`),
  typesetContent: (id: string, opts?: { tool?: string; cover_url?: string; avatar_url?: string }) =>
    post<{ content_id: string; images: string[]; count: number; tool: string }>(`/contents/${id}/typeset`, opts || {}),
  listCovers: () => get<string[]>('/typeset/covers'),
  // Publications
  getPublications: (params?: { status?: string; persona_id?: string }) => get<PublicationOut[]>('/publications', params),
  updatePublication: (pubId: number, data: { status: string; post_url?: string }) =>
    patch<PublicationOut>(`/publications/${pubId}`, data),
  recordMetrics: (pubId: number, data: { views: number; likes: number; collects: number; comments: number; shares: number }) =>
    put<MetricsOut>(`/publications/${pubId}/metrics`, data),
  // Tasks
  createArticle: (data: { idea_id: string; platform: string; persona_id?: string }) => post<{ task_id: string }>('/tasks/create', data),
  reviseContent: (data: { content_id: string; feedback: string }) => post<{ task_id: string }>('/tasks/revise', data),
  getTasks: () => get<TaskStatus[]>('/tasks'),
  getTask: (id: string) => get<TaskStatus>(`/tasks/${id}`),
  retryTask: (id: string) => post<{ task_id: string }>(`/tasks/${id}/retry`, {}),
  // Select
  selectRecommend: (persona_id: string) => post<{ task_id: string }>(`/select/recommend?persona_id=${encodeURIComponent(persona_id)}`, {}),
  selectPublish: (data: { content_ids: string[]; persona_id: string }) => post<{ published: number; content_ids: string[] }>('/select/publish', data),
  selectHistory: (persona_id: string) => get<RecommendBatch[]>('/select/history', { persona_id }),
  // Feishu
  sendToFeishu: (content_id: string) =>
    post<{ ok: boolean; message_id: string; image_count: number }>(
      `/contents/${encodeURIComponent(content_id)}/send-to-feishu`,
      {},
    ),
}
