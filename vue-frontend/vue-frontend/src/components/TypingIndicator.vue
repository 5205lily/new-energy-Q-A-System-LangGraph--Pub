<template>
  <div class="msg-anim flex gap-4 max-w-3xl mx-auto">
    <div class="w-8 h-8 bg-gradient-to-br from-blue-500 to-indigo-600 rounded-full flex items-center justify-center shrink-0">
      <Bot class="w-4 h-4 text-white" />
    </div>
    <div class="flex-1">
      <div class="bg-white border border-gray-200 rounded-2xl rounded-tl-sm px-5 py-4 shadow-sm">
        <div class="flex items-center gap-2">
          <div class="dot-flashing"></div>
          <span class="text-sm text-gray-500">Agent 正在思考...</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Bot } from 'lucide-vue-next'
</script>
