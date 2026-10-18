<template>
  <div class="mt-3 pt-3 border-t border-gray-100">
    <p class="text-xs font-semibold text-gray-500 mb-2 flex items-center gap-1">
      <BookOpen class="w-3 h-3" />
      引用来源
    </p>
    <div class="space-y-1.5">
      <div v-for="(source, i) in sources" :key="i" class="source-card">
        <p class="text-xs font-semibold text-gray-700">{{ source.title }}</p>
        <p class="text-xs text-gray-500 mt-1">{{ source.snippet }}</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { BookOpen } from 'lucide-vue-next'
import type { SourceInfo } from '@/types'

defineProps<{
  sources: SourceInfo[]
}>()
</script>
