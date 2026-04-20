#!/usr/bin/env python3
"""
小红书页面解析器：采集笔记内容和互动数据。

用法：
  from browser.engine import BrowserEngine
  from browser.xhs import XhsScraper

  with BrowserEngine() as engine:
      scraper = XhsScraper(engine)
      note = scraper.scrape_note("https://www.xiaohongshu.com/explore/xxx")
      metrics = scraper.scrape_metrics("https://www.xiaohongshu.com/explore/xxx")
"""

import re
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional

from playwright.sync_api import Page

from .engine import BrowserEngine
from .ocr import ocr_bytes


@dataclass
class NoteData:
    """单篇笔记的完整数据。"""
    note_id: str = ""
    source_url: str = ""
    title: str = ""
    author: str = ""
    author_id: str = ""
    published_at: str = ""
    content_text: str = ""
    tags: list[str] = field(default_factory=list)
    images_count: int = 0
    image_ocr: list[str] = field(default_factory=list)
    likes: int = 0
    collects: int = 0
    comments: int = 0
    shares: Optional[int] = None
    views: Optional[int] = None
    captured_at: str = ""
    capture_status: str = "success"  # success / partial / failed
    failure_reason: str = ""


@dataclass
class MetricsData:
    """互动数据快照。"""
    likes: int = 0
    collects: int = 0
    comments: int = 0
    shares: Optional[int] = None
    views: Optional[int] = None
    platform_status: str = "normal"  # normal / deleted / reviewing / limited / inaccessible
    captured_at: str = ""
    failure_reason: str = ""


@dataclass
class NoteSummary:
    """笔记摘要（列表页使用）。"""
    note_id: str = ""
    title: str = ""
    author: str = ""
    source_url: str = ""
    cover_url: str = ""
    likes: int = 0


def _parse_count(text: str) -> int:
    """解析互动数字（处理 '万' 单位和空文本）。"""
    if not text:
        return 0
    text = text.strip()
    if text in ("赞", "收藏", "评论", "分享", "转发"):
        return 0
    try:
        if "万" in text:
            return int(float(text.replace("万", "")) * 10000)
        return int(text)
    except (ValueError, TypeError):
        return 0


def _extract_note_id(url: str) -> str:
    """从 URL 提取 note_id。"""
    # https://www.xiaohongshu.com/explore/xxx?...
    # https://www.xiaohongshu.com/discovery/item/xxx?...
    # https://www.xiaohongshu.com/user/profile/<uid>/<note_id>?...
    match = re.search(r'(?:explore|discovery/item|notes?|user/profile/[^/]+)/([a-f0-9]+)', url)
    return match.group(1) if match else ""


class XhsScraper:
    """小红书采集器。"""

    def __init__(self, engine: BrowserEngine):
        self.engine = engine

    def scrape_note(self, url: str) -> NoteData:
        """采集单篇笔记的完整内容（含 OCR）。"""
        note = NoteData(
            note_id=_extract_note_id(url),
            source_url=url,
            captured_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )

        page = self.engine.new_page()
        try:
            self._do_scrape_note(page, url, note)
        except Exception as e:
            note.capture_status = "failed"
            note.failure_reason = str(e)
            print(f"采集失败: {e}", file=sys.stderr)
        finally:
            page.close()

        return note

    def _do_scrape_note(self, page: Page, url: str, note: NoteData):
        """实际的笔记采集逻辑。"""
        # 确保 viewport 足够大，避免图片被挤压
        page.set_viewport_size({"width": 1440, "height": 900})
        BrowserEngine.safe_goto(page, url)

        # 检查页面状态
        if self._check_page_error(page):
            note.capture_status = "failed"
            note.failure_reason = "页面不可用或已删除"
            return

        # 等待笔记容器加载
        try:
            page.wait_for_selector('#noteContainer', timeout=10000)
        except Exception:
            self._dismiss_popups(page)
            try:
                page.wait_for_selector('#noteContainer', timeout=5000)
            except Exception:
                pass

        self._dismiss_popups(page)
        BrowserEngine.random_delay(1.0, 2.0)

        # 限定在 #noteContainer 内采集，避免拿到 feed 卡片的数据
        container = page.query_selector('#noteContainer')
        if not container:
            note.capture_status = "failed"
            note.failure_reason = "未找到笔记容器 #noteContainer"
            return

        # --- 标题 ---
        note.title = self._extract_text_in(container, [
            '#detail-title',
            '.title',
        ])

        # --- 正文（#detail-desc 内文字，排除标签链接） ---
        desc_el = container.query_selector('#detail-desc')
        if desc_el:
            # 提取纯文本部分（标签在 a.tag 里，单独处理）
            note.content_text = (desc_el.inner_text() or "").strip()
            # 去掉标签文字（以 # 开头的行）
            lines = note.content_text.split('\n')
            content_lines = [l for l in lines if not l.strip().startswith('#')]
            note.content_text = '\n'.join(content_lines).strip()

        # --- 作者 ---
        note.author = self._extract_text_in(container, [
            '.author-container .username',
            '.author-container .name',
            '.author-wrapper .username',
            '.author-wrapper .name',
        ])

        # --- 作者 ID ---
        author_link = container.query_selector('.author-container a.name, .author-wrapper a.name')
        if author_link:
            href = author_link.get_attribute('href') or ''
            match = re.search(r'/user/profile/(\w+)', href)
            if match:
                note.author_id = match.group(1)

        # --- 发布时间 ---
        note.published_at = self._extract_text_in(container, [
            '.note-content .date',
            '.note-content .bottom-container',
            'span.date',
        ])

        # --- 互动数据（底部操作栏） ---
        # 小红书笔记详情页的互动数据在底部 engage-bar 里
        # 选择器: .engage-bar 或 #noteContainer 底部的 span.count
        note.likes, note.collects, note.comments = self._extract_engage_counts(container)

        # --- 标签 ---
        tag_elements = container.query_selector_all('#detail-desc a.tag, a#hash-tag')
        for el in tag_elements:
            tag_text = (el.inner_text() or "").strip().lstrip('#')
            if tag_text and tag_text not in note.tags:
                note.tags.append(tag_text)

        # --- 图片 OCR ---
        self._scrape_images_ocr(page, note)

        # 判断 capture_status
        has_ocr = any(t.strip() for t in note.image_ocr)
        if not note.title and not note.content_text and not has_ocr:
            note.capture_status = "failed"
            note.failure_reason = "未能提取标题和正文"
        elif not note.title and not note.content_text and has_ocr:
            # 图片文字笔记：用 OCR 第一行作为标题
            first_ocr = next((t.strip() for t in note.image_ocr if t.strip()), "")
            first_line = first_ocr.split('\n')[0][:50]
            note.title = first_line
            note.capture_status = "partial"
            note.failure_reason = "图片文字笔记，标题取自 OCR"
        elif not note.title or not note.content_text:
            note.capture_status = "partial"
            note.failure_reason = "部分字段缺失"

    def scrape_metrics(self, url: str) -> MetricsData:
        """仅采集互动数据（轻量版）。"""
        metrics = MetricsData(
            captured_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )

        page = self.engine.new_page()
        try:
            BrowserEngine.safe_goto(page, url)

            # 检查页面状态
            if self._check_page_error(page):
                metrics.platform_status = self._detect_status(page)
                metrics.failure_reason = f"页面状态: {metrics.platform_status}"
                return metrics

            self._dismiss_popups(page)
            page.wait_for_timeout(2000)

            try:
                page.wait_for_selector('#noteContainer', timeout=5000)
            except Exception:
                metrics.platform_status = "inaccessible"
                metrics.failure_reason = "未进入笔记详情页"
                return metrics

            container = page.query_selector('#noteContainer')
            if not container:
                metrics.platform_status = "inaccessible"
                metrics.failure_reason = "未找到笔记容器 #noteContainer"
                return metrics

            metrics.likes, metrics.collects, metrics.comments = self._extract_engage_counts(container)
            metrics.platform_status = "normal"

        except Exception as e:
            metrics.platform_status = "inaccessible"
            metrics.failure_reason = str(e)
            print(f"Metrics 采集失败: {e}", file=sys.stderr)
        finally:
            page.close()

        return metrics

    def scrape_favorites(self, limit: int = 20) -> list[NoteSummary]:
        """采集收藏页笔记列表。"""
        page = self.engine.new_page()
        summaries = []

        try:
            BrowserEngine.safe_goto(page, "https://www.xiaohongshu.com")
            BrowserEngine.random_delay(2.0, 3.0)
            self._dismiss_popups(page)

            # 进入收藏页（个人主页 → 收藏）
            # 先进个人主页
            avatar = page.query_selector('a[href*="/user/profile"], .user-avatar, [class*="sidebar"] a[class*="user"]')
            if avatar:
                avatar.click()
                BrowserEngine.random_delay(2.0, 3.0)

            # 点收藏 tab
            tabs = page.query_selector_all('.tabs .tab, [class*="tab-item"], [role="tab"]')
            for tab in tabs:
                text = (tab.inner_text() or "").strip()
                if "收藏" in text:
                    tab.click()
                    BrowserEngine.random_delay(2.0, 3.0)
                    break

            # 采集笔记卡片
            summaries = self._scrape_note_cards(page, limit)

        except Exception as e:
            print(f"收藏页采集失败: {e}", file=sys.stderr)
        finally:
            page.close()

        return summaries

    def scrape_account(self, account_url: str, limit: int = 20) -> list[NoteSummary]:
        """采集账号主页的笔记列表。"""
        page = self.engine.new_page()
        summaries = []

        try:
            BrowserEngine.safe_goto(page, account_url)
            self._dismiss_popups(page)
            BrowserEngine.random_delay(2.0, 3.0)

            summaries = self._scrape_note_cards(page, limit)

        except Exception as e:
            print(f"账号页采集失败: {e}", file=sys.stderr)
        finally:
            page.close()

        return summaries

    # ========== 内部方法 ==========

    def _extract_text_in(self, container, selectors: list[str]) -> str:
        """在指定容器内尝试多个选择器提取文本。"""
        for sel in selectors:
            try:
                el = container.query_selector(sel)
                if el:
                    text = (el.inner_text() or "").strip()
                    if text:
                        return text
            except Exception:
                continue
        return ""

    def _extract_engage_counts(self, container) -> tuple[int, int, int]:
        """提取互动数据（点赞、收藏、评论）。

        小红书笔记详情页底部 engage-bar-style 内：
        - span.like-wrapper → 点赞数
        - span.collect-wrapper → 收藏数
        - span.chat-wrapper → 评论数
        """
        likes = collects = comments = 0
        try:
            counts = container.evaluate("""
                el => {
                    const bar = el.querySelector('.engage-bar-style, .engage-bar, .engage-bar-container');
                    if (!bar) return {};
                    const like = bar.querySelector('.like-wrapper');
                    const collect = bar.querySelector('.collect-wrapper');
                    const chat = bar.querySelector('.chat-wrapper');
                    return {
                        likes: like ? like.innerText.trim() : '',
                        collects: collect ? collect.innerText.trim() : '',
                        comments: chat ? chat.innerText.trim() : ''
                    };
                }
            """)
            if counts:
                likes = _parse_count(counts.get('likes', ''))
                collects = _parse_count(counts.get('collects', ''))
                comments = _parse_count(counts.get('comments', ''))
        except Exception as e:
            print(f"互动数据提取失败: {e}", file=sys.stderr)

        return likes, collects, comments

    def _scrape_note_cards(self, page: Page, limit: int) -> list[NoteSummary]:
        """从列表页提取笔记卡片信息。"""
        summaries = []
        scroll_count = 0
        max_scrolls = limit // 4 + 5  # 大约每屏 4 条

        while len(summaries) < limit and scroll_count < max_scrolls:
            cards = page.query_selector_all(
                'section.note-item, [class*="note-item"], a[class*="cover"]'
            )

            for card in cards:
                if len(summaries) >= limit:
                    break

                summary = NoteSummary()

                # 链接和 note_id
                href = ""
                preferred_links = [
                    card.query_selector('a.cover'),
                    card.query_selector('a[href*="/explore/"]'),
                    card.query_selector('a[href*="/user/profile/"]'),
                    card.query_selector('a'),
                ]
                for link in preferred_links:
                    if not link:
                        continue
                    candidate = (link.get_attribute('href') or "").strip()
                    if candidate:
                        href = candidate
                        break

                if href:
                    summary.note_id = _extract_note_id(href)
                    if not href.startswith("http"):
                        href = f"https://www.xiaohongshu.com{href}"
                    summary.source_url = href

                # 跳过已采集的
                if summary.note_id and any(s.note_id == summary.note_id for s in summaries):
                    continue

                # 标题
                title_el = card.query_selector('[class*="title"], .title, span')
                summary.title = (title_el.inner_text() if title_el else "").strip()

                # 作者
                author_el = card.query_selector('[class*="author"], .author, [class*="name"]')
                summary.author = (author_el.inner_text() if author_el else "").strip()

                # 封面图
                img = card.query_selector('img')
                summary.cover_url = (img.get_attribute('src') if img else "") or ""

                # 点赞数
                like_el = card.query_selector('[class*="like"] [class*="count"], .like-count')
                summary.likes = _parse_count(like_el.inner_text() if like_el else "")

                if summary.note_id:
                    summaries.append(summary)

            # 滚动加载更多
            page.evaluate("window.scrollBy(0, window.innerHeight)")
            BrowserEngine.random_delay(1.5, 3.0)
            scroll_count += 1

        return summaries

    def _scrape_images_ocr(self, page: Page, note: NoteData):
        """采集笔记中的图片并 OCR。

        小红书笔记图片在 swiper 轮播容器中，每张图在 .note-slider-img 里。
        需要通过点击下一张按钮逐张切换并截图。
        """
        container = page.query_selector('#noteContainer')
        if not container:
            return

        # 统计图片数量（通过 swiper 的 pagination 或直接数图片）
        # 先尝试从页面上获取图片总数（如 "1/5" 指示器）
        total_images = page.evaluate("""
            () => {
                // 方法1: 通过 swiper slides 数量（去重，排除 duplicate）
                const slides = document.querySelectorAll('#noteContainer .swiper-slide:not(.swiper-slide-duplicate)');
                if (slides.length > 0) return slides.length;
                // 方法2: 通过大图 img 数量
                const imgs = document.querySelectorAll('#noteContainer .note-slider-img img');
                if (imgs.length > 0) return imgs.length;
                return 0;
            }
        """)

        note.images_count = total_images

        if total_images == 0:
            return

        # 找到下一张按钮
        next_btn = container.query_selector(
            '.swiper-button-next, [class*="next-btn"], [class*="arrow-right"]'
        )

        for i in range(total_images):
            try:
                # 获取当前可见的图片
                visible_img = page.evaluate("""
                    () => {
                        const slide = document.querySelector('#noteContainer .swiper-slide-active img, #noteContainer .note-slider-img img');
                        if (slide && slide.naturalWidth > 100) return true;
                        return false;
                    }
                """)

                if not visible_img:
                    note.image_ocr.append("")
                    continue

                # 直接截图 active slide 内的 img 元素
                img_el = container.query_selector('.swiper-slide-active img')
                if img_el and img_el.is_visible():
                    screenshot = img_el.screenshot()
                    text = ocr_bytes(screenshot)
                    note.image_ocr.append(text)
                else:
                    note.image_ocr.append("")

                # 点击下一张（通过 JS 调用 swiper API 更可靠）
                if i < total_images - 1:
                    page.evaluate("""
                        () => {
                            const swiper = document.querySelector('#noteContainer .swiper');
                            if (swiper && swiper.swiper) {
                                swiper.swiper.slideNext();
                            } else {
                                const btn = document.querySelector('#noteContainer .swiper-button-next');
                                if (btn) btn.click();
                            }
                        }
                    """)
                    BrowserEngine.random_delay(0.5, 1.0)

            except Exception as e:
                note.image_ocr.append(f"[OCR 失败: {e}]")
                if note.capture_status == "success":
                    note.capture_status = "partial"
                    note.failure_reason = f"图片 {i+1} OCR 失败"
                print(f"图片 {i+1} OCR 失败: {e}", file=sys.stderr)

    def _extract_content(self, page: Page) -> str:
        """提取正文内容，处理折叠展开。"""
        # 尝试展开折叠的正文
        expand_btns = page.query_selector_all(
            '[class*="expand"], .show-more, [class*="unfold"], a:has-text("展开")'
        )
        for btn in expand_btns:
            try:
                btn.click()
                BrowserEngine.random_delay(0.3, 0.8)
            except Exception:
                pass

        # 提取正文
        selectors = [
            '#detail-desc',
            '.note-text',
            '.content',
            '[class*="desc"]',
            '[class*="content"]',
        ]

        for sel in selectors:
            el = page.query_selector(sel)
            if el:
                text = (el.inner_text() or "").strip()
                if text:
                    return text
        return ""

    def _extract_text(self, page: Page, selectors: list[str]) -> str:
        """尝试多个选择器提取文本。"""
        for sel in selectors:
            try:
                el = page.query_selector(sel)
                if el:
                    text = (el.inner_text() or "").strip()
                    if text:
                        return text
            except Exception:
                continue
        return ""

    def _extract_attr(self, page: Page, selectors: list[str], attr: str) -> str:
        """尝试多个选择器提取属性。"""
        for sel in selectors:
            try:
                el = page.query_selector(sel)
                if el:
                    val = el.get_attribute(attr)
                    if val:
                        return val
            except Exception:
                continue
        return ""

    def _extract_count(self, page: Page, selectors: list[str]) -> int:
        """尝试多个选择器提取数字。"""
        text = self._extract_text(page, selectors)
        return _parse_count(text)

    def _dismiss_popups(self, page: Page):
        """关闭可能弹出的登录/下载弹窗。"""
        popup_close_selectors = [
            '.login-modal button.close-icon',
            '.icon-btn-wrapper.close-button',
            '.reds-modal button.close-icon',
            '[class*="close-btn"]',
            '.close-button',
            'button[aria-label="close"]',
            '.login-mask .close',
        ]
        for sel in popup_close_selectors:
            try:
                btn = page.query_selector(sel)
                if btn and btn.is_visible():
                    btn.click()
                    BrowserEngine.random_delay(0.3, 0.5)
            except Exception:
                pass

    def _check_page_error(self, page: Page) -> bool:
        """检查页面是否有错误状态。"""
        error_patterns = ["内容已删除", "页面不存在", "404", "笔记不存在", "该内容已被删除"]
        try:
            body_text = page.inner_text("body")[:500]
            return any(p in body_text for p in error_patterns)
        except Exception:
            return False

    def _detect_status(self, page: Page) -> str:
        """检测页面具体状态。"""
        try:
            body_text = page.inner_text("body")[:500]
        except Exception:
            return "inaccessible"

        if "删除" in body_text or "不存在" in body_text:
            return "deleted"
        if "审核" in body_text:
            return "reviewing"
        if "404" in body_text:
            return "deleted"
        return "inaccessible"
