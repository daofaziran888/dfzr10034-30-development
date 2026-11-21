import { createRouter, createWebHistory } from 'vue-router'

import ColumnAuthorizationView from '@/views/ColumnAuthorizationView.vue'
import Overview from '@/views/Overview.vue'
import WorkbenchView from '@/views/WorkbenchView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'overview', component: Overview },
    { path: '/column-authorization', name: 'column-authorization', component: ColumnAuthorizationView },
    { path: '/:moduleKey', name: 'module', component: WorkbenchView, props: true },
  ],
})

export default router
