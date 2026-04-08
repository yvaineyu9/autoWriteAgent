<script setup lang="ts">
import { ref, inject, watch, onMounted } from 'vue'
import type { Ref } from 'vue'
import { api } from '../api/client'
import type { PublicationOut } from '../types'

const personaId = inject<Ref<string>>('currentPersona')!

const pubs = ref<PublicationOut[]>([])
const loading = ref(true)
const statusFilter = ref('')

// Metrics Form
const showMetrics = ref(false)
const metricTarget = ref<PublicationOut | null>(null)
const form = ref({ views: 0, likes: 0, collects: 0, comments: 0, shares: 0 })
const saving = ref(false)

// Status Edit
const showStatusEdit = ref(false)
const editTarget = ref<PublicationOut | null>(null)
const editStatus = ref('draft')
const editUrl = ref('')
const savingStatus = ref(false)

const toast = ref<{ msg: string; type: string } | null>(null)

async function load() {
  loading.value = true
  pubs.value = await api.getPublications({
    status: statusFilter.value || undefined,
    persona_id: personaId.value || undefined,
  })
  loading.value = false
}

onMounted(load)
watch(personaId, load)

function openMetrics(p: PublicationOut) {
  metricTarget.value = p
  if (p.latest_metrics) {
    form.value = {
      views: p.latest_metrics.views,
      likes: p.latest_metrics.likes,
      collects: p.latest_metrics.collects,
      comments: p.latest_metrics.comments,
      shares: p.latest_metrics.shares,
    }
  } else {
    form.value = { views: 0, likes: 0, collects: 0, comments: 0, shares: 0 }
  }
  showMetrics.value = true
}

async function saveMetrics() {
  if (!metricTarget.value) return
  saving.value = true
  try {
    await api.recordMetrics(metricTarget.value.id, form.value)
    showMetrics.value = false
    toast.value = { msg: '数据已保存', type: 'success' }
    setTimeout(() => toast.value = null, 3000)
    load()
  } catch (e: any) {
    toast.value = { msg: e.message, type: 'error' }
    setTimeout(() => toast.value = null, 4000)
  } finally {
    saving.value = false
  }
}

function openStatusEdit(p: PublicationOut) {
  editTarget.value = p
  editStatus.value = p.status
  editUrl.value = p.post_url || ''
  showStatusEdit.value = true
}

async function saveStatus() {
  if (!editTarget.value) return
  savingStatus.value = true
  try {
    await api.updatePublication(editTarget.value.id, {
      status: editStatus.value,
      post_url: editUrl.value || undefined,
    })
    showStatusEdit.value = false
    toast.value = { msg: '状态已更新', type: 'success' }
    setTimeout(() => toast.value = null, 3000)
    load()
  } catch (e: any) {
    toast.value = { msg: e.message, type: 'error' }
    setTimeout(() => toast.value = null, 4000)
  } finally {
    savingStatus.value = false
  }
}

const platformLabel: Record<string, string> = {
  xiaohongshu: '小红书',
  wechat: '微信',
}

const statusLabel: Record<string, string> = {
  draft: '待发布',
  published: '已发布',
}
</script>

<template>
  <div>
    <div class="page-header">
      <h1>发布数据</h1>
    </div>

    <div class="filters">
      <select v-model="statusFilter" @change="load">
        <option value="">全部状态</option>
        <option value="draft">待发布</option>
        <option value="published">已发布</option>
      </select>
    </div>

    <div v-if="loading" class="loading">加载中...</div>

    <table v-else-if="pubs.length">
      <thead>
        <tr>
          <th>标题</th>
          <th>平台</th>
          <th>状态</th>
          <th>发布链接</th>
          <th>发布时间</th>
          <th>浏览</th>
          <th>点赞</th>
          <th>收藏</th>
          <th>评论</th>
          <th>分享</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="p in pubs" :key="p.id">
          <td>{{ p.content_title || p.content_id }}</td>
          <td>{{ platformLabel[p.platform] || p.platform }}</td>
          <td>
            <span
              :class="'badge badge-' + p.status"
              style="cursor: pointer;"
              @click="openStatusEdit(p)"
              :title="'点击修改状态'"
            >
              {{ statusLabel[p.status] || p.status }}
            </span>
          </td>
          <td>
            <a v-if="p.post_url" :href="p.post_url" target="_blank" style="color: #1976d2; font-size: 12px;">链接</a>
            <span v-else style="color: #ccc; cursor: pointer;" @click="openStatusEdit(p)">+ 添加</span>
          </td>
          <td>{{ p.published_at || '-' }}</td>
          <td>{{ p.latest_metrics?.views ?? '-' }}</td>
          <td>{{ p.latest_metrics?.likes ?? '-' }}</td>
          <td>{{ p.latest_metrics?.collects ?? '-' }}</td>
          <td>{{ p.latest_metrics?.comments ?? '-' }}</td>
          <td>{{ p.latest_metrics?.shares ?? '-' }}</td>
          <td class="actions">
            <button class="icon-btn" data-tip="编辑状态" @click="openStatusEdit(p)">
              <svg viewBox="0 0 24 24"><path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
            </button>
            <button v-if="p.status === 'published'" class="icon-btn primary" data-tip="录入数据" @click="openMetrics(p)">
              <svg viewBox="0 0 24 24"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>
            </button>
          </td>
        </tr>
      </tbody>
    </table>

    <div v-else class="empty">暂无发布记录</div>

    <!-- Status Edit Modal -->
    <div v-if="showStatusEdit" class="modal-overlay" @click.self="showStatusEdit = false">
      <div class="modal">
        <h3>编辑发布状态</h3>
        <p style="font-size: 12px; color: #999; margin-bottom: 16px;">
          {{ editTarget?.content_title }}
        </p>
        <div class="form-group">
          <label>状态</label>
          <select v-model="editStatus">
            <option value="draft">待发布</option>
            <option value="published">已发布</option>
          </select>
        </div>
        <div class="form-group">
          <label>发布链接</label>
          <input v-model="editUrl" type="text" placeholder="https://..." />
        </div>
        <div class="modal-actions">
          <button class="btn btn-secondary" @click="showStatusEdit = false">取消</button>
          <button class="btn btn-primary" :disabled="savingStatus" @click="saveStatus">
            {{ savingStatus ? '保存中...' : '保存' }}
          </button>
        </div>
      </div>
    </div>

    <!-- Metrics Form Modal -->
    <div v-if="showMetrics" class="modal-overlay" @click.self="showMetrics = false">
      <div class="modal">
        <h3>录入数据</h3>
        <p style="font-size: 12px; color: #999; margin-bottom: 16px;">
          {{ metricTarget?.content_title }} - {{ platformLabel[metricTarget?.platform || ''] }}
        </p>
        <div class="form-group">
          <label>浏览量</label>
          <input v-model.number="form.views" type="number" min="0" />
        </div>
        <div class="form-group">
          <label>点赞数</label>
          <input v-model.number="form.likes" type="number" min="0" />
        </div>
        <div class="form-group">
          <label>收藏数</label>
          <input v-model.number="form.collects" type="number" min="0" />
        </div>
        <div class="form-group">
          <label>评论数</label>
          <input v-model.number="form.comments" type="number" min="0" />
        </div>
        <div class="form-group">
          <label>分享数</label>
          <input v-model.number="form.shares" type="number" min="0" />
        </div>
        <div class="modal-actions">
          <button class="btn btn-secondary" @click="showMetrics = false">取消</button>
          <button class="btn btn-primary" :disabled="saving" @click="saveMetrics">
            {{ saving ? '保存中...' : '保存' }}
          </button>
        </div>
      </div>
    </div>

    <div v-if="toast" :class="'toast toast-' + toast.type">{{ toast.msg }}</div>
  </div>
</template>
