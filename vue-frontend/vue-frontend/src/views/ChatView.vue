<template>
  <div class="h-screen flex overflow-hidden">
    <!-- 侧边栏 -->
    <Sidebar />

    <!-- 主聊天区 -->
    <main class="flex-1 flex flex-col min-w-0">
      <!-- 顶部栏 -->
      <header class="h-14 bg-white border-b border-gray-200 flex items-center justify-between px-6 shrink-0">
        <div class="flex items-center gap-2">
          <span class="agent-badge badge-ok">
            <CheckCircle class="w-3 h-3" />
            Agent 就绪
          </span>
        </div>
      </header>

      <!-- 消息列表 -->
      <MessageList />

      <!-- HITL 审核面板 -->
      <HITLPanel 
        v-if="store.isInterrupted" 
        :data="store.interruptData"
        @review="chat.sendReview"
      />

      <!-- 输入区 -->
      <ChatInput @send="chat.sendMessage" />
    </main>
  </div>
</template>

<script setup lang="ts">
import { CheckCircle } from 'lucide-vue-next'
import { useChatStore } from '@/stores/chat'
import { useChat } from '@/composables/useChat'
import Sidebar from '@/components/Sidebar.vue'
import MessageList from '@/components/MessageList.vue'
import HITLPanel from '@/components/HITLPanel.vue'
import ChatInput from '@/components/ChatInput.vue'

const store = useChatStore()
const chat = useChat()
</script>
