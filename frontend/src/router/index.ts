import { createRouter, createWebHistory } from 'vue-router'

export default createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/images' },
    { path: '/images', component: () => import('../views/ImageListView.vue'), meta: { title: '图像' } },
    { path: '/annotate/:id', component: () => import('../views/CharAnnotateView.vue'), meta: { title: '标注' } },
    { path: '/jobs', component: () => import('../views/JobsView.vue'), meta: { title: '任务' } },
  ],
})
