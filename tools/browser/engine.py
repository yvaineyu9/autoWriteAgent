#!/usr/bin/env python3
"""
Playwright 浏览器引擎：连接已有 Chrome 实例。

使用前需以 debug 模式启动 Chrome：
  open -a "Google Chrome" --args --remote-debugging-port=9222

用法：
  from browser.engine import BrowserEngine

  engine = BrowserEngine()
  engine.connect()
  page = engine.new_page()
  page.goto("https://www.xiaohongshu.com")
  engine.close()
"""

import random
import time
import sys

from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page


class BrowserEngine:
    """Playwright 引擎，复用已有 Chrome 的登录态。"""

    def __init__(self, port: int = 9222):
        self.port = port
        self._playwright = None
        self._browser: Browser = None
        self._context: BrowserContext = None

    def connect(self):
        """连接到已运行的 Chrome 实例。"""
        self._playwright = sync_playwright().start()
        try:
            self._browser = self._playwright.chromium.connect_over_cdp(
                f"http://localhost:{self.port}"
            )
        except Exception as e:
            self._playwright.stop()
            self._playwright = None
            raise ConnectionError(
                f"无法连接 Chrome (port={self.port})。\n"
                f"请先启动 Chrome debug 模式：\n"
                f'  /Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome '
                f'--remote-debugging-port={self.port}\n'
                f"原始错误: {e}"
            ) from e

        # 复用已有 context（保留登录态）
        contexts = self._browser.contexts
        if contexts:
            self._context = contexts[0]
        else:
            self._context = self._browser.new_context()

        print(f"已连接 Chrome (port={self.port})", file=sys.stderr)

    def new_page(self) -> Page:
        """在已有 context 中新建标签页。"""
        if not self._context:
            raise RuntimeError("未连接浏览器，请先调用 connect()")
        return self._context.new_page()

    def close(self):
        """断开连接（不关闭 Chrome）。"""
        if self._playwright:
            self._playwright.stop()
            self._playwright = None
            self._browser = None
            self._context = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *args):
        self.close()

    @staticmethod
    def random_delay(min_sec: float = 1.0, max_sec: float = 3.0):
        """随机等待，模拟人类操作节奏。"""
        delay = random.uniform(min_sec, max_sec)
        time.sleep(delay)

    @staticmethod
    def safe_goto(page: Page, url: str, timeout: int = 30000, wait_until: str = "domcontentloaded"):
        """带重试的页面导航。

        Args:
            page: Playwright Page
            url: 目标 URL
            timeout: 超时毫秒
            wait_until: 等待事件类型
        """
        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                page.goto(url, timeout=timeout, wait_until=wait_until)
                BrowserEngine.random_delay(1.5, 3.0)
                return
            except Exception as e:
                if attempt < max_retries:
                    print(f"导航失败 (重试 {attempt + 1}/{max_retries}): {e}", file=sys.stderr)
                    BrowserEngine.random_delay(2.0, 5.0)
                else:
                    raise
