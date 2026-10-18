<template>
  <div class="msg-anim flex gap-4 max-w-3xl mx-auto" :class="{ 'flex-row-reverse': isUser }">
    <!-- 头像 -->
    <div 
      class="w-8 h-8 rounded-full flex items-center justify-center shrink-0"
      :class="isUser ? 'bg-gray-700' : 'bg-gradient-to-br from-blue-500 to-indigo-600'"
    >
      <component :is="isUser ? User : Bot" class="w-4 h-4 text-white" />
    </div>

    <!-- 内容区 -->
    <div class="flex-1 min-w-0" :class="{ 'text-right': isUser }">
      <!-- 徽章 -->
      <div v-if="message.badges?.length" class="flex gap-1 mb-2" :class="isUser ? 'justify-end' : ''">
        <span 
          v-for="badge in message.badges" 
          :key="badge"
          class="agent-badge"
          :class="getBadgeClass(badge)"
        >
          {{ badge }}
        </span>
      </div>

      <!-- 消息气泡 -->
      <div 
        class="px-5 py-4 shadow-sm inline-block text-left"
        :class="[
          isUser 
            ? 'bg-gray-800 text-white rounded-2xl rounded-tr-sm' 
            : 'bg-white border border-gray-200 rounded-2xl rounded-tl-sm'
        ]"
      >
        <!-- 用户消息：纯文本 -->
        <p v-if="isUser" class="whitespace-pre-wrap">{{ safeContent }}</p>

        <!-- 助手消息：Markdown -->
        <div v-else class="markdown-body" v-html="renderedContent"></div>

        <!-- 引用来源 -->
        <SourceCards v-if="!isUser && message.sources?.length && store.settings.showSources" :sources="message.sources" />

        <!-- 思考过程 -->
        <div v-if="!isUser && message.reasoning && store.settings.showReasoning" class="reasoning-box">
          {{ message.reasoning }}
        </div>

        <!-- 图表 -->
        <img 
          v-if="!isUser && message.chartPath" 
          :src="message.chartPath" 
          class="mt-3 rounded-lg border border-gray-200 max-w-full"
          alt="Agent 生成的图表"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Bot, User } from 'lucide-vue-next'
import type { ChatMessage } from '@/types'
import { useChatStore } from '@/stores/chat'
import { renderMarkdown } from '@/utils/markdown'
import SourceCards from './SourceCards.vue'

const props = defineProps<{
  message: ChatMessage
}>()

const store = useChatStore()
const isUser = computed(() => props.message.role === 'user')

// 修复：防御性提取内容
const safeContent = computed(() => {
  const content = props.message?.content
  if (typeof content === 'string') return content
  
  if (content && typeof content === 'object') {
    // 尝试提取常见的后端返回字段
    const extracted = content.answer || content.content || content.message || content.detail
    if (extracted && typeof extracted === 'string') return extracted
    // 兜底：转成 JSON 字符串方便调试
    return JSON.stringify(content)
  }
  
  return String(content ?? '')
})

const renderedContent = computed(() => renderMarkdown(safeContent.value))

function getBadgeClass(badge: string): string {
  if (badge.includes('计算')) return 'badge-calc'
  if (badge.includes('图表')) return 'badge-chart'
  if (badge.includes('审核')) return 'badge-hitl'
  return 'badge-ok'
}
</script>