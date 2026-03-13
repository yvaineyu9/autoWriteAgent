#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
小红书上传助手 - 自动填充内容到创作者后台，等待手动发布

功能：
1. 解析 Markdown 文件（frontmatter + 正文 + 简介 + 标签）
2. 用 Playwright 打开小红书创作者中心发布页
3. 上传图片、填写标题、正文、标签
4. 停住，等待用户手动点击发布

使用：
    python xiaohongshu_uploader.py <markdown文件> <图片目录>
    python xiaohongshu_uploader.py <markdown文件> <图片目录> --login  # 首次登录

示例：
    python xiaohongshu_uploader.py \
        ~/claude-workflows/60_Published/social-media/yuejian/2026-03-12_xxx_小红书.md \
        ~/claude-workflows/60_Published/social-media/output/article1/
"""

import asyncio
import json
import os
import re
import sys
import glob
import argparse
import random
from pathlib import Path
from typing import Optional, Dict, List, Tuple

# 配置路径
BASE_DIR = Path.home() / "claude-workflows"
SECRETS_DIR = BASE_DIR / ".secrets"
COOKIES_FILE = SECRETS_DIR / "xiaohongshu_cookies.json"

# 小红书创作者中心发布页
PUBLISH_URL = "https://creator.xiaohongshu.com/publish/publish"
LOGIN_URL = "https://creator.xiaohongshu.com"

# 确保目录存在
SECRETS_DIR.mkdir(parents=True, exist_ok=True)


# ─── Cookie 管理（复用 crawler 逻辑）───

def load_cookies() -> Optional[list]:
    """加载保存的 cookies"""
    if COOKIES_FILE.exists():
        try:
            with open(COOKIES_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️ 加载 cookies 失败: {e}")
    return None


def save_cookies(cookies: list):
    """保存 cookies"""
    try:
        with open(COOKIES_FILE, 'w', encoding='utf-8') as f:
            json.dump(cookies, f, ensure_ascii=False, indent=2)
        print(f"✅ Cookies 已保存")
    except Exception as e:
        print(f"❌ 保存 cookies 失败: {e}")


# ─── Markdown 解析 ───

def parse_markdown(file_path: Path) -> Dict:
    """解析小红书 Markdown 文件，提取标题、正文、简介、标签"""
    content = file_path.read_text(encoding='utf-8')

    # 解析 frontmatter
    frontmatter = {}
    body = content
    if content.startswith('---'):
        parts = content.split('---', 2)
        if len(parts) >= 3:
            fm_text = parts[1].strip()
            # 简单 YAML 解析
            for line in fm_text.split('\n'):
                if ':' in line:
                    key, _, value = line.partition(':')
                    frontmatter[key.strip()] = value.strip()
            body = parts[2].strip()

    # 提取标题（第一个 # 标题）
    title = ''
    lines = body.split('\n')
    for line in lines:
        if line.strip().startswith('# ') and not line.strip().startswith('## '):
            title = line.strip().lstrip('# ').strip()
            break

    # 分离正文和简介
    description = ''
    hashtags = []

    if '---简介---' in body:
        main_body, _, desc_part = body.partition('---简介---')
    elif '--- 简介 ---' in body:
        main_body, _, desc_part = body.partition('--- 简介 ---')
    else:
        main_body = body
        desc_part = ''

    if desc_part:
        desc_lines = desc_part.strip().split('\n')
        desc_text_lines = []
        for line in desc_lines:
            line = line.strip()
            # 提取 hashtags
            if re.match(r'^#\S', line):
                # 这行是 hashtag 行
                tags = re.findall(r'#(\S+)', line)
                hashtags.extend(tags)
            elif line:
                desc_text_lines.append(line)
        description = '\n'.join(desc_text_lines)

    # 格式化正文（去掉 # 标题行，保留其余内容）
    body_lines = main_body.split('\n')
    formatted_lines = []
    for line in body_lines:
        stripped = line.strip()
        # 跳过 H1 标题（已提取）
        if stripped.startswith('# ') and not stripped.startswith('## '):
            continue
        # 保留 H2 但去掉 ## 标记
        if stripped.startswith('## '):
            formatted_lines.append(stripped[3:])
            continue
        # 去掉 Markdown 加粗标记
        cleaned = stripped.replace('**', '')
        formatted_lines.append(cleaned)

    formatted_body = '\n'.join(formatted_lines).strip()
    # 清理多余空行（保留最多一个）
    formatted_body = re.sub(r'\n{3,}', '\n\n', formatted_body)

    # 小红书标题限制 20 字
    if len(title) > 20:
        title = title[:19] + '…'

    return {
        'title': title,
        'body': formatted_body,
        'description': description,
        'hashtags': hashtags,
        'frontmatter': frontmatter,
    }


def find_images(image_dir: Path) -> List[Path]:
    """查找图片目录中的所有图片，按页码排序"""
    patterns = ['page-*.jpg', 'page-*.jpeg', 'page-*.png']
    images = []
    for pattern in patterns:
        images.extend(image_dir.glob(pattern))

    # 按页码数字排序
    def sort_key(p):
        match = re.search(r'page-(\d+)', p.stem)
        return int(match.group(1)) if match else 0

    images.sort(key=sort_key)
    return images


# ─── 人类行为模拟 ───

async def human_delay(min_ms=300, max_ms=800):
    """模拟人类操作间隔"""
    delay = random.randint(min_ms, max_ms) / 1000
    await asyncio.sleep(delay)


async def human_type(page, selector, text):
    """模拟人类打字速度"""
    element = await page.wait_for_selector(selector, timeout=10000)
    await element.click()
    await human_delay(200, 400)
    # 逐字输入，模拟真实打字
    for char in text:
        await page.keyboard.type(char, delay=random.randint(30, 80))
    await human_delay(300, 600)


# ─── 核心：登录 ───

async def login_and_save():
    """打开创作者中心登录页，等待手动登录后保存 cookies"""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("❌ 请先安装 playwright: pip install playwright && playwright install chromium")
        return False

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 800},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        page = await context.new_page()

        print("🌐 正在打开小红书创作者中心...")
        print("👉 请扫码或短信登录\n")

        await page.goto(LOGIN_URL)

        # 等待登录成功（检测到创作者中心的页面元素）
        print("⏳ 等待登录（最长 5 分钟）...")
        try:
            await page.wait_for_url("**/creator/**", timeout=300000)
            print("✅ 登录成功！")
        except Exception:
            print("⚠️ 等待超时，尝试保存当前 cookies...")

        cookies = await context.cookies()
        save_cookies(cookies)
        await browser.close()
        return True


# ─── 核心：上传内容到后台 ───

async def upload_to_backend(parsed: Dict, images: List[Path]):
    """打开发布页，上传图片、填写标题正文标签，然后停住"""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("❌ 请先安装 playwright: pip install playwright && playwright install chromium")
        return False

    cookies = load_cookies()
    if not cookies:
        print("❌ 未找到 cookies，请先登录：")
        print("   python xiaohongshu_uploader.py --login")
        return False

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,  # 必须有界面，用户要手动点发布
        )
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 900},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )

        # 加载 cookies
        await context.add_cookies(cookies)
        page = await context.new_page()

        print("🌐 正在打开发布页面...")
        await page.goto(PUBLISH_URL, wait_until="networkidle")
        await human_delay(2000, 3000)

        # 检查是否需要重新登录
        current_url = page.url
        if 'login' in current_url.lower() or 'sign' in current_url.lower():
            print("⚠️ Cookie 已过期，需要重新登录")
            print("👉 请在浏览器中登录...")
            try:
                await page.wait_for_url("**/publish/**", timeout=300000)
                # 登录成功后保存新 cookies
                new_cookies = await context.cookies()
                save_cookies(new_cookies)
                print("✅ 重新登录成功，cookies 已更新")
                await human_delay(2000, 3000)
            except Exception:
                print("❌ 登录超时")
                await browser.close()
                return False

        # ── Step 0: 切换到图文发布 tab ──
        print("\n📋 切换到图文发布模式...")

        # 小红书创作者中心默认可能在视频 tab，需要点击「上传图文」
        tab_selectors = [
            'div.creator-tab:has-text("上传图文")',
            'span:has-text("上传图文")',
            'div:has-text("上传图文"):not(:has(div))',
            '[class*="tab"]:has-text("图文")',
        ]
        for sel in tab_selectors:
            try:
                tab = await page.wait_for_selector(sel, timeout=3000)
                if tab:
                    await tab.click()
                    print("   ✅ 已切换到图文模式")
                    await human_delay(1500, 2500)
                    break
            except Exception:
                continue

        # ── Step 1: 上传图片 ──
        print(f"\n📸 上传图片（共 {len(images)} 张）...")

        # 小红书的 file input 通常是隐藏的，需要用 locator 直接操作
        # 找到接受图片的 file input（排除只接受视频的）
        image_paths = [str(img.resolve()) for img in images]

        uploaded = False
        # 尝试多种方式找到图片上传入口
        file_inputs = await page.query_selector_all('input[type="file"]')
        for fi in file_inputs:
            accept = await fi.get_attribute('accept') or ''
            # 跳过只接受视频的 input
            if accept and all(ext in accept for ext in ['.mp4', '.mov']) and '.jpg' not in accept and '.png' not in accept and '.jpeg' not in accept:
                continue
            # 这个 input 接受图片（或没有 accept 限制）
            try:
                await fi.set_input_files(image_paths)
                uploaded = True
                print(f"   ✅ 已选择 {len(images)} 张图片")
                break
            except Exception as e:
                print(f"   ⚠️ 上传尝试失败: {e}")
                continue

        if not uploaded:
            # 如果没有找到合适的 input，尝试所有 file input（包括隐藏的）
            for fi in file_inputs:
                try:
                    await fi.set_input_files(image_paths)
                    uploaded = True
                    print(f"   ✅ 已通过备选方式选择 {len(images)} 张图片")
                    break
                except Exception:
                    continue

        if not uploaded:
            print("   ❌ 未找到图片上传入口，请手动上传图片")
            print("   📂 图片路径：")
            for img in images:
                print(f"      {img}")

        # 等待图片上传完成
        print("   ⏳ 等待上传完成...")
        await human_delay(3000, 5000)

        # 等待上传指示器消失或图片预览出现
        for i in range(30):  # 最多等 30 秒
            await asyncio.sleep(1)
            uploading = await page.query_selector_all('[class*="uploading"], [class*="progress"]')
            if not uploading:
                break

        print("   ✅ 图片上传完成")
        await human_delay(1000, 2000)

        # ── Step 2: 填写标题 ──
        print(f"\n📝 填写标题: {parsed['title']}")

        # 小红书标题输入框
        title_selectors = [
            '#title-input',
            'input[placeholder*="标题"]',
            '[class*="title"] input',
            '[class*="title"] [contenteditable]',
            'input[maxlength="20"]',
        ]

        title_filled = False
        for sel in title_selectors:
            try:
                title_el = await page.wait_for_selector(sel, timeout=3000)
                if title_el:
                    await title_el.click()
                    await human_delay(200, 400)
                    await page.keyboard.type(parsed['title'], delay=random.randint(30, 80))
                    title_filled = True
                    print("   ✅ 标题已填写")
                    break
            except Exception:
                continue

        if not title_filled:
            print("   ⚠️ 未找到标题输入框，请手动填写")

        await human_delay(500, 1000)

        # ── Step 3: 填写正文（简介/描述）──
        desc_text = parsed['description'] if parsed['description'] else parsed['body'][:500]
        print(f"\n📝 填写正文（{len(desc_text)} 字）...")

        desc_selectors = [
            '#post-textarea',
            '[placeholder*="输入正文描述"]',
            '[placeholder*="添加正文"]',
            '[class*="post-content"] [contenteditable]',
            '[class*="desc"] [contenteditable]',
            '[contenteditable="true"]',
        ]

        desc_filled = False
        for sel in desc_selectors:
            try:
                desc_el = await page.wait_for_selector(sel, timeout=3000)
                if desc_el:
                    await desc_el.click()
                    await human_delay(300, 500)
                    # 正文较长，用粘贴代替逐字输入
                    await page.evaluate(
                        '''(text) => {
                            navigator.clipboard.writeText(text);
                        }''',
                        desc_text
                    )
                    # macOS: Cmd+V 粘贴
                    await page.keyboard.press('Meta+v')
                    await human_delay(500, 1000)
                    desc_filled = True
                    print("   ✅ 正文已填写")
                    break
            except Exception:
                continue

        if not desc_filled:
            print("   ⚠️ 未找到正文输入框，请手动填写")
            # 备选：复制到系统剪贴板
            try:
                import subprocess
                process = subprocess.Popen(['pbcopy'], stdin=subprocess.PIPE)
                process.communicate(desc_text.encode('utf-8'))
                print("   📋 正文已复制到剪贴板，可手动粘贴")
            except Exception:
                pass

        await human_delay(500, 1000)

        # ── Step 4: 添加标签 ──
        if parsed['hashtags']:
            print(f"\n🏷️ 添加标签: {', '.join(parsed['hashtags'][:5])}")

            # 先点击「# 话题」按钮展开输入
            topic_btn_selectors = [
                'button.topic-btn',
                'button:has-text("话题")',
                'button.contentBtn.topic-btn',
            ]
            topic_opened = False
            for sel in topic_btn_selectors:
                try:
                    btn = await page.wait_for_selector(sel, timeout=3000)
                    if btn:
                        await btn.click()
                        await human_delay(500, 800)
                        topic_opened = True
                        break
                except Exception:
                    continue

            if topic_opened:
                for tag in parsed['hashtags'][:5]:
                    try:
                        # 在弹出的话题搜索框中输入
                        topic_input = await page.wait_for_selector(
                            'input[placeholder*="搜索话题"], input[placeholder*="话题"], input[type="text"]',
                            timeout=3000
                        )
                        if topic_input:
                            await topic_input.click()
                            await human_delay(200, 400)
                            # 清空输入框
                            await page.keyboard.press('Meta+a')
                            await page.keyboard.type(tag, delay=random.randint(30, 80))
                            await human_delay(800, 1200)
                            # 点击第一个搜索结果
                            try:
                                first_result = await page.wait_for_selector(
                                    '[class*="topic-item"], [class*="search-item"], [class*="result"] div',
                                    timeout=3000
                                )
                                if first_result:
                                    await first_result.click()
                                    await human_delay(500, 800)
                            except Exception:
                                # 没有搜索结果就按回车
                                await page.keyboard.press('Enter')
                                await human_delay(500, 800)
                    except Exception:
                        continue
                print("   ✅ 标签已添加")
            else:
                print("   ⚠️ 未找到话题按钮，跳过标签")

        # ── Step 5: 保存草稿 ──
        print("\n💾 保存草稿...")
        # 滚动到页面底部，确保"暂存离开"按钮可见
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await human_delay(3000, 5000)  # 等久一点让页面完全渲染

        draft_selectors = [
            # 新版小红书创作者中心
            'button:has-text("暂存离开")',
            'div.publish-page-publish-btn button:first-child',
            # 旧版
            'button:has-text("存草稿")',
            'button:has-text("保存草稿")',
            'span:has-text("存草稿")',
            'button:has-text("草稿")',
        ]

        draft_saved = False
        # 第一轮：精确选择器
        for sel in draft_selectors:
            try:
                draft_btn = await page.wait_for_selector(sel, timeout=3000)
                if draft_btn:
                    # 确保按钮在视口内
                    await draft_btn.scroll_into_view_if_needed()
                    await human_delay(500, 800)
                    await draft_btn.click()
                    await human_delay(4000, 6000)
                    # 检查是否跳转到了笔记管理页（说明保存成功）
                    if '笔记管理' in (await page.title()) or 'publish' not in page.url:
                        draft_saved = True
                        print("   ✅ 草稿已保存（已跳转）")
                    else:
                        draft_saved = True
                        print("   ✅ 草稿保存已点击")
                    break
            except Exception:
                continue

        # 第二轮：遍历所有按钮和可点击元素
        if not draft_saved:
            print("   ⚠️ 精确选择器未命中，扫描页面按钮...")
            try:
                # 尝试所有 button 元素
                all_buttons = await page.query_selector_all('button')
                for btn in all_buttons:
                    text = (await btn.text_content() or '').strip()
                    if '草稿' in text:
                        await btn.click()
                        await human_delay(3000, 4000)
                        draft_saved = True
                        print(f"   ✅ 草稿已保存 (按钮: '{text}')")
                        break
            except Exception:
                pass

        # 第三轮：通过 JavaScript 点击
        if not draft_saved:
            try:
                result = await page.evaluate("""() => {
                    const els = document.querySelectorAll('button, div[class*="btn"], span[role="button"]');
                    for (const el of els) {
                        if (el.textContent.includes('草稿')) {
                            el.click();
                            return el.textContent.trim();
                        }
                    }
                    return null;
                }""")
                if result:
                    await human_delay(3000, 4000)
                    draft_saved = True
                    print(f"   ✅ 草稿已保存 (JS点击: '{result}')")
            except Exception:
                pass

        if not draft_saved:
            print("   ❌ 未能自动保存草稿，截图诊断中...")
            # 截图保存供诊断
            screenshot_path = str(BASE_DIR / "60_Published" / "social-media" / "output" / "debug_screenshot.png")
            await page.screenshot(path=screenshot_path, full_page=True)
            print(f"   📸 截图已保存: {screenshot_path}")
            # 打印页面上所有按钮文本
            buttons_info = await page.evaluate("""() => {
                const results = [];
                const els = document.querySelectorAll('button, [role="button"], div[class*="btn"], a[class*="btn"]');
                for (const el of els) {
                    const text = el.textContent.trim().substring(0, 50);
                    const tag = el.tagName;
                    const cls = el.className.substring(0, 80);
                    if (text) results.push(tag + ' | ' + cls + ' | ' + text);
                }
                return results;
            }""")
            print("   页面按钮列表:")
            for b in buttons_info:
                print(f"     {b}")
            await asyncio.sleep(5)

        # 保存最新 cookies
        try:
            new_cookies = await context.cookies()
            save_cookies(new_cookies)
        except Exception:
            pass

        print("\n" + "=" * 50)
        if draft_saved:
            print("✅ 完成！草稿已保存到小红书后台")
        else:
            print("⚠️ 内容已填充，请在浏览器中手动保存草稿")
        print("=" * 50)

        # 非交互模式直接关闭，交互模式等待确认
        try:
            if sys.stdin.isatty():
                print("\n👉 请在浏览器中检查内容，完成后按回车关闭浏览器...")
                await asyncio.get_event_loop().run_in_executor(None, input)
        except (EOFError, OSError):
            pass

        # 关闭前再保存一次 cookies
        try:
            new_cookies = await context.cookies()
            save_cookies(new_cookies)
        except Exception:
            pass

        await browser.close()
        return draft_saved


# ─── 主函数 ───

def main():
    parser = argparse.ArgumentParser(
        description='小红书上传助手 - 自动填充内容到创作者后台'
    )
    parser.add_argument('markdown', nargs='?', help='Markdown 文件路径')
    parser.add_argument('images', nargs='?', help='图片目录路径')
    parser.add_argument('--login', action='store_true', help='登录并保存 cookies')

    args = parser.parse_args()

    # 登录模式
    if args.login:
        print("🔐 启动登录流程...")
        asyncio.run(login_and_save())
        return

    # 上传模式
    if not args.markdown or not args.images:
        parser.print_help()
        print("\n示例：")
        print("  # 首次使用先登录")
        print("  python xiaohongshu_uploader.py --login")
        print()
        print("  # 上传内容")
        print("  python xiaohongshu_uploader.py \\")
        print("    ~/claude-workflows/60_Published/social-media/yuejian/2026-03-12_xxx_小红书.md \\")
        print("    ~/claude-workflows/60_Published/social-media/output/article1/")
        sys.exit(1)

    md_path = Path(args.markdown).expanduser()
    img_dir = Path(args.images).expanduser()

    # 验证文件
    if not md_path.exists():
        print(f"❌ Markdown 文件不存在: {md_path}")
        sys.exit(1)

    if not img_dir.exists() or not img_dir.is_dir():
        print(f"❌ 图片目录不存在: {img_dir}")
        sys.exit(1)

    # 解析内容
    print(f"📄 解析文件: {md_path.name}")
    parsed = parse_markdown(md_path)

    print(f"   标题: {parsed['title']}")
    print(f"   正文: {len(parsed['body'])} 字")
    print(f"   简介: {len(parsed['description'])} 字")
    print(f"   标签: {', '.join(parsed['hashtags']) if parsed['hashtags'] else '无'}")

    # 查找图片
    images = find_images(img_dir)
    if not images:
        print(f"❌ 图片目录中没有找到图片: {img_dir}")
        sys.exit(1)

    print(f"\n🖼️ 找到 {len(images)} 张图片:")
    for img in images:
        print(f"   {img.name}")

    print()

    # 开始上传
    asyncio.run(upload_to_backend(parsed, images))


if __name__ == '__main__':
    main()
