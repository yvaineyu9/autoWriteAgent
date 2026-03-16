# XHS 小红书排版工具（CLI 版）

## 概述

这是一个 Node.js 命令行工具，用于将 Markdown 内容生成小红书风格的卡片图片（1080×1802px PNG）。
工具位于 `social-media/tools/xhs-cli/`。

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

# 2. 生成图片
node social-media/tools/xhs-cli/xhs-gen.js \
  -i /tmp/xhs-content.md \
  -o /tmp/xhs-output/

# 3. 图片会输出到指定目录
# /tmp/xhs-output/page-1.png (封面)
# /tmp/xhs-output/page-2.png (内容页)
# ...
```

## CLI 参数

| 参数 | 简写 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `--input` | `-i` | 是* | — | Markdown 文件路径（或用 stdin） |
| `--output` | `-o` | 否 | `./output` | 输出目录（自动创建） |
| `--cover` | — | 否 | 内置封面图 | 封面图片路径（本地文件） |
| `--author-name` | — | 否 | `月见-关系小精灵` | 作者显示名 |
| `--author-bio` | — | 否 | `星宿关系、合盘、马盘` | 作者简介 |
| `--author-avatar` | — | 否 | 内置头像 | 头像图片路径（本地文件） |
| `--category` | — | 否 | `月见APP  缘分、关系、恋爱神器` | 内容页顶部标签 |
| `--title` | — | 否 | 取 Markdown 中的 `# 标题` | 覆盖标题 |

## Markdown 格式

```markdown
# 主标题          → 提取为封面大标题（仅第一个 # 生效）
## 小标题          → 棕色粗体 48px，前后有额外间距
**整行强调**       → 整行会有 金色背景 + 棕色下划线
普通段落           → 正文 40px，支持行内 **强调** 高亮
---               → 分隔线
```

### 格式规则
- `# 标题`：必须放在内容开头，会被提取到封面，不会出现在正文中
- `## 小标题`：`##` 后必须有空格
- `**强调**`：整行只有 `**...**` 时渲染为独立高亮块；混在段落中时渲染为行内高亮
- `---`：三个或以上连字符，渲染为细分隔线
- 空行会被忽略

## 输出说明

- 每张图片 **1080×1802 像素**（小红书标准竖版比例）
- 第一张为封面页（含封面图、标题、作者信息、正文开头）
- 从第二张起为内容页（含页头标签、正文、页脚页码）
- 自动分页，内容流式排入直到页面填满
- 封面/头像加载失败时自动降级（渐变背景/占位圆），不会中断生成

## 资源文件

| 文件 | 说明 |
|------|------|
| `assets/default-cover.png` | 默认封面图（1080×580 推荐） |
| `assets/default-avatar.png` | 默认作者头像（圆形裁剪） |
| `assets/texture-bg.png` | 纸质纹理背景（半透明叠加） |
| `fonts/SourceHanSerifCN-Regular.otf` | 思源宋体 Regular |
| `fonts/SourceHanSerifCN-Bold.otf` | 思源宋体 Bold |

更换资源时直接替换对应文件即可。

## 注意事项

- **Emoji 支持**：macOS 上已注册 Apple Color Emoji 字体，可以正常渲染 emoji（如 🌙 🪐）。非 macOS 系统需确保有 emoji 字体。
- 封面图建议尺寸 1080×580 或等比例
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
