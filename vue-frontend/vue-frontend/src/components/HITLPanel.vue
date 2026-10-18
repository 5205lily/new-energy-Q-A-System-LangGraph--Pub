<template>
  <div class="bg-amber-50 border-t border-amber-200 px-6 py-4">
    <div class="max-w-3xl mx-auto">
      <div class="flex items-center gap-2 mb-3">
        <AlertTriangle class="w-5 h-5 text-amber-600" />
        <h3 class="font-semibold text-amber-800">Agent 执行已暂停，等待人工审核</h3>
      </div>
      <p class="text-sm text-amber-700 mb-3">{{ data?.reasoning || '检测到回答可能包含资料中未提及的信息' }}</p>
      <div class="flex gap-3">
        <button 
          @click="$emit('review', 'approve')"
          class="px-4 py-2 bg-green-600 text-white text-sm rounded-lg hover:bg-green-700 transition-colors flex items-center gap-2"
        >
          <Check class="w-4 h-4" />
          通过
        </button>
        <button 
          @click="$emit('review', 'retry')"
          class="px-4 py-2 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700 transition-colors flex items-center gap-2"
        >
          <RefreshCw class="w-4 h-4" />
          重试
        </button>
        <button 
          @click="$emit('review', 'reject')"
          class="px-4 py-2 bg-red-600 text-white text-sm rounded-lg hover:bg-red-700 transition-colors flex items-center gap-2"
        >
          <X class="w-4 h-4" />
          拒绝
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { AlertTriangle, Check, RefreshCw, X } from 'lucide-vue-next'
import type { InterruptData } from '@/types'

defineProps<{
  data: InterruptData | null
}>()

defineEmits<{
  review: [action: 'approve' | 'retry' | 'reject']
}>()
</script>
