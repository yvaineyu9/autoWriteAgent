<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api/client'
import type { IdeaOut } from '../types'

const router = useRouter()

const ideas = ref<IdeaOut[]>([])
const loading = ref(true)
const statusFilter = ref('')
// Detail/Editor modal (unified)
const showDetail = ref(false)
const detailIdea = ref<IdeaOut | null>(null)
const detailBody = ref('')
const detailOriginal = ref('')
const detailTitle = ref('')
const detailTags = ref('')
const detailLoading = ref(false)
const detailDirty = ref(false)
const saving = ref(false)
const copied = ref(false)

// AI expand
const expandInstruction = ref('')
const expandSubmitting = ref(false)
const expandTaskId = ref('')
const expandStatus = ref('')
const expandStep = ref('')
const expandError = ref('')
let expandTimer: ReturnType<typeof setInterval> | null = null

// Add modal (for new ideas only)
const showAdd = ref(false)
const addTitle = ref('')
const addContent = ref('')
const addTags = ref('')
const addSaving = ref(false)

// AI Collect
const showCollect = ref(false)
const collectSource = ref('')
const collectSubmitting = ref(false)
const collectTaskId = ref('')
const collectStatus = ref('')  // '' | 'running' | 'completed' | 'failed'
const collectStep = ref('')
const collectResult = ref<{ collected: number; saved: number } | null>(null)
const collectError = ref('')
let pollTimer: ReturnType<typeof setInterval> | null = null

// Delete confirm
const showDeleteConfirm = ref(false)
const deleteTarget = ref<IdeaOut | null>(null)
const deleting = ref(false)

const toast = ref<{ msg: string; type: string } | null>(null)

function showToast(msg: string, type: string = 'success') {
  toast.value = { msg, type }
  setTimeout(() => toast.value = null, 3000)
}

function stopPolling() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
  if (expandTimer) { clearInterval(expandTimer); expandTimer = null }
}
onUnmounted(stopPolling)

async function pollCollect() {
  if (!collectTaskId.value) return
  try {
    const t = await api.getTask(collectTaskId.value)
    collectStatus.value = t.status
    collectStep.value = t.current_step || ''
    if (t.status === 'completed') {
      stopPolling()
      collectResult.value = (t.result as any) || null
      showToast('采集完成，新增 ' + (collectResult.value?.saved || 0) + ' 条灵感')
      load()
    } else if (t.status === 'failed') {
      stopPolling()
      collectError.value = t.error || '未知错误'
    }
  } catch { /* ignore */ }
}

async function load() {
  loading.value = true
  ideas.value = await api.getIdeas(statusFilter.value || undefined)
  loading.value = false
}

onMounted(load)

function parseTags(tags: string | null): string[] {
  if (!tags) return []
  try {
    const arr = JSON.parse(tags)
    return Array.isArray(arr) ? arr : tags.split(',').map(t => t.trim()).filter(Boolean)
  } catch {
    return tags.split(',').map(t => t.trim()).filter(Boolean)
  }
}

// --- Detail/Editor ---
async function openDetail(idea: IdeaOut) {
  detailIdea.value = idea
  detailTitle.value = idea.title
  detailTags.value = idea.tags || ''
  detailBody.value = ''
  detailOriginal.value = ''
  detailDirty.value = false
  detailLoading.value = true
  expandInstruction.value = ''
  expandStatus.value = ''
  expandStep.value = ''
  expandError.value = ''
  expandTaskId.value = ''
  if (expandTimer) { clearInterval(expandTimer); expandTimer = null }
  showDetail.value = true
  try {
    const data = await api.getIdeaBody(idea.id)
    detailBody.value = data.body
    detailOriginal.value = data.body
  } catch (e: any) {
    detailBody.value = ''
    showToast(e.message, 'error')
  } finally {
    detailLoading.value = false
  }
}

function onDetailInput() {
  detailDirty.value = detailBody.value !== detailOriginal.value || detailTitle.value !== (detailIdea.value?.title || '') || detailTags.value !== (detailIdea.value?.tags || '')
}

async function saveDetail() {
  if (!detailIdea.value || !detailTitle.value.trim()) return
  saving.value = true
  try {
    await api.updateIdea(detailIdea.value.id, {
      title: detailTitle.value,
      content: detailBody.value,
      tags: detailTags.value,
    })
    detailOriginal.value = detailBody.value
    detailDirty.value = false
    showToast('已保存')
    load()
  } catch (e: any) {
    showToast(e.message, 'error')
  } finally {
    saving.value = false
  }
}

async function copyDetail() {
  await navigator.clipboard.writeText(detailBody.value)
  copied.value = true
  setTimeout(() => copied.value = false, 2000)
}

// --- AI Expand ---
async function pollExpand() {
  if (!expandTaskId.value) return
  try {
    const t = await api.getTask(expandTaskId.value)
    expandStatus.value = t.status
    expandStep.value = t.current_step || ''
    if (t.status === 'completed') {
      if (expandTimer) { clearInterval(expandTimer); expandTimer = null }
      // Reload body
      if (detailIdea.value) {
        const data = await api.getIdeaBody(detailIdea.value.id)
        detailBody.value = data.body
        detailOriginal.value = data.body
        detailDirty.value = false
      }
      showToast('AI 扩充完成，内容已更新')
    } else if (t.status === 'failed') {
      if (expandTimer) { clearInterval(expandTimer); expandTimer = null }
      expandError.value = t.error || '未知错误'
    }
  } catch { /* ignore */ }
}

async function submitExpand() {
  if (!detailIdea.value || !expandInstruction.value.trim()) return
  expandSubmitting.value = true
  try {
    const res = await api.expandIdea(detailIdea.value.id, expandInstruction.value)
    expandTaskId.value = res.task_id
    expandStatus.value = 'running'
    expandStep.value = 'Starting...'
    expandError.value = ''
    expandInstruction.value = ''
    expandTimer = setInterval(pollExpand, 3000)
  } catch (e: any) {
    showToast(e.message, 'error')
  } finally {
    expandSubmitting.value = false
  }
}

// --- Add ---
function openAdd() {
  addTitle.value = ''
  addContent.value = ''
  addTags.value = ''
  showAdd.value = true
}

async function saveAdd() {
  if (!addTitle.value.trim()) return
  addSaving.value = true
  try {
    await api.createIdea({ title: addTitle.value, content: addContent.value, tags: addTags.value })
    showAdd.value = false
    showToast('灵感已添加')
    load()
  } catch (e: any) {
    showToast(e.message, 'error')
  } finally {
    addSaving.value = false
  }
}

// --- AI Collect ---
function openCollect() {
  collectSource.value = ''
  collectStatus.value = ''
  collectStep.value = ''
  collectResult.value = null
  collectError.value = ''
  collectTaskId.value = ''
  stopPolling()
  showCollect.value = true
}

async function submitCollect() {
  if (!collectSource.value.trim()) return
  collectSubmitting.value = true
  try {
    const res = await api.collectIdeas(collectSource.value)
    collectTaskId.value = res.task_id
    collectStatus.value = 'running'
    collectStep.value = 'Starting...'
    pollTimer = setInterval(pollCollect, 3000)
  } catch (e: any) {
    showToast(e.message, 'error')
  } finally {
    collectSubmitting.value = false
  }
}

// --- Create article from idea (navigate to ContentsView) ---
function openCreateFromDetail() {
  if (!detailIdea.value) return
  showDetail.value = false
  router.push('/contents?create_from_idea=' + detailIdea.value.id)
}

function openCreateDialog(idea: IdeaOut) {
  router.push('/contents?create_from_idea=' + idea.id)
}

// --- Delete ---
function confirmDelete(idea: IdeaOut) {
  deleteTarget.value = idea
  showDeleteConfirm.value = true
}

async function doDelete() {
  if (!deleteTarget.value) return
  deleting.value = true
  try {
    await api.deleteIdea(deleteTarget.value.id)
    showDeleteConfirm.value = false
    showDetail.value = false
    showToast('已删除')
    load()
  } catch (e: any) {
    showToast(e.message, 'error')
  } finally {
    deleting.value = false
  }
}
</script>

<template>
  <div>
    <div class="page-header">
      <h1>灵感池</h1>
      <div style="display: flex; gap: 6px;">
        <button class="icon-btn primary" data-tip="AI 采集" @click="openCollect">
          <svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
        </button>
        <button class="icon-btn primary" data-tip="手动添加" @click="openAdd">
          <svg viewBox="0 0 24 24"><path d="M12 5v14M5 12h14"/></svg>
        </button>
      </div>
    </div>

    <div class="filters">
      <select v-model="statusFilter" @change="load">
        <option value="">全部状态</option>
        <option value="pending">待使用</option>
        <option value="used">已使用</option>
        <option value="archived">已归档</option>
      </select>
    </div>

    <div v-if="loading" class="loading">加载中...</div>

    <table v-else-if="ideas.length">
      <thead>
        <tr>
          <th>标题</th>
          <th>标签</th>
          <th>来源</th>
          <th>状态</th>
          <th>创建时间</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="idea in ideas" :key="idea.id">
          <td>
            <a href="#" style="color: #1976d2; text-decoration: none;" @click.prevent="openDetail(idea)">
              {{ idea.title }}
            </a>
          </td>
          <td>
            <span v-for="tag in parseTags(idea.tags)" :key="tag" class="tag">{{ tag }}</span>
          </td>
          <td>{{ idea.source }}</td>
          <td><span :class="'badge badge-' + idea.status">{{ idea.status }}</span></td>
          <td>{{ idea.created_at }}</td>
          <td class="actions">
            <button class="icon-btn" data-tip="查看" @click="openDetail(idea)">
              <svg viewBox="0 0 24 24"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
            </button>
            <button class="icon-btn" data-tip="编辑" @click="openDetail(idea)">
              <svg viewBox="0 0 24 24"><path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
            </button>
            <button v-if="idea.status === 'pending'" class="icon-btn primary" data-tip="创建文章" @click="openCreateDialog(idea)">
              <svg viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="12" y1="18" x2="12" y2="12"/><line x1="9" y1="15" x2="15" y2="15"/></svg>
            </button>
            <button class="icon-btn danger" data-tip="删除" @click="confirmDelete(idea)">
              <svg viewBox="0 0 24 24"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/></svg>
            </button>
          </td>
        </tr>
      </tbody>
    </table>

    <div v-else class="empty">暂无灵感</div>

    <!-- Detail/Editor Modal -->
    <div v-if="showDetail" class="modal-overlay" @click.self="showDetail = false">
      <div class="modal idea-editor-modal">
        <!-- Editable title + tags -->
        <div class="idea-editor-header">
          <input v-model="detailTitle" class="idea-title-input" placeholder="灵感标题" @input="onDetailInput" />
          <input v-model="detailTags" class="idea-tags-input" placeholder="标签（逗号分隔）" @input="onDetailInput" />
        </div>

        <div v-if="detailLoading" class="loading">加载中...</div>
        <template v-else>
          <!-- Editable body -->
          <textarea v-model="detailBody" class="idea-editor-textarea" @input="onDetailInput"></textarea>

          <!-- Action bar -->
          <div class="editor-actions">
            <div class="editor-actions-left">
              <button class="icon-btn primary" :data-tip="saving ? '保存中...' : detailDirty ? '保存修改' : '无变更'" :disabled="!detailDirty || saving" @click="saveDetail">
                <svg viewBox="0 0 24 24"><path d="M19 21H5a2 2 0 01-2-2V5a2 2 0 012-2h11l5 5v11a2 2 0 01-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg>
              </button>
              <button class="icon-btn" :data-tip="copied ? '已复制' : '复制'" @click="copyDetail">
                <svg viewBox="0 0 24 24"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg>
              </button>
              <button class="icon-btn danger" data-tip="删除" @click="detailIdea && confirmDelete(detailIdea)">
                <svg viewBox="0 0 24 24"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/></svg>
              </button>
            </div>
            <div style="display: flex; gap: 8px; align-items: center;">
              <button v-if="detailIdea?.status === 'pending'" class="btn btn-primary btn-sm" @click="openCreateFromDetail">
                创建文章
              </button>
              <button class="icon-btn" data-tip="关闭" @click="showDetail = false">
                <svg viewBox="0 0 24 24"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
              </button>
            </div>
          </div>

          <!-- AI Expand section -->
          <div class="ai-section">
            <div class="ai-section-title">AI 扩充</div>

            <div v-if="expandStatus === 'running'" class="ai-expand-progress">
              <span class="spinner"></span>
              <span>{{ expandStep }}</span>
            </div>
            <div v-else-if="expandStatus === 'completed'" class="ai-expand-progress" style="background: #e8f5e9; color: #2e7d32;">
              内容已更新
            </div>
            <div v-else-if="expandStatus === 'failed'" class="ai-expand-progress" style="background: #fce4ec; color: #c62828;">
              失败: {{ expandError }}
            </div>

            <div class="ai-input-row">
              <textarea
                v-model="expandInstruction"
                class="ai-textarea"
                :disabled="expandStatus === 'running'"
                placeholder="输入指令让 AI 继续研究、扩充、细化这条灵感...&#10;例: 补充心理学理论支撑&#10;例: 找3个类似话题的热门切入角度"
              ></textarea>
              <button
                class="btn btn-primary"
                :disabled="expandSubmitting || !expandInstruction.trim() || expandStatus === 'running'"
                @click="submitExpand"
              >
                {{ expandSubmitting ? '提交中...' : expandStatus === 'running' ? 'AI 处理中...' : 'AI 扩充' }}
              </button>
            </div>
          </div>
        </template>
      </div>
    </div>

    <!-- Add Modal -->
    <div v-if="showAdd" class="modal-overlay" @click.self="showAdd = false">
      <div class="modal" style="min-width: 560px;">
        <h3>添加灵感</h3>
        <div class="form-group">
          <label>标题</label>
          <input v-model="addTitle" type="text" placeholder="灵感标题" />
        </div>
        <div class="form-group">
          <label>标签（逗号分隔）</label>
          <input v-model="addTags" type="text" placeholder="标签1,标签2,标签3" />
        </div>
        <div class="form-group">
          <label>内容</label>
          <textarea v-model="addContent" style="min-height: 150px;" placeholder="灵感描述、参考资料、切入角度..."></textarea>
        </div>
        <div class="modal-actions">
          <button class="btn btn-secondary" @click="showAdd = false">取消</button>
          <button class="btn btn-primary" :disabled="addSaving || !addTitle.trim()" @click="saveAdd">
            {{ addSaving ? '保存中...' : '保存' }}
          </button>
        </div>
      </div>
    </div>

    <!-- AI Collect Modal -->
    <div v-if="showCollect" class="modal-overlay" @click.self="showCollect = false">
      <div class="modal" style="min-width: 520px;">
        <h3>AI 采集灵感</h3>
        <p style="font-size: 12px; color: #999; margin-bottom: 12px;">
          输入主题、关键词或 URL，AI 会自动搜集并提炼灵感
        </p>

        <div v-if="collectStatus === 'running'" class="ai-collect-progress">
          <span class="spinner"></span>
          <span>{{ collectStep }}</span>
        </div>
        <div v-else-if="collectStatus === 'completed'" class="ai-collect-progress" style="background: #e8f5e9; color: #2e7d32;">
          采集完成：发现 {{ collectResult?.collected || 0 }} 条，入库 {{ collectResult?.saved || 0 }} 条
        </div>
        <div v-else-if="collectStatus === 'failed'" class="ai-collect-progress" style="background: #fce4ec; color: #c62828;">
          失败: {{ collectError }}
        </div>

        <div class="form-group">
          <label>素材源</label>
          <textarea
            v-model="collectSource"
            :disabled="collectStatus === 'running'"
            placeholder="例: 亲密关系中的回避型依恋&#10;或: https://example.com/article&#10;或: 最近小红书上关于星座合盘的热门话题"
            style="min-height: 100px;"
          ></textarea>
        </div>
        <div class="modal-actions">
          <button class="btn btn-secondary" @click="showCollect = false">关闭</button>
          <button
            class="btn btn-primary"
            :disabled="collectSubmitting || !collectSource.trim() || collectStatus === 'running'"
            @click="submitCollect"
          >
            {{ collectSubmitting ? '提交中...' : collectStatus === 'running' ? 'AI 采集中...' : '开始采集' }}
          </button>
        </div>
      </div>
    </div>

    <!-- Delete Confirm -->
    <div v-if="showDeleteConfirm" class="modal-overlay" @click.self="showDeleteConfirm = false">
      <div class="modal" style="min-width: 360px;">
        <h3>确认删除</h3>
        <p style="margin: 12px 0; font-size: 14px;">确定要删除灵感「{{ deleteTarget?.title }}」吗？此操作不可恢复。</p>
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
.idea-editor-modal {
  min-width: 700px;
  max-width: 850px;
}

.idea-editor-header {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 12px;
}

.idea-title-input {
  font-size: 18px;
  font-weight: 600;
  border: none;
  border-bottom: 1px solid #eee;
  padding: 6px 0;
  outline: none;
}

.idea-title-input:focus {
  border-bottom-color: #1976d2;
}

.idea-tags-input {
  font-size: 12px;
  color: #666;
  border: none;
  border-bottom: 1px solid #f0f0f0;
  padding: 4px 0;
  outline: none;
}

.idea-tags-input:focus {
  border-bottom-color: #90caf9;
}

.idea-editor-textarea {
  width: 100%;
  min-height: 35vh;
  padding: 14px;
  border: 1px solid #ddd;
  border-radius: 8px;
  font-size: 14px;
  line-height: 1.7;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  resize: vertical;
  background: #fafafa;
}

.idea-editor-textarea:focus {
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
  gap: 4px;
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

.ai-expand-progress,
.ai-collect-progress {
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
</style>
