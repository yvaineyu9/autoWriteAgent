<template>
  <div class="app-layout">
    <aside class="sidebar">
      <h2>autoWrite</h2>
      <nav>
        <router-link to="/ideas">灵感池</router-link>
        <router-link to="/contents">成品仓库</router-link>
        <router-link to="/publications">发布数据</router-link>
        <router-link to="/tasks">任务监控</router-link>
      </nav>
    </aside>
    <main class="main-content">
      <router-view />
    </main>
  </div>
</template>
