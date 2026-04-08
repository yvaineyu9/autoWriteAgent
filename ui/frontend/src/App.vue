<template>
  <div class="app-layout">
    <aside class="sidebar">
      <h2>autoWrite</h2>
      <div class="persona-selector" v-if="personas.length">
        <select v-model="currentPersona" @change="onPersonaChange">
          <option v-for="p in personas" :key="p.id" :value="p.id">{{ p.name }}</option>
        </select>
      </div>
      <nav>
        <router-link to="/">仪表盘</router-link>
        <router-link to="/ideas">灵感池</router-link>
        <router-link to="/contents">成品仓库</router-link>
        <router-link to="/select">选文发布</router-link>
        <router-link to="/publications">发布数据</router-link>
        <router-link to="/tasks">任务监控</router-link>
      </nav>
    </aside>
    <main class="main-content">
      <div class="flow-bar">
        <template v-for="(step, i) in flowSteps" :key="i">
          <span v-if="i > 0" class="flow-sep">&rarr;</span>
          <router-link
            :to="step.path"
            class="flow-step"
            :class="{ 'flow-active': currentPath === step.path }"
          >{{ step.label }}</router-link>
        </template>
      </div>
      <router-view :persona-id="currentPersona" :personas="personas" />
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, provide, computed } from 'vue'
import { useRoute } from 'vue-router'
import { api } from './api/client'
import type { PersonaOut } from './types'

const route = useRoute()

const flowSteps = [
  { label: '采集灵感', path: '/ideas' },
  { label: '创作文章', path: '/contents' },
  { label: '排版生图', path: '/contents' },
  { label: '选文', path: '/select' },
  { label: '发布', path: '/publications' },
  { label: '数据跟踪', path: '/publications' },
]

const currentPath = computed(() => route.path)

const personas = ref<PersonaOut[]>([])
const currentPersona = ref('')

provide('currentPersona', currentPersona)
provide('personas', personas)

onMounted(async () => {
  try {
    personas.value = await api.getPersonas()
    const saved = localStorage.getItem('persona_id')
    if (saved && personas.value.some(p => p.id === saved)) {
      currentPersona.value = saved
    } else if (personas.value.length) {
      currentPersona.value = personas.value[0].id
    }
  } catch {
    // fallback
    currentPersona.value = 'yuejian'
  }
})

function onPersonaChange() {
  localStorage.setItem('persona_id', currentPersona.value)
}
</script>
