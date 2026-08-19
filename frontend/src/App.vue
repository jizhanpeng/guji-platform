<script setup lang="ts">
import { NConfigProvider, NLayout, NLayoutSider, NLayoutContent, NMenu, NMessageProvider, zhCN, dateZhCN } from 'naive-ui'
import type { MenuOption } from 'naive-ui'
import { computed, h } from 'vue'
import { RouterLink, useRoute } from 'vue-router'

const route = useRoute()
const activeKey = computed(() => route.path)

const menuOptions: MenuOption[] = [
  { label: () => h(RouterLink, { to: '/images' }, { default: () => '图像管理' }), key: '/images' },
  { label: () => h(RouterLink, { to: '/styles' }, { default: () => '风格管理' }), key: '/styles' },
  { label: () => h(RouterLink, { to: '/jobs' }, { default: () => '任务中心' }), key: '/jobs' },
]
</script>

<template>
  <n-config-provider :locale="zhCN" :date-locale="dateZhCN">
    <n-message-provider>
      <n-layout style="height: 100vh">
        <n-layout-sider bordered width="180">
          <div style="padding: 16px; font-weight: 600; font-size: 16px">古籍数据平台</div>
          <n-menu :value="activeKey" :options="menuOptions" />
        </n-layout-sider>
        <n-layout-content style="padding: 16px; overflow: auto">
          <router-view />
        </n-layout-content>
      </n-layout>
    </n-message-provider>
  </n-config-provider>
</template>
