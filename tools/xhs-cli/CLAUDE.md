# XHS 小红书排版工具（CLI 版）

## 概述

本目录包含两个 Node.js 命令行工具，用于将 Markdown 内容生成小红书风格的卡片图片。
工具位于 `social-media/tools/xhs-cli/`。

| 工具 | 画布尺寸 | 输出格式 | 风格 |
|------|----------|----------|------|
| `xhs-gen.js` (v1) | 892×1242px | JPEG | 纸质纹理背景、棕色标题 |
| `xhs-gen-v2.js` (v2) | 1080×1440px | JPEG | 深色渐变封面、金色装饰 |

## 快速使用

```bash
# 1. 写一个 Markdown 文件
cat > /tmp/xhs-content.md << 'EOF'
# 文章主标题

## 第一个小标题

**这是一行强调文本（整行高亮）**

这是正文段落。支持行内 **强调词** 高亮（金色背景+下划线）。

---

## 第二个小标题

更多正文内容...
EOF

# 2. 生成图片（v1）
node social-media/tools/xhs-cli/xhs-gen.js \
  -i /tmp/xhs-content.md \
  -o /tmp/xhs-output/

# 或使用 v2
node social-media/tools/xhs-cli/xhs-gen-v2.js \
  -i /tmp/xhs-content.md \
  -o /tmp/xhs-output/

# 3. 图片会输出到指定目录
# /tmp/xhs-output/page-1.jpg (封面)
# /tmp/xhs-output/page-2.jpg (内容页)
# ...
```

## CLI 参数

两个版本共享相同的 CLI 参数：

| 参数 | 简写 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `--input` | `-i` | 是* | — | Markdown 文件路径（或用 stdin） |
| `--output` | `-o` | 否 | `./output` | 输出目录（自动创建） |
| `--cover` | — | 否 | 内置封面图 | 封面图片路径（本地文件） |
| `--author-name` | — | 否 | `月见-关系小精灵` | 作者显示名 |
| `--author-bio` | — | 否 | 见下方说明 | 作者简介 |
| `--author-avatar` | — | 否 | 内置头像 | 头像图片路径（本地文件） |
| `--category-left` | — | 否 | 见下方说明 | 页头/页脚左侧文字 |
| `--category-slogan` | — | 否 | 见下方说明 | 页头/页脚右侧标语 |
| `--title` | — | 否 | 取 Markdown 中的 `# 标题` | 覆盖标题 |

### 默认值差异

| 参数 | v1 默认值 | v2 默认值 |
|------|-----------|-----------|
| `--author-bio` | `关系真相、星宿、合盘` | `关系真相 · 星宿 · 合盘` |
| `--category-left` | `月见 APP` | `月见APP` |
| `--category-slogan` | `关系分析、成长助手` | `关系分析、缘分助手` |

> **提示**：建议通过人设配置文件 `personas/<account>/xhs-cli.json` 传入参数，保持统一。

## Markdown 格式

```markdown
# 主标题          → 提取为封面大标题（仅第一个 # 生效）
## 小标题          → 棕色/深色粗体小标题，前后有额外间距
**整行强调**       → 整行会有高亮背景 + 下划线
普通段落           → 正文，支持行内 **强调** 高亮
---               → 分隔线
```

### 格式规则
- `# 标题`：必须放在内容开头，会被提取到封面，不会出现在正文中
- `## 小标题`：`##` 后必须有空格
- `**强调**`：整行只有 `**...**` 时渲染为独立高亮块；混在段落中时渲染为行内高亮
- `---`：三个或以上连字符，渲染为细分隔线
- 空行产生额外的呼吸间距

## 输出说明

- 输出格式为 **JPEG**（v1 quality 85，v2 quality 90）
- 第一张为封面页（含封面图、标题、作者信息）
- 从第二张起为内容页（含页头/页脚、正文）
- 自动分页，内容流式排入直到页面填满
- 封面/头像加载失败时自动降级（渐变背景/占位圆），不会中断生成

## 资源文件

| 文件 | 说明 |
|------|------|
| `assets/default-cover.png` | 默认封面图 |
| `assets/default-avatar.png` | 默认作者头像（圆形裁剪） |
| `assets/texture-bg.png` | 纸质纹理背景（v1 使用，半透明叠加） |
| `fonts/SourceHanSerifCN-Regular.otf` | 思源宋体 Regular |
| `fonts/SourceHanSerifCN-Bold.otf` | 思源宋体 Bold |

更换资源时直接替换对应文件即可。

## 注意事项

- **Emoji 支持**：macOS 上已注册 Apple Color Emoji 字体，可以正常渲染 emoji（如 🌙 🪐）。非 macOS 系统需确保有 emoji 字体。
- 封面图建议尺寸与画布宽度一致
- 如需更换头像/封面，传入本地文件路径即可

## Stdin 模式

```bash
echo "# 标题\n正文内容" | node social-media/tools/xhs-cli/xhs-gen.js -o /tmp/output/
```

## 示例：完整调用

```bash
node social-media/tools/xhs-cli/xhs-gen.js \
  -i /tmp/article.md \
  -o /tmp/xhs-cards/ \
  --author-name "我的账号" \
  --author-bio "个人简介" \
  --cover /tmp/my-cover.jpg
```
