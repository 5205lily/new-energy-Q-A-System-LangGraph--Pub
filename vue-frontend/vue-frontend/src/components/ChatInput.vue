<template>
  <div class="bg-white border-t border-gray-200 px-4 py-4 shrink-0">
    <div class="max-w-3xl mx-auto relative">
      <textarea
        ref="textarea"
        v-model="text"
        rows="1"
        placeholder="请输入您的问题..."
        class="w-full pl-4 pr-14 py-3 bg-gray-50 border border-gray-200 rounded-xl resize-none focus:outline-none focus:ring-2 focus:ring-blue-500 focus:bg-white transition-all text-sm"
        :disabled="store.isStreaming"
        @keydown="handleKeydown"
        @input="autoResize"
      />
      <button
        @click="submit"
        :disabled="!canSend"
        class="absolute right-2 bottom-2 p-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-lg transition-colors"
      >
        <Send class="w-4 h-4" />
      </button>
    </div>
    <p class="text-center text-xs text-gray-400 mt-2">Agent 可能会犯错，重要决策请核实资料来源</p>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick } from 'vue'
import { Send } from 'lucide-vue-next'
import { useChatStore } from '@/stores/chat'

const store = useChatStore()
const text = ref('')
const textarea = ref<HTMLTextAreaElement>()

const canSend = computed(() => text.value.trim().length > 0 && !store.isStreaming)

const emit = defineEmits<{
  send: [question: string]
}>()

function autoResize() {
  nextTick(() => {
    if (textarea.value) {
      textarea.value.style.height = 'auto'
      textarea.value.style.height = Math.min(textarea.value.scrollHeight, 200) + 'px'
    }
  })
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    submit()
  }
}

function submit() {
  const question = text.value.trim()
  if (!question || store.isStreaming) return
  emit('send', question)
  text.value = ''
  nextTick(() => {
    if (textarea.value) {
      textarea.value.style.height = 'auto'
    }
  })
}
</script>
