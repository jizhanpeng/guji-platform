import { createRouter, createWebHistory } from 'vue-router'

export default createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/dashboard' },
    { path: '/dashboard', component: () => import('../views/DashboardView.vue'), meta: { title: '总览' } },
    { path: '/images', component: () => import('../views/ImageListView.vue'), meta: { title: '图像' } },
    { path: '/annotate/:id', component: () => import('../views/CharAnnotateView.vue'), meta: { title: '标注' } },
    { path: '/damage/:id', component: () => import('../views/DamageAnnotateView.vue'), meta: { title: '破损' } },
    { path: '/styles', component: () => import('../views/StylesView.vue'), meta: { title: '风格' } },
    { path: '/crops', component: () => import('../views/CropsView.vue'), meta: { title: '裁剪' } },
    { path: '/jobs', component: () => import('../views/JobsView.vue'), meta: { title: '任务' } },
  ],
})
