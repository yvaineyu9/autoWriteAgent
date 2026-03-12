#!/usr/bin/env node
'use strict';

const { createCanvas, GlobalFonts, loadImage } = require('@napi-rs/canvas');
const fs = require('fs');
const path = require('path');

// ─── CLI 参数解析 ───
function parseArgs() {
  const args = process.argv.slice(2);
  const opts = {
    input: null,
    output: './output',
    cover: null,
    authorName: '月见-关系小精灵',
    authorBio: '星宿关系、合盘、马盘',
    authorAvatar: null,
    category: '月见APP       缘分、关系、恋爱神器',
    title: null,
  };

  for (let i = 0; i < args.length; i++) {
    switch (args[i]) {
      case '-i': case '--input': opts.input = args[++i]; break;
      case '-o': case '--output': opts.output = args[++i]; break;
      case '--cover': opts.cover = args[++i]; break;
      case '--author-name': opts.authorName = args[++i]; break;
      case '--author-bio': opts.authorBio = args[++i]; break;
      case '--author-avatar': opts.authorAvatar = args[++i]; break;
      case '--category': opts.category = args[++i]; break;
      case '--title': opts.title = args[++i]; break;
      case '-h': case '--help':
        console.log(`
用法: node xhs-gen.js -i <markdown文件> [-o <输出目录>] [选项]

选项:
  -i, --input <file>        Markdown 文件路径（必填，或用 stdin）
  -o, --output <dir>        输出目录（默认 ./output）
  --cover <file>            封面图路径
  --author-name <name>      作者名（默认 "月见-关系小精灵"）
  --author-bio <bio>        作者简介（默认 "星宿关系、合盘、马盘"）
  --author-avatar <file>    头像路径
  --category <text>         页头标签
  --title <text>            覆盖 Markdown 中的 # 标题

示例:
  node xhs-gen.js -i content.md -o ./output/
  cat content.md | node xhs-gen.js -o ./output/
`);
        process.exit(0);
    }
  }
  return opts;
}

// ─── 资源路径 ───
const ROOT = __dirname;
const ASSETS = path.join(ROOT, 'assets');
const FONTS = path.join(ROOT, 'fonts');

const DEFAULT_COVER = path.join(ASSETS, 'default-cover.png');
const DEFAULT_AVATAR = path.join(ASSETS, 'default-avatar.png');
const TEXTURE_BG = path.join(ASSETS, 'texture-bg.png');

// ─── 注册字体 ───
GlobalFonts.registerFromPath(path.join(FONTS, 'SourceHanSerifCN-Regular.otf'), 'Source Han Serif CN');
GlobalFonts.registerFromPath(path.join(FONTS, 'SourceHanSerifCN-Bold.otf'), 'Source Han Serif CN');

// ─── 样式常量 ───
const BODY_FONT = '40px "Source Han Serif CN"';
const BODY_FONT_BOLD = 'bold 40px "Source Han Serif CN"';
const H2_FONT = 'bold 48px "Source Han Serif CN"';
const TEXT_COLOR = '#291100';
const H2_COLOR = '#833B00';
const LINE_HEIGHT = 72;
const BLOCK_GAP = 80;
const MAX_WIDTH = 952;
const MARGIN_LEFT = 64;
const FOOTER_Y = 1700;
const LETTER_SPACING = 3; // px

// ─── Markdown 解析 ───
function stripFrontmatter(text) {
  // Strip YAML frontmatter (--- ... ---)
  const match = text.match(/^---\s*\n([\s\S]*?)\n---\s*\n/);
  if (match) return text.slice(match[0].length);
  return text;
}

function parseContent(text) {
  text = stripFrontmatter(text);
  const lines = text.split('\n');
  const blocks = [];
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    // Skip XHS hashtag lines (e.g. "#分手 #恋爱心理学 #情感")
    if (/^#\S+(\s+#\S+)*\s*$/.test(trimmed)) continue;
    // Skip signature lines
    if (/^我是月见/.test(trimmed)) continue;
    if (/^---+$/.test(trimmed)) {
      blocks.push({ type: 'separator' });
    } else if (/^##\s+/.test(trimmed)) {
      blocks.push({ type: 'h2', content: trimmed.replace(/^##\s+/, '') });
    } else if (/^#\s+/.test(trimmed)) {
      blocks.push({ type: 'h1', content: trimmed.replace(/^#\s+/, '') });
    } else if (/^\*\*[^*]+\*\*$/.test(trimmed)) {
      blocks.push({ type: 'highlight', content: trimmed.replace(/\*\*/g, '') });
    } else {
      blocks.push({ type: 'paragraph', content: trimmed });
    }
  }
  return blocks;
}

function cleanSeparators(blocks) {
  const cleaned = [];
  for (let i = 0; i < blocks.length; i++) {
    if (blocks[i].type === 'separator') {
      if (cleaned.length === 0) continue;
      if (i + 1 < blocks.length && blocks[i + 1].type === 'h2') continue;
    }
    cleaned.push(blocks[i]);
  }
  return cleaned;
}

// ─── Canvas 文本工具 ───
// @napi-rs/canvas 不支持 ctx.letterSpacing，手动处理
function measureCharWidth(ctx, char) {
  return ctx.measureText(char).width + LETTER_SPACING;
}

// 测量整个字符串宽度（含 letter-spacing）
function measureTextWidth(ctx, text) {
  let w = 0;
  for (const char of text) w += measureCharWidth(ctx, char);
  return w;
}

function wrapText(ctx, text, x, y, maxWidth, lineHeight) {
  const chars = text.split('');
  let currentX = x;
  let currentY = y;

  for (let i = 0; i < chars.length; i++) {
    const w = measureCharWidth(ctx, chars[i]);
    if (currentX + w > x + maxWidth && currentX > x) {
      currentY += lineHeight;
      currentX = x;
    }
    ctx.fillText(chars[i], currentX, currentY);
    currentX += w;
  }
  return currentY;
}

function wrapTextRich(ctx, text, x, y, maxWidth, lineHeight) {
  const parts = text.split(/(\*\*[^*]+\*\*)/);
  const segments = [];
  for (const part of parts) {
    if (part.startsWith('**') && part.endsWith('**')) {
      segments.push({ text: part.slice(2, -2), bold: true });
    } else if (part) {
      segments.push({ text: part, bold: false });
    }
  }

  // 第一遍：测量，收集字符坐标和加粗区间
  let currentX = x, currentY = y;
  const charPositions = [];
  const boldRanges = [];
  ctx.font = BODY_FONT;

  for (const seg of segments) {
    let segStartX = seg.bold ? currentX : -1;
    for (const char of seg.text) {
      const w = measureCharWidth(ctx, char);
      if (currentX + w > x + maxWidth && currentX > x) {
        if (seg.bold && segStartX >= 0) {
          boldRanges.push({ startX: segStartX, endX: currentX, y: currentY });
        }
        currentY += lineHeight;
        currentX = x;
        if (seg.bold) segStartX = x;
      }
      charPositions.push({ char, x: currentX, y: currentY });
      currentX += w;
    }
    if (seg.bold && segStartX >= 0) {
      boldRanges.push({ startX: segStartX, endX: currentX, y: currentY });
    }
  }

  // 第二遍：画高亮背景 + 下划线
  const hlP = 6;
  for (const r of boldRanges) {
    ctx.fillStyle = 'rgba(245, 222, 170, 0.45)';
    ctx.fillRect(r.startX - hlP, r.y - 36, (r.endX - r.startX) + hlP * 2, 50);
    ctx.strokeStyle = '#A0522D';
    ctx.lineWidth = 3;
    ctx.beginPath();
    ctx.moveTo(r.startX - hlP, r.y + 10);
    ctx.lineTo(r.endX + hlP, r.y + 10);
    ctx.stroke();
  }

  // 第三遍：画文字
  ctx.fillStyle = TEXT_COLOR;
  ctx.font = BODY_FONT;
  for (const cp of charPositions) {
    ctx.fillText(cp.char, cp.x, cp.y);
  }

  return currentY;
}

// ─── 渲染逻辑 ───
function renderBlocksUntilFull(ctx, blocks, startY, maxY) {
  let y = startY;
  ctx.textBaseline = 'alphabetic';
  let consumed = 0;

  for (let i = 0; i < blocks.length; i++) {
    const block = blocks[i];

    // 预测高度
    let predictedEndY;
    if (block.type === 'separator') {
      predictedEndY = y + 60;
    } else {
      let font;
      switch (block.type) {
        case 'h2': font = H2_FONT; break;
        case 'highlight': font = BODY_FONT; break;
        default: font = BODY_FONT; break;
      }
      ctx.font = font;

      let predictLines = 1, lineW = 0;
      if (block.type === 'paragraph') {
        const parts = block.content.split(/(\*\*[^*]+\*\*)/);
        for (const part of parts) {
          const isBold = part.startsWith('**') && part.endsWith('**');
          const txt = isBold ? part.slice(2, -2) : part;
          ctx.font = isBold ? BODY_FONT : BODY_FONT;
          for (const char of txt) {
            const w = measureCharWidth(ctx, char);
            if (lineW + w > MAX_WIDTH && lineW > 0) { predictLines++; lineW = 0; }
            lineW += w;
          }
        }
      } else {
        for (const char of block.content) {
          const w = measureCharWidth(ctx, char);
          if (lineW + w > MAX_WIDTH && lineW > 0) { predictLines++; lineW = 0; }
          lineW += w;
        }
      }
      predictedEndY = y + (predictLines - 1) * LINE_HEIGHT;
      if (block.type === 'h2' && consumed > 0) predictedEndY += BLOCK_GAP;
    }

    if (predictedEndY > maxY && consumed > 0) break;

    // 防孤标题
    if ((block.type === 'h2' || block.type === 'separator') && consumed > 0 && i < blocks.length - 1) {
      const nextPredictedEnd = predictedEndY + BLOCK_GAP + LINE_HEIGHT;
      if (nextPredictedEnd > maxY) break;
    }

    // 渲染
    switch (block.type) {
      case 'h2':
        if (consumed > 0) y += BLOCK_GAP;
        ctx.fillStyle = H2_COLOR;
        ctx.font = H2_FONT;
        y = wrapText(ctx, block.content, MARGIN_LEFT, y, MAX_WIDTH, LINE_HEIGHT) + BLOCK_GAP;
        break;

      case 'highlight':
        ctx.font = BODY_FONT;
        const hlW = Math.min(measureTextWidth(ctx, block.content), MAX_WIDTH);
        const hlP = 10;
        ctx.fillStyle = 'rgba(245, 222, 170, 0.45)';
        ctx.fillRect(MARGIN_LEFT - hlP, y - 36, hlW + hlP * 2, 50);
        ctx.fillStyle = TEXT_COLOR;
        const hlEnd = wrapText(ctx, block.content, MARGIN_LEFT, y, MAX_WIDTH, LINE_HEIGHT);
        ctx.strokeStyle = '#A0522D';
        ctx.lineWidth = 3;
        ctx.beginPath();
        ctx.moveTo(MARGIN_LEFT - hlP, y + 10);
        ctx.lineTo(MARGIN_LEFT + hlW + hlP, y + 10);
        ctx.stroke();
        y = hlEnd + BLOCK_GAP;
        break;

      case 'paragraph':
        ctx.fillStyle = TEXT_COLOR;
        y = wrapTextRich(ctx, block.content, MARGIN_LEFT, y, MAX_WIDTH, LINE_HEIGHT) + BLOCK_GAP;
        break;

      case 'separator':
        y += 10;
        ctx.strokeStyle = 'rgba(41, 17, 0, 0.15)';
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(MARGIN_LEFT, y);
        ctx.lineTo(MARGIN_LEFT + MAX_WIDTH, y);
        ctx.stroke();
        y += 50;
        break;
    }
    consumed++;
  }
  return consumed;
}

// ─── 页脚 ───
function drawFooter(ctx, title, pageIndex, totalPages) {
  ctx.strokeStyle = 'rgba(41, 17, 0, 0.1)';
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(MARGIN_LEFT, FOOTER_Y);
  ctx.lineTo(1016, FOOTER_Y);
  ctx.stroke();

  ctx.textBaseline = 'alphabetic';
  ctx.fillStyle = 'rgba(41, 17, 0, 0.3)';
  ctx.font = '32px "Source Han Serif CN"';
  const shortTitle = title.length > 20 ? title.substring(0, 20) + '...' : title;
  ctx.fillText(shortTitle, MARGIN_LEFT, FOOTER_Y + 52);

  ctx.font = '24px "Source Han Serif CN"';
  ctx.fillText(`${pageIndex + 1}/${totalPages}`, MAX_WIDTH, FOOTER_Y + 56);
}

// ─── 页面绘制 ───
async function drawCoverPage(mainTitle, blocks, coverPath, avatarPath, authorInfo, textureImg) {
  const canvas = createCanvas(1080, 1802);
  const ctx = canvas.getContext('2d');

  ctx.fillStyle = '#FDF9F0';
  ctx.fillRect(0, 0, 1080, 1802);

  // 封面图
  try {
    const coverImg = await loadImage(coverPath);
    ctx.drawImage(coverImg, 0, 0, 1080, 580);
  } catch (e) {
    // 封面加载失败时填充渐变
    console.warn('封面图加载失败，使用默认渐变:', e.message);
    const grad = ctx.createLinearGradient(0, 0, 1080, 580);
    grad.addColorStop(0, '#2a1b3d');
    grad.addColorStop(1, '#44318d');
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, 1080, 580);
  }

  // 圆角卡片
  const cardY = 530;
  ctx.fillStyle = '#FDF9F0';
  ctx.beginPath();
  ctx.roundRect(0, cardY, 1080, 1802 - cardY, [57, 57, 0, 0]);
  ctx.fill();

  // 纹理
  if (textureImg) {
    ctx.save();
    ctx.globalAlpha = 0.5;
    ctx.beginPath();
    ctx.roundRect(0, cardY, 1080, 1802 - cardY, [57, 57, 0, 0]);
    ctx.clip();
    ctx.drawImage(textureImg, 0, cardY, 1080, 1802 - cardY);
    ctx.restore();
  }

  // 标题
  ctx.fillStyle = '#833B00';
  ctx.font = 'bold 82px "Source Han Serif CN"';
  ctx.textBaseline = 'top';
  const titleEndY = wrapText(ctx, mainTitle, MARGIN_LEFT, 600, MAX_WIDTH, 120);

  // 头像
  const authorY = titleEndY + 120 + 32;
  try {
    const avatarImg = await loadImage(avatarPath);
    ctx.save();
    ctx.beginPath();
    ctx.arc(MARGIN_LEFT + 74, authorY + 74, 74, 0, Math.PI * 2);
    ctx.clip();
    ctx.drawImage(avatarImg, MARGIN_LEFT, authorY, 148, 148);
    ctx.restore();
  } catch (e) {
    // 头像加载失败，画占位圆
    console.warn('头像加载失败，使用占位圆:', e.message);
    ctx.fillStyle = '#ddd';
    ctx.beginPath();
    ctx.arc(MARGIN_LEFT + 74, authorY + 74, 74, 0, Math.PI * 2);
    ctx.fill();
  }

  // 作者名
  ctx.textBaseline = 'alphabetic';
  ctx.fillStyle = '#291100';
  ctx.font = 'bold 40px "Source Han Serif CN"';
  ctx.fillText(authorInfo.name, MARGIN_LEFT + 148 + 24, authorY + 70);

  // 作者简介
  ctx.fillStyle = 'rgba(41, 17, 0, 0.5)';
  ctx.font = '32px "Source Han Serif CN"';
  ctx.fillText(authorInfo.bio, MARGIN_LEFT + 148 + 24, authorY + 120);

  // 正文
  const bodyStartY = authorY + 148 + 96;
  const consumed = renderBlocksUntilFull(ctx, blocks, bodyStartY, FOOTER_Y - 48);

  return { canvas, consumed };
}

async function drawContentPage(mainTitle, blocks, categoryTag, textureImg) {
  const canvas = createCanvas(1080, 1802);
  const ctx = canvas.getContext('2d');

  ctx.fillStyle = '#FDF9F0';
  ctx.fillRect(0, 0, 1080, 1802);

  // 纹理
  if (textureImg) {
    ctx.save();
    ctx.globalAlpha = 0.5;
    ctx.drawImage(textureImg, 0, 0, 1080, 1802);
    ctx.restore();
  }

  // 分类标签
  let y = 82;
  ctx.fillStyle = 'rgba(41, 17, 0, 0.3)';
  ctx.font = '32px "Source Han Serif CN"';
  ctx.fillText(categoryTag, MARGIN_LEFT, y);
  const dividerY = y + 8 + 12;

  ctx.strokeStyle = 'rgba(41, 17, 0, 0.2)';
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(MARGIN_LEFT, dividerY);
  ctx.lineTo(1016, dividerY);
  ctx.stroke();
  y = dividerY + 36 + 32;

  // 渲染内容块
  const consumed = renderBlocksUntilFull(ctx, blocks, y, FOOTER_Y - 44);

  return { canvas, consumed };
}

// ─── 主流程 ───
async function main() {
  const opts = parseArgs();

  // 读取 Markdown
  let markdown;
  if (opts.input) {
    markdown = fs.readFileSync(opts.input, 'utf-8');
  } else if (!process.stdin.isTTY) {
    markdown = fs.readFileSync(0, 'utf-8'); // stdin
  } else {
    console.error('错误: 请指定 -i <文件> 或通过 stdin 输入');
    process.exit(1);
  }

  // 解析
  let blocks = parseContent(markdown);
  let mainTitle = opts.title || '未命名文章';
  const h1Index = blocks.findIndex(b => b.type === 'h1');
  if (h1Index >= 0) {
    mainTitle = blocks[h1Index].content;
    blocks.splice(h1Index, 1);
  }
  if (opts.title) mainTitle = opts.title;
  blocks = cleanSeparators(blocks);

  // 资源
  const coverPath = opts.cover || DEFAULT_COVER;
  const avatarPath = opts.authorAvatar || DEFAULT_AVATAR;
  const authorInfo = { name: opts.authorName, bio: opts.authorBio };

  let textureImg = null;
  try { textureImg = await loadImage(TEXTURE_BG); } catch { }

  // 创建输出目录
  fs.mkdirSync(opts.output, { recursive: true });

  const canvases = [];

  // 1. 封面页
  const cover = await drawCoverPage(mainTitle, blocks, coverPath, avatarPath, authorInfo, textureImg);
  canvases.push(cover.canvas);
  blocks = blocks.slice(cover.consumed);

  // 2. 内容页
  while (blocks.length > 0) {
    const page = await drawContentPage(mainTitle, blocks, opts.category, textureImg);
    canvases.push(page.canvas);
    blocks = blocks.slice(page.consumed);
  }

  // 3. 给内容页加页脚
  const totalPages = canvases.length;
  for (let i = 1; i < totalPages; i++) {
    drawFooter(canvases[i].getContext('2d'), mainTitle, i, totalPages);
  }

  // 4. 输出 PNG
  for (let i = 0; i < canvases.length; i++) {
    const outFile = path.join(opts.output, `page-${i + 1}.png`);
    const buf = canvases[i].toBuffer('image/png');
    fs.writeFileSync(outFile, buf);
  }

  console.log(`✅ 生成完成: ${totalPages} 页 → ${opts.output}`);
  for (let i = 0; i < totalPages; i++) {
    console.log(`   page-${i + 1}.png`);
  }
}

main().catch(err => {
  console.error('生成失败:', err.message);
  process.exit(1);
});
