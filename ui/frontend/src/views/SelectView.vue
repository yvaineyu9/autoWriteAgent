<template>
  <div>
    <div class="page-header">
      <h1>选文发布</h1>
      <div style="display:flex;gap:8px">
        <button class="btn btn-secondary" :disabled="contents.length === 0 || recommending" @click="doRecommend">
          {{ recommending ? 'AI 推荐中...' : 'AI 推荐' }}
        </button>
        <button class="btn btn-primary" :disabled="selectedIds.length === 0 || publishing" @click="doPublish">
          确认发布 ({{ selectedIds.length }})
        </button>
      </div>
    </div>

    <!-- AI Recommend progress -->
    <div v-if="recommending" class="ai-recommend-bar">
      <span class="spinner"></span> {{ recommendStep }}
    </div>

    <div v-if="loading" class="loading"><span class="spinner"></span> 加载中...</div>

    <div v-else-if="contents.length === 0" class="empty">暂无待发布的定稿文章</div>

    <div v-else class="select-grid">
      <div
        v-for="c in contents"
        :key="c.content_id"
        class="select-card"
        :class="{ selected: selectedIds.includes(c.content_id) }"
        @click="toggleSelect(c.content_id)"
      >
        <div class="select-check">
          <input type="checkbox" :checked="selectedIds.includes(c.content_id)" @click.stop="toggleSelect(c.content_id)" />
        </div>
        <div class="select-info">
          <div class="select-title">{{ c.title }}</div>
          <div class="select-meta">
            <span class="badge badge-final">定稿</span>
            <span class="tag">{{ platformLabel(c.platform) }}</span>
            <span v-if="c.review_score != null" class="select-score">{{ c.review_score }}/10</span>
            <span class="select-date">{{ c.created_at?.split(' ')[0] }}</span>
          </div>
          <div v-if="recommendations[c.content_id]" class="select-reason">
            AI 推荐：{{ recommendations[c.content_id] }}
          </div>
        </div>
      </div>
    </div>

    <!-- History -->
    <div class="section-header" style="margin-top:36px">
      <h2>推荐历史</h2>
    </div>
    <div v-if="history.length === 0" class="empty" style="padding:24px">暂无推荐记录</div>
    <div v-else class="history-list">
      <div v-for="batch in history" :key="batch.task_id" class="history-batch">
        <div class="history-time">{{ batch.created_at }}</div>
        <div class="history-items">
          <div v-for="item in batch.items" :key="item.content_id" class="history-item">
            <span class="history-title">{{ item.content_title || item.content_id }}</span>
            <span v-if="item.content_status" :class="'badge badge-' + item.content_status">{{ statusLabel(item.content_status) }}</span>
            <span v-if="item.reason" class="history-reason">{{ item.reason }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Toast -->
    <div v-if="toast" :class="'toast toast-' + toast.type">{{ toast.msg }}</div>
  </div>
</template>

<script setup lang="ts">
import { ref, inject, watch, onMounted, onUnmounted } from 'vue'
import type { Ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api/client'
import type { ContentOut, RecommendBatch } from '../types'

const router = useRouter()
const personaId = inject<Ref<string>>('currentPersona')!

const contents = ref<ContentOut[]>([])
const selectedIds = ref<string[]>([])
const history = ref<RecommendBatch[]>([])
const loading = ref(false)
const publishing = ref(false)
const recommending = ref(false)
const recommendStep = ref('')
const recommendations = ref<Record<string, string>>({})
let recommendPollTimer: ReturnType<typeof setInterval> | null = null
const toast = ref<{ type: string; msg: string } | null>(null)

async function loadContents() {
  if (!personaId.value) return
  loading.value = true
  try {
    contents.value = await api.getContents({ status: 'final', persona_id: personaId.value })
  } catch { /* ignore */ }
  loading.value = false
}

async function loadHistory() {
  if (!personaId.value) return
  try {
    history.value = await api.selectHistory(personaId.value)
  } catch { /* ignore */ }
}

const statusLabels: Record<string, string> = {
  draft: '草稿', final: '定稿', publishing: '发布中', published: '已发布',
  revising: '修订中', pending: '待处理', archived: '已归档',
}
function statusLabel(s: string) { return statusLabels[s] || s }

onMounted(() => { loadContents(); loadHistory() })
watch(personaId, () => { selectedIds.value = []; recommendations.value = {}; loadContents(); loadHistory() })
onUnmounted(() => { if (recommendPollTimer) clearInterval(recommendPollTimer) })

function toggleSelect(id: string) {
  const idx = selectedIds.value.indexOf(id)
  if (idx >= 0) {
    selectedIds.value.splice(idx, 1)
  } else {
    selectedIds.value.push(id)
  }
}

function platformLabel(p: string) {
  return p === 'xiaohongshu' ? '小红书' : p === 'wechat' ? '微信' : p
}

function showToast(type: string, msg: string) {
  toast.value = { type, msg }
  setTimeout(() => { toast.value = null }, 3000)
}

async function doRecommend() {
  recommending.value = true
  recommendStep.value = 'Starting...'
  recommendations.value = {}
  try {
    const res = await api.selectRecommend(personaId.value)
    const taskId = res.task_id
    recommendPollTimer = setInterval(async () => {
      try {
        const t = await api.getTask(taskId)
        recommendStep.value = t.current_step || ''
        if (t.status === 'completed') {
          if (recommendPollTimer) clearInterval(recommendPollTimer)
          recommending.value = false
          // Parse recommendations and auto-select
          const recs = t.result?.recommendations as Array<{ content_id: string; reason: string }> | undefined
          if (recs && recs.length) {
            const newSelected: string[] = []
            const newReasons: Record<string, string> = {}
            for (const r of recs) {
              newSelected.push(r.content_id)
              newReasons[r.content_id] = r.reason
            }
            selectedIds.value = newSelected
            recommendations.value = newReasons
            showToast('success', `AI 推荐了 ${recs.length} 篇文章`)
            loadHistory()
          } else {
            showToast('success', 'AI 未推荐任何文章')
          }
        } else if (t.status === 'failed') {
          if (recommendPollTimer) clearInterval(recommendPollTimer)
          recommending.value = false
          showToast('error', t.error || 'AI 推荐失败')
        }
      } catch { /* ignore poll errors */ }
    }, 3000)
  } catch (e: any) {
    recommending.value = false
    showToast('error', e.message || 'AI 推荐启动失败')
  }
}

async function doPublish() {
  if (selectedIds.value.length === 0) return
  publishing.value = true
  try {
    const result = await api.selectPublish({
      content_ids: selectedIds.value,
      persona_id: personaId.value,
    })
    showToast('success', `已创建 ${result.published} 条发布记录`)
    selectedIds.value = []
    setTimeout(() => { router.push('/publications') }, 1500)
  } catch (e: any) {
    showToast('error', e.message || '发布失败')
  }
  publishing.value = false
}
</script>

<style scoped>
.select-grid {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.select-card {
  display: flex;
  align-items: center;
  gap: 16px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 18px 20px;
  cursor: pointer;
  transition: all var(--transition);
  box-shadow: var(--shadow-sm);
}

.select-card:hover {
  border-color: #c7c9f7;
  box-shadow: var(--shadow-md);
}

.select-card.selected {
  border-color: var(--accent);
  background: var(--accent-soft);
  box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.08);
}

.select-check input {
  width: 18px;
  height: 18px;
  cursor: pointer;
  accent-color: var(--accent);
}

.select-info {
  flex: 1;
}

.select-title {
  font-size: 14.5px;
  font-weight: 550;
  margin-bottom: 7px;
  color: var(--text-1);
}

.select-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--text-3);
}

.select-score {
  color: var(--accent);
  font-weight: 600;
}

.select-date {
  color: var(--text-3);
}

.select-reason {
  margin-top: 8px;
  font-size: 12px;
  color: var(--accent);
  background: rgba(99, 102, 241, 0.06);
  padding: 6px 10px;
  border-radius: var(--radius-sm);
  border-left: 2px solid var(--accent);
}

.ai-recommend-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 11px 16px;
  border-radius: var(--radius);
  background: var(--accent-soft);
  color: var(--accent);
  font-size: 13px;
  font-weight: 500;
  margin-bottom: 18px;
  border: 1px solid rgba(99, 102, 241, 0.12);
}

/* History */
.history-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.history-batch {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 16px 20px;
  box-shadow: var(--shadow-sm);
}

.history-time {
  font-size: 12px;
  color: var(--text-3);
  margin-bottom: 10px;
  font-weight: 500;
}

.history-items {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.history-item {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 13px;
  flex-wrap: wrap;
}

.history-title {
  font-weight: 520;
  color: var(--text-1);
}

.history-reason {
  font-size: 12px;
  color: var(--text-3);
  flex-basis: 100%;
  padding-left: 2px;
  border-left: 2px solid var(--border);
  margin-left: 0;
  padding: 2px 0 2px 10px;
}
</style>
