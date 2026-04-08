import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/ideas' },
    { path: '/ideas', component: () => import('../views/IdeasView.vue') },
    { path: '/contents', component: () => import('../views/ContentsView.vue') },
    { path: '/publications', component: () => import('../views/PublicationsView.vue') },
    { path: '/tasks', component: () => import('../views/TasksView.vue') },
  ],
})

export default router
