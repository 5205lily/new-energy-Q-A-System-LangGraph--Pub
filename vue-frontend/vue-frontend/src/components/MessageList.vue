<template>
  <div ref="container" class="flex-1 overflow-y-auto px-4 py-6 space-y-6">
    <!-- 欢迎消息 -->
    <div v-if="!store.hasMessages" class="msg-anim flex gap-4 max-w-3xl mx-auto">
      <div class="w-8 h-8 bg-gradient-to-br from-blue-500 to-indigo-600 rounded-full flex items-center justify-center shrink-0">
        <Bot class="w-4 h-4 text-white" />
      </div>
      <div class="flex-1">
        <div class="bg-white border border-gray-200 rounded-2xl rounded-tl-sm px-5 py-4 shadow-sm">
          <p class="text-gray-800 leading-relaxed">
            你好！我是<strong>新能源运维 Agent 助手</strong>。我可以帮你：
          </p>
          <ul class="mt-2 space-y-1 text-gray-600 text-sm">
            <li class="flex items-center gap-2"><Search class="w-4 h-4 text-blue-500" />从知识库检索技术资料</li>
            <li class="flex items-center gap-2"><Calculator class="w-4 h-4 text-blue-500" />执行数值计算与换算</li>
            <li class="flex items-center gap-2"><BarChart3 class="w-4 h-4 text-blue-500" />生成数据可视化图表</li>
            <li class="flex items-center gap-2"><ShieldCheck class="w-4 h-4 text-blue-500" />自动检测并纠正回答质量</li>
          </ul>
          <p class="mt-3 text-sm text-gray-500">试试问我关于风电、光伏、储能的问题吧！</p>
        </div>
      </div>
    </div>

    <!-- 消息列表 -->
    <MessageItem v-for="msg in store.messages" :key="msg.id" :message="msg" />

    <!-- 打字指示器 -->
    <TypingIndicator v-if="store.isStreaming && !store.isInterrupted" />
  </div>
</template>

<script setup lang="ts">
import { ref, watch, nextTick } from 'vue'
import { Bot, Search, Calculator, BarChart3, ShieldCheck } from 'lucide-vue-next'
import { useChatStore } from '@/stores/chat'
import MessageItem from './MessageItem.vue'
import TypingIndicator from './TypingIndicator.vue'

const store = useChatStore()
const container = ref<HTMLElement>()

watch(() => store.messages.length, () => {
  nextTick(() => {
    if (container.value) {
      container.value.scrollTop = container.value.scrollHeight
    }
  })
})
</script>
