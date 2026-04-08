<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { api } from '../api/client'
import type { ContentOut } from '../types'

const contents = ref<ContentOut[]>([])
const loading = ref(true)
const statusFilter = ref('')
const platformFilter = ref('')

// Editor modal
const showEditor = ref(false)
const editorTarget = ref<ContentOut | null>(null)
const editorBody = ref('')
const editorOriginal = ref('')
const loadingBody = ref(false)
const saving = ref(false)
const copied = ref(false)
const editorDirty = ref(false)

// AI feedback + task tracking
const feedback = ref('')
const submittingAI = ref(false)
const aiTaskId = ref('')
const aiTaskStatus = ref('')  // '' | 'running' | 'completed' | 'failed'
const aiTaskStep = ref('')
const aiTaskError = ref('')
let pollTimer: ReturnType<typeof setInterval> | null = null

// Typeset config
const showTypesetConfig = ref(false)
const typesetTarget = ref<ContentOut | null>(null)
const typesetTool = ref('v2')
const typesetSelectedCover = ref('')  // filename or empty for default
const typesetCustomCoverUrl = ref('')
const builtinCovers = ref<string[]>([])
const typesetPersona = ref('yuejian')

// Typeset result
const typesetImages = ref<string[]>([])
const typesetting = ref(false)
const showTypeset = ref(false)
const typesetContentId = ref('')

// Delete confirm
const showDeleteConfirm = ref(false)
const deleteTarget = ref<ContentOut | null>(null)
const deleting = ref(false)

const toast = ref<{ msg: string; type: string } | null>(null)

function confirmDelete(c: ContentOut) {
  deleteTarget.value = c
  showDeleteConfirm.value = true
}

async function doDelete() {
  if (!deleteTarget.value) return
  deleting.value = true
  try {
    await api.deleteContent(deleteTarget.value.content_id)
    showDeleteConfirm.value = false
    showEditor.value = false
    showToast('已删除')
    load()
  } catch (e: any) {
    showToast(e.message, 'error')
  } finally {
    deleting.value = false
  }
}

function showToast(msg: string, type: string = 'success') {
  toast.value = { msg, type }
  setTimeout(() => toast.value = null, 3000)
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

onUnmounted(stopPolling)

async function pollTask() {
  if (!aiTaskId.value) return
  try {
    const t = await api.getTask(aiTaskId.value)
    aiTaskStatus.value = t.status
    aiTaskStep.value = t.current_step || ''
    if (t.status === 'completed') {
      stopPolling()
      aiTaskError.value = ''
      // Auto-reload content body
      if (editorTarget.value) {
        const data = await api.getContentBody(editorTarget.value.content_id)
        editorBody.value = data.body
        editorOriginal.value = data.body
        editorDirty.value = false
      }
      showToast('AI 修改完成，内容已更新')
    } else if (t.status === 'failed') {
      stopPolling()
      aiTaskError.value = t.error || '未知错误'
      showToast('AI 修改失败: ' + aiTaskError.value, 'error')
    }
  } catch {
    // ignore poll errors
  }
}

async function load() {
  loading.value = true
  const params: Record<string, string> = {}
  if (statusFilter.value) params.status = statusFilter.value
  if (platformFilter.value) params.platform = platformFilter.value
  contents.value = await api.getContents(params)
  loading.value = false
}

onMounted(load)

async function openEditor(c: ContentOut) {
  editorTarget.value = c
  loadingBody.value = true
  showEditor.value = true
  editorDirty.value = false
  feedback.value = ''
  aiTaskId.value = ''
  aiTaskStatus.value = ''
  aiTaskStep.value = ''
  aiTaskError.value = ''
  stopPolling()
  try {
    const data = await api.getContentBody(c.content_id)
    editorBody.value = data.body
    editorOriginal.value = data.body
  } catch (e: any) {
    showToast(e.message, 'error')
  } finally {
    loadingBody.value = false
  }
}

function onBodyInput() {
  editorDirty.value = editorBody.value !== editorOriginal.value
}

async function saveManual() {
  if (!editorTarget.value) return
  saving.value = true
  try {
    await api.saveContentBody(editorTarget.value.content_id, editorBody.value)
    editorOriginal.value = editorBody.value
    editorDirty.value = false
    showToast('已保存')
  } catch (e: any) {
    showToast(e.message, 'error')
  } finally {
    saving.value = false
  }
}

async function submitAIRevise() {
  if (!editorTarget.value || !feedback.value.trim()) return
  submittingAI.value = true
  try {
    const res = await api.reviseContent({
      content_id: editorTarget.value.content_id,
      feedback: feedback.value,
    })
    // Start polling
    aiTaskId.value = res.task_id
    aiTaskStatus.value = 'running'
    aiTaskStep.value = 'Starting...'
    aiTaskError.value = ''
    feedback.value = ''
    stopPolling()
    pollTimer = setInterval(pollTask, 3000)
  } catch (e: any) {
    showToast(e.message, 'error')
  } finally {
    submittingAI.value = false
  }
}

async function copyBody() {
  await navigator.clipboard.writeText(editorBody.value)
  copied.value = true
  setTimeout(() => copied.value = false, 2000)
}

async function openTypesetConfig(c: ContentOut) {
  typesetTarget.value = c
  typesetTool.value = 'v2'
  typesetCustomCoverUrl.value = ''
  typesetPersona.value = 'yuejian'
  showTypesetConfig.value = true
  try {
    builtinCovers.value = await api.listCovers()
    // Default select 5th cover, or last available
    const idx = Math.min(4, builtinCovers.value.length - 1)
    typesetSelectedCover.value = idx >= 0 ? builtinCovers.value[idx] : ''
  } catch {
    builtinCovers.value = []
    typesetSelectedCover.value = ''
  }
}

async function doTypeset() {
  if (!typesetTarget.value) return
  const c = typesetTarget.value
  typesetContentId.value = c.content_id
  typesetting.value = true
  typesetImages.value = []
  showTypesetConfig.value = false
  showTypeset.value = true

  let cover_url: string | undefined
  if (typesetCustomCoverUrl.value.trim()) {
    cover_url = typesetCustomCoverUrl.value.trim()
  } else if (typesetSelectedCover.value) {
    cover_url = `asset:${typesetSelectedCover.value}`
  }

  try {
    const res = await api.typesetContent(c.content_id, {
      tool: typesetTool.value,
      cover_url,
    })
    typesetImages.value = res.images
    showToast(`生成 ${res.count} 张图片`)
  } catch (e: any) {
    showToast(e.message, 'error')
  } finally {
    typesetting.value = false
  }
}

const personas = [
  { id: 'yuejian', name: '月见', desc: '关系心理学 x 文艺情感' },
  { id: 'chongxiaoyu', name: '虫小宇', desc: 'Gen Z 占星 + AI' },
]

const platformLabel: Record<string, string> = {
  xiaohongshu: '小红书',
  wechat: '微信',
}
</script>

<template>
  <div>
    <div class="page-header">
      <h1>成品仓库</h1>
    </div>

    <div class="filters">
      <select v-model="statusFilter" @change="load">
        <option value="">全部状态</option>
        <option value="draft">草稿</option>
        <option value="final">定稿</option>
        <option value="publishing">发布中</option>
        <option value="published">已发布</option>
      </select>
      <select v-model="platformFilter" @change="load">
        <option value="">全部平台</option>
        <option value="xiaohongshu">小红书</option>
        <option value="wechat">微信</option>
      </select>
    </div>

    <div v-if="loading" class="loading">加载中...</div>

    <table v-else-if="contents.length">
      <thead>
        <tr>
          <th>标题</th>
          <th>平台</th>
          <th>状态</th>
          <th>评分</th>
          <th>创建时间</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="c in contents" :key="c.content_id">
          <td>{{ c.title }}</td>
          <td>{{ platformLabel[c.platform] || c.platform }}</td>
          <td><span :class="'badge badge-' + c.status">{{ c.status }}</span></td>
          <td>{{ c.review_score != null ? c.review_score + '/10' : '-' }}</td>
          <td>{{ c.created_at }}</td>
          <td class="actions">
            <button class="icon-btn" data-tip="查看/编辑" @click="openEditor(c)">
              <svg viewBox="0 0 24 24"><path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
            </button>
            <button v-if="c.platform === 'xiaohongshu'" class="icon-btn primary" data-tip="排版图片" @click="openTypesetConfig(c)">
              <svg viewBox="0 0 24 24"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>
            </button>
            <button v-if="c.status !== 'published'" class="icon-btn danger" data-tip="删除" @click="confirmDelete(c)">
              <svg viewBox="0 0 24 24"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/></svg>
            </button>
          </td>
        </tr>
      </tbody>
    </table>

    <div v-else class="empty">暂无成品</div>

    <!-- Editor Modal -->
    <div v-if="showEditor" class="modal-overlay" @click.self="showEditor = false">
      <div class="modal editor-modal">
        <div class="editor-header">
          <h3>{{ editorTarget?.title }}</h3>
          <span style="font-size: 12px; color: #999;">
            {{ platformLabel[editorTarget?.platform || ''] }}
          </span>
        </div>

        <div v-if="loadingBody" class="loading">加载中...</div>
        <template v-else>
          <!-- Editable content area -->
          <textarea
            v-model="editorBody"
            class="editor-textarea"
            @input="onBodyInput"
          ></textarea>

          <!-- Manual save + copy -->
          <div class="editor-actions">
            <div class="editor-actions-left">
              <button class="icon-btn primary" :data-tip="saving ? '保存中...' : editorDirty ? '保存修改' : '无变更'" :disabled="!editorDirty || saving" @click="saveManual">
                <svg viewBox="0 0 24 24"><path d="M19 21H5a2 2 0 01-2-2V5a2 2 0 012-2h11l5 5v11a2 2 0 01-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg>
              </button>
              <button class="icon-btn" :data-tip="copied ? '已复制' : '复制内容'" @click="copyBody">
                <svg viewBox="0 0 24 24"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg>
              </button>
              <button v-if="editorTarget?.status !== 'published'" class="icon-btn danger" data-tip="删除" @click="editorTarget && confirmDelete(editorTarget)">
                <svg viewBox="0 0 24 24"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/></svg>
              </button>
            </div>
            <button class="icon-btn" data-tip="关闭" @click="showEditor = false">
              <svg viewBox="0 0 24 24"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
            </button>
          </div>

          <!-- AI revision section -->
          <div class="ai-section">
            <div class="ai-section-title">AI 修改</div>

            <!-- Task progress bar -->
            <div v-if="aiTaskStatus === 'running'" class="ai-progress">
              <span class="spinner"></span>
              <span class="ai-progress-text">{{ aiTaskStep }}</span>
            </div>
            <div v-else-if="aiTaskStatus === 'completed'" class="ai-progress ai-progress-done">
              内容已更新
            </div>
            <div v-else-if="aiTaskStatus === 'failed'" class="ai-progress ai-progress-fail">
              失败: {{ aiTaskError }}
            </div>

            <div class="ai-input-row">
              <textarea
                v-model="feedback"
                class="ai-textarea"
                placeholder="输入修改意见，让 AI 重写这篇文章..."
                :disabled="aiTaskStatus === 'running'"
              ></textarea>
              <button
                class="btn btn-primary"
                :disabled="submittingAI || !feedback.trim() || aiTaskStatus === 'running'"
                @click="submitAIRevise"
              >
                {{ submittingAI ? '提交中...' : aiTaskStatus === 'running' ? 'AI 处理中...' : '提交 AI 修改' }}
              </button>
            </div>
          </div>
        </template>
      </div>
    </div>

    <!-- Typeset Config Dialog -->
    <div v-if="showTypesetConfig" class="modal-overlay" @click.self="showTypesetConfig = false">
      <div class="modal typeset-config-modal">
        <h3>排版设置</h3>
        <p style="font-size: 12px; color: #999; margin-bottom: 16px;">{{ typesetTarget?.title }}</p>

        <!-- Tool selection: visual cards -->
        <div class="config-section">
          <label class="config-label">排版风格</label>
          <div class="tool-cards">
            <div
              class="tool-card"
              :class="{ 'tool-card-active': typesetTool === 'v1' }"
              @click="typesetTool = 'v1'"
            >
              <div class="tool-card-preview tool-card-v1">
                <span class="tool-card-icon">V1</span>
              </div>
              <div class="tool-card-info">
                <strong>纸质纹理</strong>
                <span>892 x 1242</span>
              </div>
            </div>
            <div
              class="tool-card"
              :class="{ 'tool-card-active': typesetTool === 'v2' }"
              @click="typesetTool = 'v2'"
            >
              <div class="tool-card-preview tool-card-v2">
                <span class="tool-card-icon">V2</span>
              </div>
              <div class="tool-card-info">
                <strong>深色渐变</strong>
                <span>1080 x 1440</span>
              </div>
            </div>
          </div>
        </div>

        <!-- Cover selection: flat grid -->
        <div class="config-section">
          <label class="config-label">封面/头图</label>
          <div class="cover-grid">
            <div
              v-for="c in builtinCovers"
              :key="c"
              class="cover-item"
              :class="{ 'cover-selected': typesetSelectedCover === c }"
              @click="typesetSelectedCover = c; typesetCustomCoverUrl = ''"
            >
              <img :src="`/api/typeset/covers/${c}`" :alt="c" />
            </div>
          </div>
          <div style="margin-top: 8px;">
            <input
              v-model="typesetCustomCoverUrl"
              type="text"
              placeholder="或粘贴自定义封面 URL..."
              style="width: 100%; padding: 6px 10px; border: 1px solid #ddd; border-radius: 6px; font-size: 12px;"
              @input="typesetSelectedCover = ''"
            />
          </div>
        </div>

        <!-- Persona selection: visual cards -->
        <div class="config-section">
          <label class="config-label">人设（头像/署名/页头）</label>
          <div class="persona-cards">
            <div
              v-for="p in personas"
              :key="p.id"
              class="persona-card"
              :class="{ 'persona-card-active': typesetPersona === p.id }"
              @click="typesetPersona = p.id"
            >
              <strong>{{ p.name }}</strong>
              <span>{{ p.desc }}</span>
            </div>
          </div>
        </div>

        <div class="modal-actions">
          <button class="btn btn-secondary" @click="showTypesetConfig = false">取消</button>
          <button class="btn btn-primary" @click="doTypeset">生成排版图片</button>
        </div>
      </div>
    </div>

    <!-- Typeset Preview Modal -->
    <div v-if="showTypeset" class="modal-overlay" @click.self="showTypeset = false">
      <div class="modal typeset-modal">
        <h3>排版预览</h3>
        <div v-if="typesetting" class="loading">
          <span class="spinner"></span> 生成中...
        </div>
        <div v-else-if="typesetImages.length" class="typeset-grid">
          <div v-for="img in typesetImages" :key="img" class="typeset-item">
            <img :src="`/api/contents/${typesetContentId}/typeset/${img}`" :alt="img" />
            <a
              :href="`/api/contents/${typesetContentId}/typeset/${img}`"
              :download="img"
              class="btn btn-secondary btn-sm"
              style="margin-top: 4px;"
            >
              下载
            </a>
          </div>
        </div>
        <div v-else class="empty">无图片</div>
        <div class="modal-actions">
          <button class="btn btn-secondary" @click="showTypeset = false">关闭</button>
        </div>
      </div>
    </div>

    <!-- Delete Confirm -->
    <div v-if="showDeleteConfirm" class="modal-overlay" @click.self="showDeleteConfirm = false">
      <div class="modal" style="min-width: 360px;">
        <h3>确认删除</h3>
        <p style="margin: 12px 0; font-size: 14px;">确定要删除「{{ deleteTarget?.title }}」吗？此操作不可恢复。</p>
        <div class="modal-actions">
          <button class="btn btn-secondary" @click="showDeleteConfirm = false">取消</button>
          <button class="btn btn-sm" style="background:#c62828;color:#fff;" :disabled="deleting" @click="doDelete">
            {{ deleting ? '删除中...' : '确认删除' }}
          </button>
        </div>
      </div>
    </div>

    <div v-if="toast" :class="'toast toast-' + toast.type">{{ toast.msg }}</div>
  </div>
</template>

<style scoped>
.editor-modal {
  min-width: 700px;
  max-width: 850px;
}

.editor-header {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 12px;
}

.editor-textarea {
  width: 100%;
  min-height: 40vh;
  padding: 14px;
  border: 1px solid #ddd;
  border-radius: 8px;
  font-size: 14px;
  line-height: 1.7;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  resize: vertical;
  background: #fafafa;
}

.editor-textarea:focus {
  outline: none;
  border-color: #1976d2;
  background: #fff;
}

.editor-actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 10px;
}

.editor-actions-left {
  display: flex;
  gap: 8px;
}

.ai-section {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid #eee;
}

.ai-section-title {
  font-size: 13px;
  font-weight: 600;
  color: #555;
  margin-bottom: 8px;
}

.ai-input-row {
  display: flex;
  gap: 10px;
  align-items: flex-end;
}

.ai-progress {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  border-radius: 6px;
  background: #e3f2fd;
  color: #1565c0;
  font-size: 13px;
  margin-bottom: 10px;
}

.ai-progress-done {
  background: #e8f5e9;
  color: #2e7d32;
}

.ai-progress-fail {
  background: #fce4ec;
  color: #c62828;
}

.ai-progress-text {
  flex: 1;
}

.ai-textarea {
  flex: 1;
  min-height: 60px;
  padding: 10px 12px;
  border: 1px solid #ddd;
  border-radius: 6px;
  font-size: 13px;
  resize: vertical;
  font-family: inherit;
}

.ai-textarea:disabled {
  background: #f5f5f5;
  cursor: not-allowed;
}

.typeset-modal {
  min-width: 600px;
  max-width: 900px;
}

.typeset-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  max-height: 60vh;
  overflow-y: auto;
  padding: 4px;
}

.typeset-item {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.typeset-item img {
  width: 200px;
  border-radius: 6px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.1);
}

/* Typeset config */
.typeset-config-modal {
  min-width: 560px;
  max-width: 640px;
}

.config-section {
  margin-bottom: 18px;
}

.config-label {
  display: block;
  font-size: 13px;
  font-weight: 600;
  color: #555;
  margin-bottom: 8px;
}

/* Tool cards */
.tool-cards {
  display: flex;
  gap: 12px;
}

.tool-card {
  flex: 1;
  cursor: pointer;
  border: 2px solid #e0e0e0;
  border-radius: 10px;
  overflow: hidden;
  transition: all 0.2s;
}

.tool-card:hover {
  border-color: #90caf9;
}

.tool-card-active {
  border-color: #1976d2;
  box-shadow: 0 0 0 1px #1976d2;
}

.tool-card-preview {
  height: 80px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.tool-card-v1 {
  background: linear-gradient(135deg, #f5f0e6, #e8dcc8);
}

.tool-card-v2 {
  background: linear-gradient(135deg, #141432, #6b4a7a);
}

.tool-card-icon {
  font-size: 24px;
  font-weight: 700;
  color: #fff;
  text-shadow: 0 1px 4px rgba(0,0,0,0.3);
}

.tool-card-v1 .tool-card-icon {
  color: #5d4037;
  text-shadow: none;
}

.tool-card-info {
  padding: 8px 12px;
  background: #fafafa;
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 13px;
}

.tool-card-info span {
  font-size: 11px;
  color: #999;
}

/* Cover grid */
.cover-grid {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.cover-item {
  cursor: pointer;
  border: 2px solid transparent;
  border-radius: 8px;
  overflow: hidden;
  transition: border-color 0.2s;
}

.cover-item:hover {
  border-color: #90caf9;
}

.cover-selected {
  border-color: #1976d2;
  box-shadow: 0 0 0 1px #1976d2;
}

.cover-item img {
  width: 90px;
  height: 68px;
  object-fit: cover;
  display: block;
}

.cover-placeholder {
  width: 90px;
  height: 68px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #f0f0f0;
  color: #999;
  font-size: 12px;
}

/* Persona cards */
.persona-cards {
  display: flex;
  gap: 10px;
}

.persona-card {
  flex: 1;
  cursor: pointer;
  border: 2px solid #e0e0e0;
  border-radius: 8px;
  padding: 12px 14px;
  transition: all 0.2s;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.persona-card:hover {
  border-color: #90caf9;
}

.persona-card-active {
  border-color: #1976d2;
  background: #e3f2fd;
}

.persona-card strong {
  font-size: 14px;
}

.persona-card span {
  font-size: 11px;
  color: #888;
}
</style>
