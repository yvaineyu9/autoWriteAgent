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

    <!-- Toast -->
    <div v-if="toast" :class="'toast toast-' + toast.type">{{ toast.msg }}</div>
  </div>
</template>

<script setup lang="ts">
import { ref, inject, watch, onMounted, onUnmounted } from 'vue'
import type { Ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api/client'
import type { ContentOut } from '../types'

const router = useRouter()
const personaId = inject<Ref<string>>('currentPersona')!

const contents = ref<ContentOut[]>([])
const selectedIds = ref<string[]>([])
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

onMounted(loadContents)
watch(personaId, () => { selectedIds.value = []; recommendations.value = {}; loadContents() })
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
  gap: 14px;
  background: #fff;
  border: 2px solid #eee;
  border-radius: 10px;
  padding: 16px;
  cursor: pointer;
  transition: all 0.15s;
}

.select-card:hover {
  border-color: #90caf9;
}

.select-card.selected {
  border-color: #1976d2;
  background: #f5faff;
}

.select-check input {
  width: 18px;
  height: 18px;
  cursor: pointer;
}

.select-info {
  flex: 1;
}

.select-title {
  font-size: 15px;
  font-weight: 500;
  margin-bottom: 6px;
}

.select-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: #888;
}

.select-score {
  color: #1976d2;
  font-weight: 500;
}

.select-date {
  color: #aaa;
}

.select-reason {
  margin-top: 6px;
  font-size: 12px;
  color: #1976d2;
  background: #e3f2fd;
  padding: 4px 8px;
  border-radius: 4px;
}

.ai-recommend-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  border-radius: 6px;
  background: #e3f2fd;
  color: #1565c0;
  font-size: 13px;
  margin-bottom: 16px;
}
</style>
