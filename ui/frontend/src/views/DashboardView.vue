<template>
  <div>
    <div class="page-header">
      <h1>仪表盘</h1>
    </div>

    <!-- Stats Cards -->
    <div class="stats-grid">
      <div class="stat-card">
        <div class="stat-value">{{ data.ideas_pending }}</div>
        <div class="stat-label">待处理灵感</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{{ data.contents_final }}</div>
        <div class="stat-label">待发布成品</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{{ data.published_total }}</div>
        <div class="stat-label">已发布总数</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{{ data.published_week }}</div>
        <div class="stat-label">本周新增发布</div>
      </div>
    </div>

    <!-- Quick Actions -->
    <div class="quick-actions">
      <button class="action-card" @click="goCollect">
        <span class="action-icon">+</span>
        <span class="action-text">采集灵感</span>
      </button>
      <button class="action-card" @click="goCreate">
        <span class="action-icon">&#9998;</span>
        <span class="action-text">创作文章</span>
      </button>
      <button class="action-card" @click="goSelect">
        <span class="action-icon">&#10003;</span>
        <span class="action-text">选文发布</span>
      </button>
    </div>

    <!-- Recent Activity -->
    <div class="section-header">
      <h2>最近动态</h2>
    </div>
    <div v-if="data.activity.length === 0" class="empty">暂无动态</div>
    <table v-else>
      <thead>
        <tr>
          <th>文章</th>
          <th>状态变更</th>
          <th>时间</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="a in data.activity" :key="a.content_id + a.created_at">
          <td>{{ a.title || a.content_id }}</td>
          <td>
            <span :class="'badge badge-' + a.from_status">{{ statusLabel(a.from_status) }}</span>
            &rarr;
            <span :class="'badge badge-' + a.to_status">{{ statusLabel(a.to_status) }}</span>
          </td>
          <td>{{ a.created_at }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup lang="ts">
import { ref, inject, watch, onMounted } from 'vue'
import type { Ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api/client'
import type { DashboardData } from '../types'

const router = useRouter()
const personaId = inject<Ref<string>>('currentPersona')!

const data = ref<DashboardData>({
  ideas_pending: 0,
  contents_final: 0,
  published_total: 0,
  published_week: 0,
  activity: [],
})

async function loadDashboard() {
  if (!personaId.value) return
  try {
    data.value = await api.getDashboard(personaId.value)
  } catch { /* ignore */ }
}

onMounted(loadDashboard)
watch(personaId, loadDashboard)

const statusLabels: Record<string, string> = {
  draft: '草稿', final: '定稿', publishing: '发布中', published: '已发布',
  revising: '修订中', pending: '待处理', used: '已使用',
}
function statusLabel(s: string) { return statusLabels[s] || s }

function goCollect() { router.push('/ideas') }
function goCreate() { router.push('/contents?create=1') }
function goSelect() { router.push('/select') }
</script>

<style scoped>
.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 24px;
}

.stat-card {
  background: #fff;
  border-radius: 10px;
  padding: 20px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.08);
  text-align: center;
}

.stat-value {
  font-size: 32px;
  font-weight: 700;
  color: #1976d2;
}

.stat-label {
  font-size: 13px;
  color: #888;
  margin-top: 4px;
}

.quick-actions {
  display: flex;
  gap: 16px;
  margin-bottom: 32px;
}

.action-card {
  flex: 1;
  background: #fff;
  border: 2px dashed #ddd;
  border-radius: 10px;
  padding: 24px 16px;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  font-family: inherit;
}

.action-card:hover {
  border-color: #1976d2;
  background: #f5faff;
}

.action-icon {
  font-size: 28px;
  color: #1976d2;
}

.action-text {
  font-size: 15px;
  font-weight: 500;
  color: #333;
}

.section-header {
  margin-bottom: 12px;
}

.section-header h2 {
  font-size: 16px;
  font-weight: 600;
  color: #333;
}
</style>
