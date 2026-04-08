<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { api } from '../api/client'
import type { TaskStatus } from '../types'

const tasks = ref<TaskStatus[]>([])
const loading = ref(true)
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
        </tr>
      </thead>
      <tbody>
        <tr v-for="t in tasks" :key="t.task_id">
          <td style="font-family: monospace; font-size: 12px;">{{ t.task_id }}</td>
          <td>{{ typeLabel[t.task_type] || t.task_type }}</td>
          <td>
            <span :class="'badge badge-' + t.status">
              <span v-if="t.status === 'running'" class="spinner"></span>
              {{ t.status }}
            </span>
          </td>
          <td>{{ t.current_step || '-' }}</td>
          <td>{{ t.started_at }}</td>
          <td>
            <template v-if="t.status === 'completed' && t.result">
              <span style="color: #155724; font-size: 12px;">
                {{ t.result.content_id || JSON.stringify(t.result) }}
              </span>
            </template>
            <template v-else-if="t.status === 'failed'">
              <span style="color: #721c24; font-size: 12px;">{{ t.error }}</span>
            </template>
            <template v-else>-</template>
          </td>
        </tr>
      </tbody>
    </table>

    <div v-else class="empty">暂无任务</div>
  </div>
</template>
