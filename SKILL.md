# Feishu to Markdown Skill

将飞书文章转换为Obsidian兼容的Markdown（含图片）。

## 流程

1. 解析URL -> API获取文档块
2. 块转MD（保留格式）
3. Cookie鉴权下载CDN图片
4. 生成frontmatter + Obsidian优化

## Cookie获取

首次使用需要配置Cookie（一次配置，永久使用）：
- 自动：python feishu_to_md.py --refresh-cookies
- 手动：Chrome F12 -> Console -> document.cookie
