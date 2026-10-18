import { marked } from 'marked'
import hljs from 'highlight.js'

marked.setOptions({
  breaks: true,
  gfm: true,
  headerIds: false,
  mangle: false
})

const renderer = new marked.Renderer()

// v5+ 修复：解构 token 对象
renderer.code = ({ text, lang }: { text: string; lang?: string }) => {
  const validLang = lang && hljs.getLanguage(lang) ? lang : 'plaintext'
  const highlighted = hljs.highlight(text, { language: validLang }).value
  return `<pre><code class="hljs language-${validLang}">${highlighted}</code></pre>`
}

renderer.paragraph = ({ text }: { text: string }) => `<p class="my-2 leading-relaxed text-gray-800">${text}</p>`

renderer.heading = ({ text, depth }: { text: string; depth: number }) => {
  const sizes: Record<number, string> = {
    1: 'text-2xl font-bold my-4',
    2: 'text-xl font-semibold my-3',
    3: 'text-lg font-semibold my-2'
  }
  return `<h${depth} class="${sizes[depth] || 'text-base font-semibold my-2'}">${text}</h${depth}>`
}

renderer.list = ({ items, ordered }: { items: any[]; ordered: boolean }) => {
  const tag = ordered ? 'ol' : 'ul'
  // 简单处理 items，如果报错建议直接删除自定义 list 渲染器
  const body = items.map(item => `<li>${item.text}</li>`).join('')
  return `<${tag} class="my-2 pl-5 space-y-1">${body}</${tag}>`
}

renderer.strong = ({ text }: { text: string }) => `<strong class="font-semibold text-gray-900">${text}</strong>`
renderer.em = ({ text }: { text: string }) => `<em class="italic text-gray-600">${text}</em>`

renderer.link = ({ href, title, text }: { href: string; title: string | null; text: string }) => {
  return `<a href="${href}" target="_blank" class="text-blue-600 hover:underline">${text}</a>`
}

// 注意：marked v5+ 中 table 等复杂渲染器签名也变了，建议直接删掉自定义 table 渲染，使用默认即可，避免报错。
// 或者保留你原有的段落/标题/粗体等简单的渲染器即可。

marked.use({ renderer })

export function renderMarkdown(text: string): string {
  return marked.parse(text) as string
}

export function escapeHtml(text: string): string {
  const div = document.createElement('div')
  div.textContent = text
  return div.innerHTML
}
