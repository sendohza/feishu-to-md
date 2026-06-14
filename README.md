# Feishu to Markdown (v7.0)

将飞书文档/知识库转换为 Obsidian 兼容的 Markdown 文件，支持自动图片下载。

## 特性

- **公开链接直转**（v7.0 新增）：无需 API 凭证，浏览器渲染后自动提取
- **API 模式**：通过飞书 Open API 获取完整结构化内容
- **图片自动本地化**：Canvas 截取 blob 图片 + HTTP 下载双通道
- **Obsidian 优化**：自动 frontmatter、共享 ssets/ 目录、Callout 支持
- **虚拟滚动适配**：滚动采集 + data-block-id 去重，解决飞书虚拟 DOM 回收问题
- **批量处理**：支持文件批量转换
- **零配置公开模式**：只要页面公开可见，不需要任何凭证

## 快速开始

`ash
pip install -e .
`

### 公开模式（推荐，无需配置）

`ash
# 单文档 -> 自动存入 Obsidian Vault
python feishu_to_md.py --url "https://xxx.feishu.cn/wiki/xxxx" --mode public

# 指定输出目录
python feishu_to_md.py --url "<URL>" --mode public --output-dir ./out

# 批量转换
python feishu_to_md.py --urls-file urls.txt --mode public
`

### API 模式（需要飞书应用凭证）

创建 .env 文件：

`env
FEISHU_APP_ID=cli_xxxx
FEISHU_APP_SECRET=xxxx
FEISHU_COOKIES="session=xxxx; bv_csrf_token=xxxx"
`

`ash
# 转换并下载图片
python feishu_to_md.py --url "<URL>" --fix-images

# 从 Chrome 自动提取 cookies
python feishu_to_md.py --refresh-cookies
`

## 输出结构

### 公开模式（Obsidian Vault 布局）

`
Obsidian Vault/
  文档标题.md                    # 正文 + frontmatter
  assets/                       # 共享图片目录（文档名前缀避免冲突）
    文档标题_001.png
    文档标题_002.png
  manifests/                    # 转换清单
    文档标题.json
`

### API 模式

`
output/
  文档标题.md
  _assets/
    img_xxx.png
`

## 命令参考

`ash
python feishu_to_md.py --url "<URL>" --mode public              # 公开模式 -> Obsidian Vault
python feishu_to_md.py --url "<URL>" --mode public --output-dir ./out  # 指定输出目录
python feishu_to_md.py --url "<URL>" --mode public --skip-images # 不下载图片
python feishu_to_md.py --url "<URL>" --fix-images                # API 模式
python feishu_to_md.py --urls-file urls.txt --mode public        # 批量公开模式
python feishu_to_md.py --refresh-cookies                         # 提取 Chrome cookies
python feishu_to_md.py --url "<URL>" --log-level DEBUG           # 详细日志
`

## 技术实现（v7.0）

- Playwright 无头浏览器渲染飞书页面
- 滚动触发虚拟 DOM 加载，逐帧扫描 data-block-id 去重
- Canvas drawImage 实时截取 blob 图片，避免虚拟滚动回收后丢失
- 飞书专用 DOM 选择器：.zone-container.editor-kit-container、.docx-*-block
- 零宽空格（\u200b）自动清理

## 开发

`ash
pip install -e ".[dev]"
python -m pytest tests/ -v
`

## 许可证

MIT
