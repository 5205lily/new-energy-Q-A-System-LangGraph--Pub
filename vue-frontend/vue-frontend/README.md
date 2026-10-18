# Vue 3 + TypeScript 前端启动指南

## 一、项目结构

```
new-energy-agent-chat/
├── index.html
├── package.json
├── vite.config.ts
├── tsconfig.json
├── tailwind.config.js
├── postcss.config.js
└── src/
    ├── main.ts                 # 入口
    ├── App.vue                 # 根组件
    ├── types/
    │   └── index.ts            # TypeScript 类型定义
    ├── stores/
    │   └── chat.ts             # Pinia 状态管理
    ├── services/
    │   └── api.ts              # API 服务层（REST / SSE / WS）
    ├── utils/
    │   └── markdown.ts         # Markdown 渲染 + 代码高亮
    ├── composables/
    │   └── useChat.ts          # 聊天业务逻辑组合式函数
    ├── components/
    │   ├── Sidebar.vue         # 侧边栏（配置 + 上传）
    │   ├── MessageList.vue     # 消息列表容器
    │   ├── MessageItem.vue     # 单条消息（Markdown + 徽章 + 来源）
    │   ├── ChatInput.vue       # 输入框（自动增高 + 快捷键）
    │   ├── HITLPanel.vue       # 人工审核面板
    │   ├── SourceCards.vue     # 引用来源卡片
    │   └── TypingIndicator.vue # 打字动画
    ├── views/
    │   └── ChatView.vue        # 主视图（组合所有组件）
    └── styles/
        └── index.css           # Tailwind + 自定义样式
```

## 二、技术栈

| 技术 | 版本 | 用途 |
|------|------|------|
| Vue 3 | ^3.5 | 框架 |
| TypeScript | ^5.6 | 类型安全 |
| Vite | ^5.4 | 构建工具 |
| Pinia | ^2.2 | 状态管理 |
| Tailwind CSS | ^3.4 | 样式 |
| Lucide Vue | ^0.44 | 图标 |
| Marked | ^14.0 | Markdown 渲染 |
| Highlight.js | ^11.10 | 代码高亮 |
| Axios | ^1.7 | HTTP 请求 |

## 三、启动步骤

```bash
# 1. 进入项目目录
cd vue-frontend

# 2. 安装依赖
npm install

# 3. 启动开发服务器
npm run dev
# 访问 http://localhost:3000

# 4. 生产构建
npm run build
# 输出到 dist/ 目录
```

## 四、与后端联调

### 开发环境（Vite Proxy）
`vite.config.ts` 已配置代理：
```ts
proxy: {
  '/api': { target: 'http://localhost:8000' },
  '/ws':  { target: 'ws://localhost:8000', ws: true }
}
```
前端访问 `/api/chat` 会自动代理到 `http://localhost:8000/api/chat`。

### 生产环境
修改 `.env` 或 `src/stores/chat.ts` 中的 `apiUrl`：
```ts
apiUrl: 'https://your-production-api.com'
```

## 五、核心设计

### 1. 状态管理（Pinia）
```ts
const store = useChatStore()
store.messages      // 消息列表
store.threadId      // 当前会话ID
store.isStreaming   // 是否正在生成
store.interrupted   // 是否被 HITL 中断
store.settings      // 用户配置（模型、通信模式等）
```

### 2. 业务逻辑抽离（Composables）
```ts
const chat = useChat()
chat.sendMessage('问题')   // 自动根据 settings.commMode 选择 REST/SSE/WS
chat.sendReview('approve') // HITL 审核
```

### 3. 三种通信模式切换
侧边栏下拉框切换后，下次发送消息自动生效，无需刷新页面。

| 模式 | 特点 | 适用场景 |
|------|------|----------|
| REST | 简单可靠，一次性返回 | 默认推荐 |
| SSE | 打字机效果，体验好 | 长回答场景 |
| WebSocket | 双向实时，支持推送 | 多轮对话、实时通知 |

### 4. 组件通信
- **Props + Emit**：父子组件（如 ChatView → ChatInput @send）
- **Pinia Store**：全局状态（消息列表、中断状态）
- **Provide/Inject**：可选，深层嵌套时使用

## 六、扩展开发

### 添加新页面
```ts
// src/router/index.ts
import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/', component: () => import('@/views/ChatView.vue') },
  { path: '/history', component: () => import('@/views/HistoryView.vue') },
  { path: '/settings', component: () => import('@/views/SettingsView.vue') }
]

export const router = createRouter({ history: createWebHistory(), routes })
```

### 添加新组件
```vue
<!-- src/components/MyComponent.vue -->
<template>
  <div>{{ props.title }}</div>
</template>

<script setup lang="ts">
const props = defineProps<{ title: string }>()
</script>
```

### 接入 Element Plus / Ant Design Vue
```bash
npm install element-plus
# 在 main.ts 中引入
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
app.use(ElementPlus)
```

## 七、常见问题

**Q: `npm install` 报错 peer dependency？**
A: 用 `npm install --legacy-peer-deps` 或 `npm install --force`

**Q: 热更新不生效？**
A: 检查 `vite.config.ts` 中 `server.hmr` 配置，或重启 `npm run dev`

**Q: TypeScript 报错 `Cannot find module '@/types'`？**
A: 确保 `tsconfig.json` 中 `paths` 配置正确，且 VSCode 使用的是项目内的 TS 版本

**Q: 代码高亮不生效？**
A: 检查 `highlight.js` 是否已注册语言，`markdown.ts` 中 `hljs.getLanguage(language)` 是否返回 truthy

**Q: 图标显示为方框？**
A: `lucide-vue-next` 需要配合 Vue 3 使用，确保版本匹配。也可用 `@heroicons/vue` 替代
