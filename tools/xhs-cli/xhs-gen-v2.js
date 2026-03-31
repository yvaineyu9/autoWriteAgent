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
    authorName: '月见-关系神助攻',
    authorBio: '关系真相、星座相处、星宿、合盘',
    authorAvatar: null,
    categoryLeft: '月见APP',
    categorySlogan: '关系分析、缘分助手',
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
      case '--category-left': opts.categoryLeft = args[++i]; break;
      case '--category-slogan': opts.categorySlogan = args[++i]; break;
      case '--title': opts.title = args[++i]; break;
      case '-h': case '--help':
        console.log(`xhs-gen-v2: 小红书卡片生成器（视觉升级版）\n用法: node xhs-gen-v2.js -i <markdown> [-o <输出目录>] [选项]`);
        process.exit(0);
    }
  }
  return opts;
}

// ─── 资源路径 ───
const ROOT = path.join(__dirname);
const ASSETS = path.join(ROOT, 'assets');
const FONTS = path.join(ROOT, 'fonts');
const DEFAULT_COVER = path.join(ASSETS, 'default-cover-v2.png');
const DEFAULT_AVATAR = path.join(ASSETS, 'default-avatar.png');

// ─── 注册字体 ───
GlobalFonts.registerFromPath(path.join(FONTS, 'SourceHanSerifCN-Regular.otf'), 'Source Han Serif CN');
GlobalFonts.registerFromPath(path.join(FONTS, 'SourceHanSerifCN-Bold.otf'), 'Source Han Serif CN');
const EMOJI_FONT = '/System/Library/Fonts/Apple Color Emoji.ttc';
if (fs.existsSync(EMOJI_FONT)) GlobalFonts.registerFromPath(EMOJI_FONT, 'Apple Color Emoji');

// ─── 设计系统 ───
const W = 1080, H = 1440;

const C = {
  gradStart: '#141432', gradMid: '#3d2560', gradEnd: '#6b4a7a',
  pageBg: '#FAF6EF',
  text: '#3D2B1F', h2: '#4A3228',
  accent: '#C9A96E', accentBg: 'rgba(201,169,110,0.12)',
  muted: 'rgba(61,43,31,0.30)', sep: 'rgba(61,43,31,0.10)',
  white: '#FFF', whiteSub: 'rgba(255,255,255,0.70)', whiteMain: 'rgba(255,255,255,0.90)',
};

const F = {
  body:      '36px "Source Han Serif CN","Apple Color Emoji",serif',
  bodyBold:  'bold 36px "Source Han Serif CN","Apple Color Emoji",serif',
  h2:        'bold 40px "Source Han Serif CN","Apple Color Emoji",serif',
  coverT:    'bold 96px "Source Han Serif CN","Apple Color Emoji",serif',
  coverAuth: 'bold 32px "Source Han Serif CN",serif',
  coverBio:  '26px "Source Han Serif CN",serif',
  small:     '26px "Source Han Serif CN",serif',
  quote:     '38px "Source Han Serif CN","Apple Color Emoji",serif',
};

const L = {
  ml: 78, mr: W - 78, mw: W - 156,
  lh: 58, gap: 46, h2gap: 76,
  footY: 1365, headY: 60, bodyY: 120,
};

// ─── Markdown 解析 ───
function parseContent(text) {
  const fm = text.match(/^---\s*\n[\s\S]*?\n---\s*\n/);
  if (fm) text = text.slice(fm[0].length);
  const lines = text.split('\n');
  const blocks = [];
  let started = false;
  for (const line of lines) {
    const t = line.trim();
    if (!t) { if (started && blocks.length && blocks[blocks.length-1].type !== 'spacer') blocks.push({type:'spacer'}); continue; }
    started = true;
    if (/^---\s*简介\s*---\s*$/.test(t)) break;
    if (/^#\S+(\s+#\S+)*\s*$/.test(t)) continue;
    if (/^---+$/.test(t)) blocks.push({type:'separator'});
    else if (/^##\s+/.test(t)) { if (blocks.length && blocks[blocks.length-1].type==='spacer') blocks.pop(); blocks.push({type:'h2',content:t.replace(/^##\s+/,'')}); }
    else if (/^#\s+/.test(t)) blocks.push({type:'h1',content:t.replace(/^#\s+/,'')});
    else if (/^\*\*[^*]+\*\*$/.test(t)) blocks.push({type:'highlight',content:t.replace(/\*\*/g,'')});
    else blocks.push({type:'paragraph',content:t});
  }
  while (blocks.length && blocks[blocks.length-1].type==='spacer') blocks.pop();
  // clean separators
  const out = [];
  for (let i=0;i<blocks.length;i++) {
    if (blocks[i].type==='separator') { if (!out.length) continue; if (i+1<blocks.length && blocks[i+1].type==='h2') continue; }
    out.push(blocks[i]);
  }
  return out;
}

// ─── 文本工具 ───
// 中文禁则：这些标点不能出现在行首
const NO_START = new Set('，。、！？；：）】》」』”’…—～·,.!?;:)]}\'\'"');

function wrap(ctx, text, x, y, mw, lh) {
  const chars = Array.from(text);
  let line='', cy=y;
  for (let i=0; i<chars.length; i++) {
    const ch = chars[i];
    const next = chars[i+1];
    const shouldBreak = ctx.measureText(line+ch).width > mw && line && !(next && NO_START.has(next));
    if (shouldBreak) { ctx.fillText(line,x,cy); line=ch; cy+=lh; } else line+=ch;
  }
  ctx.fillText(line,x,cy);
  return cy;
}

function wrapCenter(ctx, text, cx, y, mw, lh) {
  const chars = Array.from(text);
  let line='', lines=[];
  for (let i=0; i<chars.length; i++) {
    const ch = chars[i];
    const next = chars[i+1];
    const shouldBreak = ctx.measureText(line+ch).width > mw && line && !(next && NO_START.has(next));
    if (shouldBreak) { lines.push(line); line=ch; } else line+=ch;
  }
  lines.push(line);
  let cy=y;
  for (const l of lines) { ctx.fillText(l, cx - ctx.measureText(l).width/2, cy); cy+=lh; }
  return cy-lh;
}

function countLines(ctx, text, mw) {
  let line='', n=1;
  for (const ch of text) { if (ctx.measureText(line+ch).width > mw && line) { n++; line=ch; } else line+=ch; }
  return n;
}

function wrapRich(ctx, text, x, y, mw, lh) {
  const parts = text.split(/(\*\*[^*]+\*\*)/);
  const segs = [];
  for (const p of parts) {
    if (p.startsWith('**')&&p.endsWith('**')) segs.push({t:p.slice(2,-2),b:true});
    else if (p) segs.push({t:p,b:false});
  }
  let cx=x, cy=y;
  const chars=[], bolds=[];
  ctx.font=F.body;
  for (const s of segs) {
    let sx = s.b ? cx : -1;
    for (const ch of s.t) {
      const w=ctx.measureText(ch).width;
      if (cx+w>x+mw && cx>x) { if(s.b&&sx>=0) bolds.push({sx,ex:cx,y:cy}); cy+=lh; cx=x; if(s.b) sx=x; }
      chars.push({ch,x:cx,y:cy,b:s.b}); cx+=w;
    }
    if (s.b&&sx>=0) bolds.push({sx,ex:cx,y:cy});
  }
  for (const r of bolds) { ctx.fillStyle=C.accentBg; ctx.fillRect(r.sx-4,r.y-24,(r.ex-r.sx)+8,34); }
  ctx.fillStyle=C.text; ctx.font=F.body;
  for (const c of chars) { if(c.b) ctx.font=F.bodyBold; else ctx.font=F.body; ctx.fillText(c.ch,c.x,c.y); }
  ctx.font=F.body;
  return cy;
}

// ─── 渲染内容块 ───
function renderBlocks(ctx, blocks, startY, maxY) {
  let y=startY, eaten=0;
  ctx.textBaseline='alphabetic'; ctx.letterSpacing='1px';

  for (let i=0; i<blocks.length; i++) {
    const b=blocks[i];
    let predY;
    if (b.type==='spacer') predY=y+L.gap;
    else if (b.type==='separator') predY=y+36;
    else if (b.type==='highlight') { ctx.font=F.quote; predY=y+16+countLines(ctx,b.content,L.mw-40)*L.lh+16; }
    else { ctx.font=b.type==='h2'?F.h2:F.body; predY=y+(countLines(ctx,b.content,L.mw)-1)*L.lh; if(b.type==='h2'&&eaten>0) predY+=L.h2gap; }

    if (predY>maxY && eaten>0) break;
    if ((b.type==='h2'||b.type==='separator')&&eaten>0&&i<blocks.length-1) { if(predY+L.gap+L.lh>maxY) break; }

    switch(b.type) {
      case 'h2':
        if (eaten>0) y+=L.h2gap;
        ctx.fillStyle=C.accent; ctx.fillRect(L.ml,y-26,3,36);
        ctx.fillStyle=C.h2; ctx.font=F.h2;
        y=wrap(ctx,b.content,L.ml+18,y,L.mw-18,L.lh)+L.h2gap;
        break;
      case 'highlight':
        ctx.font=F.quote;
        const ql=countLines(ctx,b.content,L.mw-40), qh=ql*L.lh+6;
        ctx.fillStyle=C.accentBg; ctx.fillRect(L.ml,y-22,L.mw,qh);
        ctx.fillStyle=C.accent; ctx.fillRect(L.ml,y-22,4,qh);
        ctx.fillStyle=C.text;
        const qe=wrap(ctx,b.content,L.ml+24,y+16,L.mw-40,L.lh);
        y=qe+L.gap+42;
        break;
      case 'paragraph':
        ctx.fillStyle=C.text;
        y=wrapRich(ctx,b.content,L.ml,y,L.mw,L.lh)+L.gap;
        break;
      case 'spacer': y+=L.gap; break;
      case 'separator':
        y+=4; ctx.strokeStyle=C.sep; ctx.lineWidth=1;
        ctx.beginPath(); ctx.moveTo(L.ml,y); ctx.lineTo(L.mr,y); ctx.stroke();
        y+=32; break;
    }
    eaten++;
  }
  return eaten;
}

// ─── 页眉页脚 ───
function drawHeader(ctx, opts, pi, total) {
  const y = L.headY;
  ctx.letterSpacing='0px'; ctx.textBaseline='alphabetic';
  // 品牌名（左）— 更醒目
  ctx.fillStyle='rgba(61,43,31,0.50)'; ctx.font='28px "Source Han Serif CN",serif';
  ctx.textAlign='left'; ctx.fillText(opts.categoryLeft, L.ml, y);
  // 标语（右）
  ctx.textAlign='right'; ctx.fillText(opts.categorySlogan, L.mr, y);
  ctx.textAlign='left';
  // 分隔线
  ctx.strokeStyle='rgba(61,43,31,0.20)'; ctx.lineWidth=1.5;
  ctx.beginPath(); ctx.moveTo(L.ml,y+12); ctx.lineTo(L.mr,y+12); ctx.stroke();
}

function drawFooter(ctx, opts, pi, total, title) {
  const y = L.footY;
  ctx.strokeStyle='rgba(61,43,31,0.15)'; ctx.lineWidth=1.5;
  ctx.beginPath(); ctx.moveTo(L.ml,y); ctx.lineTo(L.mr,y); ctx.stroke();
  ctx.letterSpacing='0px'; ctx.textBaseline='alphabetic';
  ctx.fillStyle='rgba(61,43,31,0.50)'; ctx.font='28px "Source Han Serif CN",serif';
  // 文章标题（左）
  ctx.textAlign='left';
  let footTitle = title || '';
  while (ctx.measureText(footTitle).width > L.mw - 120 && footTitle.length > 1) footTitle = footTitle.slice(0,-1);
  if (footTitle !== title) footTitle += '…';
  ctx.fillText(footTitle, L.ml, y+36);
  // 页码（右）
  ctx.textAlign='right';
  ctx.fillText(`${pi+1}/${total}`, L.mr, y+36);
  ctx.textAlign='left';
}

// ─── 封面页 ───
async function drawCover(title, coverPath, avatarPath, author) {
  const canvas=createCanvas(W,H), ctx=canvas.getContext('2d');

  // 渐变背景
  const g=ctx.createLinearGradient(0,0,W*0.3,H);
  g.addColorStop(0,C.gradStart); g.addColorStop(0.5,C.gradMid); g.addColorStop(1,C.gradEnd);
  ctx.fillStyle=g; ctx.fillRect(0,0,W,H);

  // 封面图（半透明叠加）
  try {
    const img=await loadImage(coverPath);
    ctx.globalAlpha=0.5; ctx.drawImage(img,0,0,W,H); ctx.globalAlpha=1;
    const ov=ctx.createLinearGradient(0,0,0,H);
    ov.addColorStop(0,'rgba(20,20,50,0.4)'); ov.addColorStop(0.5,'rgba(20,20,50,0.15)'); ov.addColorStop(1,'rgba(20,20,50,0.55)');
    ctx.fillStyle=ov; ctx.fillRect(0,0,W,H);
  } catch {
    // 微光
    const gl=ctx.createRadialGradient(W*0.7,H*0.3,50,W*0.7,H*0.3,400);
    gl.addColorStop(0,'rgba(201,169,110,0.12)'); gl.addColorStop(1,'rgba(201,169,110,0)');
    ctx.fillStyle=gl; ctx.fillRect(0,0,W,H);
  }

  // 标题居中
  ctx.textBaseline='top'; ctx.letterSpacing='6px';
  ctx.fillStyle=C.white; ctx.font=F.coverT;
  const tY=H*0.25;
  const tEnd=wrapCenter(ctx,title,W/2,tY,L.mw-20,130);

  // 装饰线（金色，居中）
  const dY=tEnd+70;
  ctx.strokeStyle=C.accent; ctx.lineWidth=1; ctx.globalAlpha=0.6;
  ctx.beginPath(); ctx.moveTo(W/2-80,dY); ctx.lineTo(W/2-15,dY); ctx.stroke();
  ctx.fillStyle=C.accent;
  ctx.beginPath(); ctx.moveTo(W/2,dY-5); ctx.lineTo(W/2+5,dY); ctx.lineTo(W/2,dY+5); ctx.lineTo(W/2-5,dY); ctx.closePath(); ctx.fill();
  ctx.beginPath(); ctx.moveTo(W/2+15,dY); ctx.lineTo(W/2+80,dY); ctx.stroke();
  ctx.globalAlpha=1;

  // 作者（底部居中）
  const aY=H-200, ar=36, as=ar*2;
  ctx.font=F.coverAuth;
  const aw=as+14+ctx.measureText(author.name).width+20;
  const ax=(W-aw)/2;
  try {
    const av=await loadImage(avatarPath);
    ctx.save(); ctx.beginPath(); ctx.arc(ax+ar,aY+ar,ar,0,Math.PI*2); ctx.clip();
    ctx.drawImage(av,ax,aY,as,as); ctx.restore();
    ctx.strokeStyle='rgba(255,255,255,0.3)'; ctx.lineWidth=1.5;
    ctx.beginPath(); ctx.arc(ax+ar,aY+ar,ar,0,Math.PI*2); ctx.stroke();
  } catch {
    ctx.fillStyle='rgba(255,255,255,0.15)';
    ctx.beginPath(); ctx.arc(ax+ar,aY+ar,ar,0,Math.PI*2); ctx.fill();
  }
  ctx.textBaseline='alphabetic'; ctx.letterSpacing='1px';
  ctx.fillStyle=C.whiteMain; ctx.font=F.coverAuth;
  ctx.fillText(author.name,ax+as+14,aY+30);
  ctx.fillStyle=C.whiteSub; ctx.font=F.coverBio; ctx.letterSpacing='0px';
  ctx.fillText(author.bio,ax+as+14,aY+68);

  return canvas;
}

// ─── 内容页 ───
function drawPage(blocks) {
  const canvas=createCanvas(W,H), ctx=canvas.getContext('2d');
  ctx.fillStyle=C.pageBg; ctx.fillRect(0,0,W,H);
  const eaten=renderBlocks(ctx,blocks,L.bodyY,L.footY-28);
  return {canvas,eaten};
}

// ─── 主流程 ───
async function main() {
  const opts=parseArgs();
  let md;
  if (opts.input) md=fs.readFileSync(opts.input,'utf-8');
  else if (!process.stdin.isTTY) md=fs.readFileSync(0,'utf-8');
  else { console.error('错误: 请指定 -i <文件>'); process.exit(1); }

  let blocks=parseContent(md);
  let title=opts.title||'未命名';
  const h1i=blocks.findIndex(b=>b.type==='h1');
  if (h1i>=0) { title=blocks[h1i].content; blocks.splice(h1i,1); }
  if (opts.title) title=opts.title;

  const coverPath=opts.cover||DEFAULT_COVER;
  const avatarPath=opts.authorAvatar||DEFAULT_AVATAR;

  fs.mkdirSync(opts.output,{recursive:true});
  const pages=[];

  // 封面
  pages.push(await drawCover(title,coverPath,avatarPath,{name:opts.authorName,bio:opts.authorBio}));

  // 内容页
  while (blocks.length) {
    const {canvas,eaten}=drawPage(blocks);
    pages.push(canvas);
    if (!eaten) { blocks.shift(); } else blocks=blocks.slice(eaten);
  }

  // 页眉页脚
  for (let i=1;i<pages.length;i++) {
    const ctx=pages[i].getContext('2d');
    drawHeader(ctx,opts,i,pages.length);
    drawFooter(ctx,opts,i,pages.length,title);
  }

  // 输出
  for (let i=0;i<pages.length;i++) {
    fs.writeFileSync(path.join(opts.output,`page-${i+1}.jpg`), pages[i].toBuffer('image/jpeg',90));
  }
  console.log(`✅ 生成完成: ${pages.length} 页 → ${opts.output}`);
  pages.forEach((_,i)=>console.log(`   page-${i+1}.jpg`));
}

main().catch(e=>{console.error('失败:',e.message);process.exit(1)});
