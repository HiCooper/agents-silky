---
name: create-vitepress-docs
description: 在新项目中创建 VitePress 产品文档站点脚手架。基于标准产品文档结构（dev/技术文档、guide/产品指南、knowledge/内部知识），包含导航配置、侧边栏、Mermaid 图表支持。触发场景：用户需要创建产品文档、API 文档、技术文档站点，或要求初始化文档项目。
---

# Create VitePress Docs

## 功能概述

在当前项目中创建标准化的 VitePress 产品文档站点，包含完整配置和目录结构。

## 使用前提

1. 当前目录是项目根目录或指定的项目目录
2. 需要创建 `docs/` 或 `docs-site/` 目录

## 执行步骤

### Step 1: 确定项目名称和站点配置

需要从用户获取以下信息：
- **项目/产品名称**：用于站点标题（如 "Hydra"、"MyProduct"）
- **项目描述**：一句话描述（用于 SEO meta description）
- **GitHub 仓库地址**：用于编辑链接（如 `https://github.com/org/repo`）
- **文档目录名**：`docs` 或 `docs-site`（默认 `docs-site`）

### Step 2: 创建目录结构

```
docs-site/
├── .vitepress/
│   └── config.ts          # VitePress 配置
├── public/
│   └── logo.svg           # Logo 文件（创建占位符）
├── guide/                  # 产品指南
│   ├── index.md
│   ├── getting-started.md
│   ├── what-is-[product].md
│   ├── wall/
│   │   └── introduction.md
│   ├── pay/
│   │   └── introduction.md
│   └── analytics/
│       └── dashboard.md
├── dev/                    # 技术文档
│   ├── index.md
│   ├── architecture/
│   │   └── index.md
│   ├── sdk/
│   │   └── index.md
│   ├── integration/
│   │   └── quick-start.md
│   └── deployment/
│       └── production.md
├── knowledge/              # 内部知识
│   ├── index.md
│   ├── adr/
│   │   └── index.md
│   └── service-endpoints.md
└── index.md               # 首页（hero 页面）
```

### Step 3: 创建 package.json

```json
{
  "name": "docs",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vitepress dev",
    "build": "vitepress build",
    "preview": "vitepress preview"
  },
  "devDependencies": {
    "vitepress": "^1.5.0",
    "vitepress-plugin-mermaid": "^2.0.17",
    "mermaid": "^11.14.0"
  }
}
```

### Step 4: 创建 .vitepress/config.ts

核心配置模板：

```typescript
import { defineConfig } from 'vitepress'
import { withMermaid } from 'vitepress-plugin-mermaid'

export default withMermaid(defineConfig({
  title: '[产品名称]',
  description: '[项目描述]',
  lang: 'zh-CN',
  base: '/',
  
  head: [
    ['link', { rel: 'icon', href: '/logo.svg' }],
  ],

  themeConfig: {
    logo: '/logo.svg',
    nav: [
      { text: '产品指南', link: '/guide/', activeMatch: '^/guide/' },
      { text: '技术文档', link: '/dev/', activeMatch: '^/dev/' },
      { text: '内部知识', link: '/knowledge/', activeMatch: '^/knowledge/' },
    ],
    
    sidebar: {
      '/guide/': guideSidebar,
      '/dev/': devSidebar,
      '/knowledge/': knowledgeSidebar,
    },
    
    search: { provider: 'local' },
    
    socialLinks: [
      { icon: 'github', link: 'https://github.com/[org]/[repo]' },
    ],
  },
  
  markdown: {
    lineNumbers: true,
  },
  
  mermaid: {
    theme: 'base',
  },
}))
```

### Step 5: 创建示例首页 index.md

```markdown
---
layout: home

hero:
  name: "[产品名称]"
  text: "[产品主标题]"
  tagline: "[一句话描述]"
  actions:
    - theme: brand
      text: 快速开始
      link: /guide/getting-started
    - theme: alt
      text: 技术架构
      link: /dev/architecture/

features:
  - icon: 🧱
    title: 功能模块 1
    details: 模块描述
  - icon: 💳
    title: 功能模块 2
    details: 模块描述
  - icon: 📦
    title: 功能模块 3
    details: 模块描述
```

### Step 6: 创建 public/logo.svg

创建简单的 SVG 占位符 logo：

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
  <circle cx="50" cy="50" r="45" fill="#3b82f6"/>
  <text x="50" y="60" text-anchor="middle" fill="white" font-size="40" font-weight="bold">P</text>
</svg>
```

### Step 7: 创建基础文档内容

每个目录创建 index.md 作为概览页面，格式参考：

```markdown
# [目录标题]

## 概述
[简要描述此部分内容]

## 内容导航
- [页面标题](/path/to/page)
- ...
```

## 完成后操作

1. 提示用户运行 `npm install` 安装依赖
2. 提示用户运行 `npm run dev` 启动开发服务器
3. 提醒用户根据实际项目修改：
   - `config.ts` 中的导航和侧边栏配置
   - `index.md` 中的 hero 和 features 内容
   - 替换 logo.svg 为实际品牌标识

## 自定义选项

如果用户需要自定义，可提供以下选项：
- 添加额外的导航标签（如 "博客"、"社区"）
- 修改侧边栏结构
- 添加 Algolia 搜索替代本地搜索
- 配置深色/浅色主题切换
- 添加多语言支持

## 参考模板

此 skill 基于以下标准产品文档站点结构设计：
- Hydra 支付基础设施文档 (docs-site)
- VitePress 官方文档

如需查看完整配置示例，参考：[/Users/xueancao/Projects/QoderProjects/star-river/docs-site/.vitepress/config.ts](/Users/xueancao/Projects/QoderProjects/star-river/docs-site/.vitepress/config.ts)
