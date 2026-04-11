export interface IdeaOut {
  id: string
  title: string
  tags: string | null
  source: string
  status: string
  created_at: string
  updated_at: string
}

export interface ContentOut {
  content_id: string
  title: string
  persona_id: string
  platform: string
  status: string
  review_score: number | null
  review_json: string | null
  source_idea: string | null
  created_at: string
  updated_at: string
}

export interface ContentBodyOut {
  content_id: string
  title: string
  body: string
  platform: string
}

export interface MetricsOut {
  views: number
  likes: number
  collects: number
  comments: number
  shares: number
  captured_at: string
}

export interface PublicationOut {
  id: number
  content_id: string
  persona_id: string
  platform: string
  status: string
  post_url: string | null
  published_at: string | null
  created_at: string
  content_title: string | null
  latest_metrics: MetricsOut | null
}

export interface TaskStatus {
  task_id: string
  task_type: string
  status: string
  current_step: string | null
  result: Record<string, unknown> | null
  error: string | null
  started_at: string
  updated_at: string
}

export interface PersonaOut {
  id: string
  name: string
  platforms: string[]
}

export interface RecommendBatch {
  task_id: string
  created_at: string
  items: Array<{
    content_id: string
    content_title: string | null
    content_status: string | null
    platform: string | null
    reason: string | null
  }>
}

export interface DashboardData {
  ideas_pending: number
  contents_final: number
  published_total: number
  published_week: number
  activity: Array<{
    content_id: string
    title: string | null
    from_status: string
    to_status: string
    created_at: string
  }>
}
