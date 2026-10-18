<template>
  <aside class="w-72 bg-white border-r border-gray-200 flex flex-col shrink-0">
    <!-- Logo -->
    <div class="p-5 border-b border-gray-100">
      <div class="flex items-center gap-3">
        <div class="w-10 h-10 bg-gradient-to-br from-blue-500 to-indigo-600 rounded-xl flex items-center justify-center shadow-lg shadow-blue-200">
          <Zap class="w-5 h-5 text-white" />
        </div>
        <div>
          <h1 class="font-bold text-gray-900 text-lg leading-tight">新能源 Agent</h1>
          <p class="text-xs text-gray-400">知识助手 v2.0</p>
        </div>
      </div>
    </div>

    <!-- 配置区 -->
    <div class="p-4 space-y-4 overflow-y-auto flex-1">
      <!-- 模型选择 -->
      <div>
        <label class="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2 block">模型</label>
        <select 
          v-model="store.settings.provider"
          class="w-full px-3 py-2 bg-gray-50 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          <option value="deepseek">DeepSeek</option>
          <option value="本地模型（免费）">本地 Ollama</option>
        </select>
      </div>

      <!-- 通信模式 -->
      <div>
        <label class="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2 block">通信模式</label>
        <select 
          v-model="store.settings.commMode"
          class="w-full px-3 py-2 bg-gray-50 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          <option value="rest">REST API</option>
          <option value="sse">SSE 流式</option>
          <option value="ws">WebSocket</option>
        </select>
      </div>

      <!-- API 地址 -->
      <div>
        <label class="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2 block">后端地址</label>
        <input 
          v-model="store.settings.apiUrl"
          type="text"
          class="w-full px-3 py-2 bg-gray-50 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
      </div>

      <!-- 显示设置 -->
      <div class="space-y-2">
        <label class="flex items-center gap-2 cursor-pointer">
          <input 
            v-model="store.settings.showReasoning" 
            type="checkbox" 
            class="w-4 h-4 text-blue-600 rounded focus:ring-blue-500"
          >
          <span class="text-sm text-gray-700">显示 Agent 思考过程</span>
        </label>
        <label class="flex items-center gap-2 cursor-pointer">
          <input 
            v-model="store.settings.showSources" 
            type="checkbox" 
            class="w-4 h-4 text-blue-600 rounded focus:ring-blue-500"
          >
          <span class="text-sm text-gray-700">显示引用来源</span>
        </label>
      </div>

      <!-- 清空按钮 -->
      <div class="border-t border-gray-100 pt-4">
        <button 
          @click="store.clearChat()"
          class="w-full flex items-center justify-center gap-2 px-4 py-2 text-sm text-red-600 bg-red-50 hover:bg-red-100 rounded-lg transition-colors"
        >
          <Trash2 class="w-4 h-4" />
          清空对话
        </button>
      </div>

      <!-- 文件上传 -->
      <div class="border-t border-gray-100 pt-4">
        <label class="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2 block">文档上传</label>
        <div 
          class="upload-zone"
          :class="{ dragover: isDragging }"
          @click="fileInput?.click()"
          @dragover.prevent="isDragging = true"
          @dragleave="isDragging = false"
          @drop.prevent="handleDrop"
        >
          <UploadCloud class="w-8 h-8 text-gray-400 mx-auto mb-2" />
          <p class="text-sm text-gray-500">点击或拖拽上传</p>
          <p class="text-xs text-gray-400 mt-1">PDF / Word / TXT</p>
        </div>
        <input 
          ref="fileInput"
          type="file" 
          class="hidden" 
          accept=".pdf,.doc,.docx,.txt"
          @change="handleFileChange"
        >
        <div v-if="uploadStatus" class="mt-2 text-xs" v-html="uploadStatus"></div>
      </div>

      <!-- 状态信息 -->
      <div class="border-t border-gray-100 pt-4">
        <div class="flex items-center gap-2 text-xs text-gray-400">
          <div 
            class="w-2 h-2 rounded-full"
            :class="{
              'bg-green-500': store.connStatus === 'connected',
              'bg-amber-500 animate-pulse': store.connStatus === 'connecting',
              'bg-gray-300': store.connStatus === 'disconnected'
            }"
          />
          <span>{{ connStatusText }}</span>
        </div>
        <p class="text-xs text-gray-400 mt-1">
          Thread ID: <span class="font-mono">{{ threadIdShort }}</span>
        </p>
      </div>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { Zap, Trash2, UploadCloud } from 'lucide-vue-next'
import { useChatStore } from '@/stores/chat'
import { api } from '@/services/api'

const store = useChatStore()
const fileInput = ref<HTMLInputElement>()
const isDragging = ref(false)
const uploadStatus = ref('')

const connStatusText = computed(() => {
  const map: Record<string, string> = {
    connected: '已连接',
    connecting: '连接中...',
    disconnected: '未连接'
  }
  return map[store.connStatus] || '未知'
})

const threadIdShort = computed(() => {
  if (!store.threadId) return '-'
  return store.threadId.substring(0, 8) + '...'
})

async function handleFileChange(e: Event) {
  const target = e.target as HTMLInputElement
  if (target.files?.length) {
    await uploadFile(target.files[0])
  }
}

async function handleDrop(e: DragEvent) {
  isDragging.value = false
  if (e.dataTransfer?.files.length) {
    await uploadFile(e.dataTransfer.files[0])
  }
}

async function uploadFile(file: File) {
  uploadStatus.value = '<span class="text-blue-600">上传中...</span>'
  try {
    const res = await api.upload(file)
    uploadStatus.value = `<span class="text-green-600">✅ ${res.filename} 已入库 (${res.chunk_count} 块)</span>`
  } catch (err: any) {
    uploadStatus.value = `<span class="text-red-600">❌ ${err.response?.data?.detail || '上传失败'}</span>`
  }
  setTimeout(() => { uploadStatus.value = '' }, 5000)
}
</script>
