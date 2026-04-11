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
  gap: 14px;
  margin-bottom: 28px;
}

.stat-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 22px 20px;
  text-align: center;
  transition: all var(--transition);
  box-shadow: var(--shadow-sm);
}

.stat-card:hover {
  box-shadow: var(--shadow-md);
  transform: translateY(-1px);
}

.stat-value {
  font-size: 36px;
  font-weight: 750;
  color: var(--accent);
  letter-spacing: -0.03em;
  line-height: 1.1;
}

.stat-label {
  font-size: 12.5px;
  color: var(--text-3);
  margin-top: 6px;
  font-weight: 450;
}

.quick-actions {
  display: flex;
  gap: 14px;
  margin-bottom: 36px;
}

.action-card {
  flex: 1;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 28px 18px;
  cursor: pointer;
  transition: all var(--transition);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  font-family: inherit;
  box-shadow: var(--shadow-sm);
}

.action-card:hover {
  border-color: var(--accent);
  background: var(--accent-soft);
  box-shadow: 0 2px 12px rgba(99, 102, 241, 0.12);
  transform: translateY(-2px);
}

.action-icon {
  width: 44px;
  height: 44px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 22px;
  color: var(--accent);
  background: var(--accent-soft);
  border-radius: 12px;
}

.action-card:hover .action-icon {
  background: rgba(99, 102, 241, 0.15);
}

.action-text {
  font-size: 14px;
  font-weight: 550;
  color: var(--text-1);
}
</style>
