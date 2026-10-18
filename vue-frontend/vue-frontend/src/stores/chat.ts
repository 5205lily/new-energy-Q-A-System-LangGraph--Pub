import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { ChatMessage, AppSettings, ConnStatus, InterruptData } from '@/types'

export const useChatStore = defineStore('chat', () => {
  // State
  const messages = ref<ChatMessage[]>([])
  const threadId = ref<string | null>(null)
  const isStreaming = ref(false)
  const interrupted = ref(false)
  const interruptData = ref<InterruptData | null>(null)
  const connStatus = ref<ConnStatus>('disconnected')

  const settings = ref<AppSettings>({
    provider: 'deepseek',
    commMode: 'rest',
    apiUrl: 'http://localhost:8000',
    showReasoning: false,
    showSources: true
  })

  // Getters
  const hasMessages = computed(() => messages.value.length > 0)
  const isInterrupted = computed(() => interrupted.value)

  // Actions
  function addMessage(msg: ChatMessage) {
    messages.value.push(msg)
  }

  function updateLastMessage(partial: Partial<ChatMessage>) {
    const last = messages.value[messages.value.length - 1]
    if (last && last.role === 'assistant') {
      Object.assign(last, partial)
    }
  }

  function setThreadId(id: string) {
    threadId.value = id
  }

  function setStreaming(val: boolean) {
    isStreaming.value = val
  }

  function setInterrupted(val: boolean, data?: InterruptData) {
    interrupted.value = val
    interruptData.value = data || null
  }

  function setConnStatus(status: ConnStatus) {
    connStatus.value = status
  }

  function updateSettings(partial: Partial<AppSettings>) {
    settings.value = { ...settings.value, ...partial }
  }

  function clearChat() {
    messages.value = []
    threadId.value = null
    interrupted.value = false
    interruptData.value = null
  }

  function removeMessage(id: string) {
    messages.value = messages.value.filter(m => m.id !== id)
  }

  return {
    messages, threadId, isStreaming, interrupted, interruptData,
    settings, connStatus,
    hasMessages, isInterrupted,
    addMessage, updateLastMessage, setThreadId, setStreaming,
    setInterrupted, setConnStatus, updateSettings, clearChat, removeMessage
  }
})
