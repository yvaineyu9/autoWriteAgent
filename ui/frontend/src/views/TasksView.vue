<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { api } from '../api/client'
import type { TaskStatus } from '../types'

const tasks = ref<TaskStatus[]>([])
const loading = ref(true)
const retrying = ref('')
const toast = ref<{ msg: string; type: string } | null>(null)
let timer: ReturnType<typeof setInterval> | null = null

async function load() {
  try {
    tasks.value = await api.getTasks()
  } catch {
    // ignore
  }
  loading.value = false
}

const hasRunning = computed(() => tasks.value.some(t => t.status === 'running'))

function startPolling() {
  timer = setInterval(() => {
    if (hasRunning.value) load()
  }, 3000)
}

onMounted(() => {
  load()
  startPolling()
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
})

const typeLabel: Record<string, string> = {
  create: '创建文章',
  revise: '修改文章',
  collect: 'AI 采集',
  expand: 'AI 扩充',
  recommend: 'AI 推荐',
}

function formatResult(t: TaskStatus): string {
  if (!t.result) return '-'
  const r = t.result as Record<string, unknown>
  switch (t.task_type) {
    case 'create':
      return '创建了文章' + (r.title ? ' ' + r.title : r.content_id ? ' ' + r.content_id : '')
    case 'revise':
      return '修改了文章 ' + (r.content_id || '') + (r.review_score ? ' (评分: ' + r.review_score + ')' : '')
    case 'collect':
      return '发现 ' + (r.collected || 0) + ' 条，入库 ' + (r.saved || 0) + ' 条'
    case 'expand':
      return '已扩充灵感'
    case 'recommend': {
      const recs = r.recommendations as unknown[] | undefined
      return '推荐了 ' + (recs?.length || 0) + ' 篇文章'
    }
    default:
      return JSON.stringify(r).slice(0, 80)
  }
}

function formatError(error: string | null): string {
  if (!error) return '未知错误'
  // Extract last meaningful line from traceback-like errors
  const lines = error.split('\n').filter(l => l.trim())
  const last = lines.length > 1 ? lines[lines.length - 1] : error
  return last.length > 120 ? last.slice(0, 120) + '...' : last
}

async function doRetry(taskId: string) {
  retrying.value = taskId
  try {
    const res = await api.retryTask(taskId)
    toast.value = { msg: '重试已启动: ' + res.task_id, type: 'success' }
    setTimeout(() => toast.value = null, 3000)
    load()
  } catch (e: any) {
    toast.value = { msg: e.message || '重试失败', type: 'error' }
    setTimeout(() => toast.value = null, 4000)
  } finally {
    retrying.value = ''
  }
}
</script>

<template>
  <div>
    <div class="page-header">
      <h1>任务监控</h1>
      <button class="icon-btn" data-tip="刷新" @click="load">
        <svg viewBox="0 0 24 24"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 11-2.12-9.36L23 10"/></svg>
      </button>
    </div>

    <div v-if="loading" class="loading">加载中...</div>

    <table v-else-if="tasks.length">
      <thead>
        <tr>
          <th>任务 ID</th>
          <th>类型</th>
          <th>状态</th>
          <th>进度</th>
          <th>开始时间</th>
          <th>结果</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="t in tasks" :key="t.task_id">
          <td style="font-family: monospace; font-size: 12px;">{{ t.task_id }}</td>
          <td>{{ typeLabel[t.task_type] || t.task_type }}</td>
          <td>
            <span :class="'badge badge-' + t.status">
              <span v-if="t.status === 'running'" class="spinner"></span>
              {{ t.status === 'running' ? '运行中' : t.status === 'completed' ? '完成' : t.status === 'failed' ? '失败' : t.status }}
            </span>
          </td>
          <td>{{ t.current_step || '-' }}</td>
          <td>{{ t.started_at }}</td>
          <td>
            <template v-if="t.status === 'completed'">
              <span style="color: #155724; font-size: 12px;">{{ formatResult(t) }}</span>
            </template>
            <template v-else-if="t.status === 'failed'">
              <span style="color: #721c24; font-size: 12px;" :title="t.error || ''">{{ formatError(t.error) }}</span>
            </template>
            <template v-else>-</template>
          </td>
          <td class="actions">
            <button
              v-if="t.status === 'failed'"
              class="btn btn-sm btn-secondary"
              :disabled="retrying === t.task_id || hasRunning"
              @click="doRetry(t.task_id)"
            >
              {{ retrying === t.task_id ? '重试中...' : '重试' }}
            </button>
          </td>
        </tr>
      </tbody>
    </table>

    <div v-else class="empty">暂无任务</div>

    <div v-if="toast" :class="'toast toast-' + toast.type">{{ toast.msg }}</div>
  </div>
</template>
