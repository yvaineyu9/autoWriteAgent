#!/usr/bin/env python3
"""
小红书批量上传 — 一个浏览器会话连续上传多篇到草稿箱

用法:
    python xhs_batch_upload.py <markdown文件1> <图片目录1> [<markdown文件2> <图片目录2> ...]
    python xhs_batch_upload.py --pairs pairs.txt  # 从文件读取 markdown+图片目录 对
"""

import asyncio
import json
import os
import re
import sys
import random
import argparse
from pathlib import Path
from datetime import datetime, timedelta

BASE_DIR = Path.home() / "claude-workflows"
SECRETS_DIR = BASE_DIR / ".secrets"
COOKIES_FILE = SECRETS_DIR / "xiaohongshu_cookies.json"
PUBLISH_URL = "https://creator.xiaohongshu.com/publish/publish"

SECRETS_DIR.mkdir(parents=True, exist_ok=True)


def load_cookies():
    if COOKIES_FILE.exists():
        try:
            with open(COOKIES_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️ 加载 cookies 失败: {e}")
    return None


def save_cookies(cookies):
    try:
        with open(COOKIES_FILE, 'w', encoding='utf-8') as f:
            json.dump(cookies, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def parse_markdown(file_path):
    content = Path(file_path).read_text(encoding='utf-8')
    frontmatter = {}
    body = content
    if content.startswith('---'):
        parts = content.split('---', 2)
        if len(parts) >= 3:
            fm_text = parts[1].strip()
            for line in fm_text.split('\n'):
                if ':' in line:
                    key, _, value = line.partition(':')
                    frontmatter[key.strip()] = value.strip()
            body = parts[2].strip()

    title = ''
    lines = body.split('\n')
    for line in lines:
        if line.strip().startswith('# ') and not line.strip().startswith('## '):
            title = line.strip().lstrip('# ').strip()
            break

    description = ''
    hashtags = []
    if '---简介---' in body:
        _, _, desc_part = body.partition('---简介---')
    elif '--- 简介 ---' in body:
        _, _, desc_part = body.partition('--- 简介 ---')
    else:
        desc_part = ''

    if desc_part:
        for line in desc_part.strip().split('\n'):
            line = line.strip()
            if re.match(r'^#\S', line):
                hashtags.extend(re.findall(r'#(\S+)', line))
            elif line:
                description += line + '\n'
        description = description.strip()

    if len(title) > 20:
        title = title[:19] + '…'

    return {
        'title': title,
        'description': description,
        'hashtags': hashtags,
    }


def find_images(image_dir):
    img_dir = Path(image_dir)
    images = []
    for pattern in ['page-*.jpg', 'page-*.jpeg', 'page-*.png']:
        images.extend(img_dir.glob(pattern))
    images.sort(key=lambda p: int(re.search(r'page-(\d+)', p.stem).group(1)) if re.search(r'page-(\d+)', p.stem) else 0)
    return images


async def human_delay(min_ms=300, max_ms=800):
    await asyncio.sleep(random.randint(min_ms, max_ms) / 1000)


async def upload_one(page, parsed, images, index, total):
    """在已打开的发布页上传一篇内容并保存草稿"""
    label = f"[{index}/{total}]"

    # 确保在发布页
    if 'publish' not in page.url:
        await page.goto(PUBLISH_URL, wait_until="networkidle")
        await human_delay(2000, 3000)

    # 切换到图文模式（必须点击"上传图文" tab）
    tab_switched = False
    for sel in [
        'text="上传图文"',
        ':text("上传图文")',
        'div:has-text("上传图文"):not(:has(div:has-text("上传图文")))',
        'span:has-text("上传图文")',
    ]:
        try:
            tab = await page.wait_for_selector(sel, timeout=3000)
            if tab:
                await tab.click()
                await human_delay(2000, 3000)
                tab_switched = True
                print(f"  {label}   ✅ 已切换到图文模式")
                break
        except Exception:
            continue
    if not tab_switched:
        # JS 兜底
        try:
            await page.evaluate("""() => {
                const tabs = document.querySelectorAll('div, span, a');
                for (const t of tabs) {
                    if (t.textContent.trim() === '上传图文' || t.textContent.trim() === '上传图文') {
                        t.click();
                        return true;
                    }
                }
                return false;
            }""")
            await human_delay(2000, 3000)
            print(f"  {label}   ✅ 已通过 JS 切换到图文模式")
        except Exception:
            print(f"  {label}   ⚠️ 未能切换到图文模式")

    # 等待图片上传区域出现
    await human_delay(1000, 2000)

    # 1. 上传图片
    print(f"  {label} 📸 上传 {len(images)} 张图片...")
    image_paths = [str(img.resolve()) for img in images]

    # 等待页面 file input 加载
    await human_delay(2000, 3000)
    file_inputs = await page.query_selector_all('input[type="file"]')
    print(f"  {label}   找到 {len(file_inputs)} 个 file input")

    uploaded = False
    for idx, fi in enumerate(file_inputs):
        accept = await fi.get_attribute('accept') or ''
        print(f"  {label}   input[{idx}] accept='{accept}'")
        # 跳过只接受视频的
        if accept and 'video' in accept and 'image' not in accept:
            continue
        try:
            await fi.set_input_files(image_paths)
            uploaded = True
            print(f"  {label}   ✅ 通过 input[{idx}] 上传成功")
            break
        except Exception as e:
            print(f"  {label}   input[{idx}] 失败: {e}")
            continue

    if not uploaded:
        # 兜底：尝试所有 file input
        for idx, fi in enumerate(file_inputs):
            try:
                await fi.set_input_files(image_paths)
                uploaded = True
                print(f"  {label}   ✅ 兜底通过 input[{idx}] 上传成功")
                break
            except Exception:
                continue

    if not uploaded:
        print(f"  {label} ❌ 图片上传失败")
        ss = str(BASE_DIR / "60_Published" / "social-media" / "output" / f"debug_upload_{index}.png")
        await page.screenshot(path=ss, full_page=True)
        print(f"  {label} 📸 截图: {ss}")
        return False

    # 等待上传完成
    await human_delay(3000, 5000)
    for _ in range(30):
        await asyncio.sleep(1)
        uploading = await page.query_selector_all('[class*="uploading"], [class*="progress"]')
        if not uploading:
            break
    await human_delay(1000, 2000)

    # 2. 填标题
    print(f"  {label} 📝 标题: {parsed['title']}")
    for sel in ['#title-input', 'input[placeholder*="标题"]', 'input[maxlength="20"]']:
        try:
            el = await page.wait_for_selector(sel, timeout=3000)
            if el:
                await el.click()
                await human_delay(200, 400)
                await page.keyboard.type(parsed['title'], delay=random.randint(30, 80))
                break
        except Exception:
            continue
    await human_delay(500, 1000)

    # 3. 填正文
    desc = parsed['description'] if parsed['description'] else ''
    if desc:
        print(f"  {label} 📝 正文 ({len(desc)} 字)")
        for sel in ['#post-textarea', '[placeholder*="输入正文"]', '[placeholder*="添加正文"]', '[contenteditable="true"]']:
            try:
                el = await page.wait_for_selector(sel, timeout=3000)
                if el:
                    await el.click()
                    await human_delay(300, 500)
                    await page.evaluate('(text) => navigator.clipboard.writeText(text)', desc)
                    await page.keyboard.press('Meta+v')
                    await human_delay(500, 1000)
                    break
            except Exception:
                continue
    await human_delay(500, 1000)

    # 4. 添加话题标签
    if parsed['hashtags']:
        print(f"  {label} 🏷️ 标签: {', '.join(parsed['hashtags'][:5])}")
        # 点击话题按钮
        try:
            topic_btn = await page.wait_for_selector('button.topic-btn, button:has-text("话题")', timeout=3000)
            if topic_btn:
                await topic_btn.click()
                await human_delay(800, 1200)

                for tag in parsed['hashtags'][:5]:
                    try:
                        # 找到话题搜索输入框
                        topic_input = await page.wait_for_selector(
                            'input[placeholder*="搜索"], input[placeholder*="话题"]',
                            timeout=3000
                        )
                        if topic_input:
                            await topic_input.click()
                            await topic_input.fill('')
                            await human_delay(200, 300)
                            await page.keyboard.type(tag, delay=random.randint(30, 80))
                            await human_delay(1000, 1500)
                            # 点第一个搜索结果
                            try:
                                result = await page.wait_for_selector(
                                    '[class*="topic-item"], [class*="search-item"], [class*="result-item"]',
                                    timeout=3000
                                )
                                if result:
                                    await result.click()
                                    await human_delay(500, 800)
                            except Exception:
                                await page.keyboard.press('Enter')
                                await human_delay(500, 800)
                    except Exception:
                        continue
        except Exception:
            print(f"  {label} ⚠️ 话题添加跳过")
    await human_delay(500, 1000)

    # 5. 定时发布（明天 + 随机时间，8:00-22:00之间）
    tomorrow = datetime.now() + timedelta(days=1)
    rand_hour = random.randint(8, 21)
    rand_minute = random.randint(0, 59)
    schedule_time = tomorrow.replace(hour=rand_hour, minute=rand_minute, second=0)
    schedule_str = schedule_time.strftime("%Y-%m-%d %H:%M")
    print(f"  {label} 📅 定时发布: {schedule_str}")

    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    await human_delay(2000, 3000)

    saved = False

    # 找到"定时发布"旁边的 toggle 开关并打开
    schedule_toggled = False

    # 方法1: 找到"定时发布"文字，然后点击其旁边的 toggle/switch
    try:
        toggled = await page.evaluate("""() => {
            // 找到包含"定时发布"的元素
            const els = document.querySelectorAll('*');
            for (const el of els) {
                if (el.childNodes.length === 1 && el.textContent.trim() === '定时发布') {
                    // 找到其父元素中的 toggle/switch
                    const parent = el.closest('div') || el.parentElement;
                    if (!parent) continue;
                    // 尝试点击同级或相邻的 toggle
                    const toggle = parent.querySelector('input[type="checkbox"], [class*="switch"], [class*="toggle"], [role="switch"]');
                    if (toggle) {
                        toggle.click();
                        return 'found-toggle';
                    }
                    // 也可能整个行是可点击的
                    parent.click();
                    return 'clicked-parent';
                }
            }
            return false;
        }""")
        if toggled:
            await human_delay(1500, 2500)
            schedule_toggled = True
            print(f"  {label}   ✅ 定时发布toggle: {toggled}")
    except Exception as e:
        print(f"  {label}   toggle方法1异常: {e}")

    if not schedule_toggled:
        # 方法2: 直接找所有 switch/toggle，取最后一个（通常定时发布在最下面）
        try:
            toggled2 = await page.evaluate("""() => {
                const switches = document.querySelectorAll('[class*="switch"], [role="switch"]');
                // 定时发布的开关通常是最后一个
                for (const sw of switches) {
                    const text = sw.closest('div')?.textContent || '';
                    if (text.includes('定时发布')) {
                        sw.click();
                        return true;
                    }
                }
                return false;
            }""")
            if toggled2:
                await human_delay(1500, 2500)
                schedule_toggled = True
                print(f"  {label}   ✅ 方法2打开了定时发布toggle")
        except Exception:
            pass

    await human_delay(1000, 1500)

    # 截图看 toggle 后的 UI
    ss_schedule = str(BASE_DIR / "60_Published" / "social-media" / "output" / f"debug_schedule_ui_{index}.png")
    await page.screenshot(path=ss_schedule)
    print(f"  {label}   📸 定时发布UI截图: {ss_schedule}")

    # 设置日期和时间
    date_str = schedule_time.strftime("%Y-%m-%d")
    time_str = schedule_time.strftime("%H:%M")

    # 列出所有 input 帮助调试（toggle 开启后应该出现新的日期时间 input）
    inputs_info = await page.evaluate("""() => {
        const inputs = document.querySelectorAll('input');
        return Array.from(inputs).map(i => ({
            type: i.type, placeholder: i.placeholder,
            value: i.value, cls: i.className.slice(0, 50)
        }));
    }""")
    print(f"  {label}   页面inputs: {json.dumps(inputs_info, ensure_ascii=False)}")

    # 尝试填写日期
    date_filled = False
    for sel in [
        'input[placeholder*="日期"]',
        'input[placeholder*="选择日期"]',
        'input[type="date"]',
        '.date-picker input',
        'input[class*="date"]',
    ]:
        try:
            date_input = await page.wait_for_selector(sel, timeout=2000)
            if date_input:
                await date_input.click()
                await human_delay(300, 500)
                await date_input.fill(date_str)
                await human_delay(500, 800)
                date_filled = True
                print(f"  {label}   填入日期: {date_str}")
                break
        except Exception:
            continue

    # 尝试填写时间
    time_filled = False
    for sel in [
        'input[placeholder*="时间"]',
        'input[placeholder*="选择时间"]',
        'input[type="time"]',
        '.time-picker input',
        'input[class*="time"]',
    ]:
        try:
            time_input = await page.wait_for_selector(sel, timeout=2000)
            if time_input:
                await time_input.click()
                await human_delay(300, 500)
                await time_input.fill(time_str)
                await human_delay(500, 800)
                time_filled = True
                print(f"  {label}   填入时间: {time_str}")
                break
        except Exception:
            continue

    # 如果没找到标准 input，尝试找 d-text 类型的 input（小红书可能用自定义组件）
    if not date_filled or not time_filled:
        # 截图看当前状态
        ss_debug = str(BASE_DIR / "60_Published" / "social-media" / "output" / f"debug_datetime_{index}.png")
        await page.screenshot(path=ss_debug)
        print(f"  {label}   📸 日期时间调试截图: {ss_debug}")
        print(f"  {label}   ⚠️ 日期填入:{date_filled} 时间填入:{time_filled}")

    await human_delay(1000, 1500)

    if not schedule_toggled:
        print(f"  {label}   ❌ 定时发布开关未能打开，跳过发布以防直接发布")
        return False

    # 点击"发布"按钮
    try:
        pub_btn = await page.wait_for_selector('button:has-text("发布")', timeout=5000)
        if pub_btn:
            await pub_btn.scroll_into_view_if_needed()
            await human_delay(500, 800)
            await pub_btn.click()
            await human_delay(3000, 5000)
            saved = True
            print(f"  {label}   ✅ 点击了发布按钮")
    except Exception as e:
        print(f"  {label}   发布按钮异常: {e}")

    # 截图确认结果
    ss_after = str(BASE_DIR / "60_Published" / "social-media" / "output" / f"debug_after_save_{index}.png")
    await page.screenshot(path=ss_after)
    print(f"  {label}   📸 发布后截图: {ss_after}")

    if saved:
        print(f"  {label} ✅ 草稿保存流程完成")
    else:
        print(f"  {label} ❌ 保存失败！")
        # 截图
        ss = str(BASE_DIR / "60_Published" / "social-media" / "output" / f"debug_{index}.png")
        await page.screenshot(path=ss, full_page=True)
        print(f"  {label} 📸 截图: {ss}")
        return False

    # 等一下再继续下一篇
    await human_delay(2000, 3000)

    # 回到发布页准备下一篇
    await page.goto(PUBLISH_URL, wait_until="networkidle")
    await human_delay(2000, 3000)

    return True


async def main_batch(pairs):
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("❌ 请先安装 playwright: pip install playwright && playwright install chromium")
        return

    cookies = load_cookies()
    if not cookies:
        print("❌ 未找到 cookies，请先登录")
        return

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 900},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        await context.add_cookies(cookies)
        page = await context.new_page()

        # 先打开发布页
        print("🌐 打开小红书创作者中心...")
        await page.goto(PUBLISH_URL, wait_until="networkidle")
        await human_delay(2000, 3000)

        # 检查登录状态
        if 'login' in page.url.lower() or 'sign' in page.url.lower():
            print("⚠️ Cookie 已过期，请在浏览器中登录...")
            try:
                await page.wait_for_url("**/publish/**", timeout=300000)
                new_cookies = await context.cookies()
                save_cookies(new_cookies)
                print("✅ 登录成功")
                await human_delay(2000, 3000)
            except Exception:
                print("❌ 登录超时")
                await browser.close()
                return

        total = len(pairs)
        success = 0
        failed = []

        for i, (md_path, img_dir) in enumerate(pairs, 1):
            parsed = parse_markdown(md_path)
            images = find_images(img_dir)

            print(f"\n{'='*60}")
            print(f"[{i}/{total}] {parsed['title']}")
            print(f"{'='*60}")

            if not images:
                print(f"  ❌ 没有找到图片: {img_dir}")
                failed.append(parsed['title'])
                continue

            ok = await upload_one(page, parsed, images, i, total)
            if ok:
                success += 1
            else:
                failed.append(parsed['title'])

        # 保存 cookies
        try:
            new_cookies = await context.cookies()
            save_cookies(new_cookies)
        except Exception:
            pass

        print(f"\n{'='*60}")
        print(f"批量上传完成: {success}/{total} 成功")
        if failed:
            print(f"失败: {', '.join(failed)}")
        print(f"{'='*60}")

        # 不关浏览器，让用户检查
        if sys.stdin.isatty():
            input("\n按回车关闭浏览器...")
        await browser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="小红书批量上传到草稿箱")
    parser.add_argument('args', nargs='*', help='交替的 markdown文件 和 图片目录')
    args = parser.parse_args()

    if len(args.args) < 2 or len(args.args) % 2 != 0:
        print("用法: python xhs_batch_upload.py <md1> <imgs1> [<md2> <imgs2> ...]")
        sys.exit(1)

    pairs = []
    for i in range(0, len(args.args), 2):
        pairs.append((args.args[i], args.args[i + 1]))

    asyncio.run(main_batch(pairs))
