#!/usr/bin/env python3
"""
OCR 模块：调用 macOS Apple Vision 识别图片中的文字。

用法：
  from browser.ocr import ocr_image, ocr_bytes

  text = ocr_image("/path/to/image.png")
  text = ocr_bytes(screenshot_bytes)
"""

import os
import subprocess
import sys
import tempfile

# Swift 脚本路径
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_SWIFT_SCRIPT = os.path.join(_SCRIPT_DIR, "ocr_vision.swift")

# 编译后的二进制缓存路径
_COMPILED_BIN = os.path.join(_SCRIPT_DIR, ".ocr_vision_bin")


def _ensure_compiled():
    """编译 Swift 脚本为二进制，避免每次调用都编译。"""
    if os.path.isfile(_COMPILED_BIN):
        # 检查是否需要重新编译（源文件更新）
        if os.path.getmtime(_COMPILED_BIN) >= os.path.getmtime(_SWIFT_SCRIPT):
            return _COMPILED_BIN

    print("首次运行，编译 OCR 工具...", file=sys.stderr)
    result = subprocess.run(
        ["swiftc", _SWIFT_SCRIPT, "-o", _COMPILED_BIN, "-O"],
        capture_output=True, text=True, timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(f"编译 Swift OCR 失败:\n{result.stderr}")
    print("OCR 工具编译完成", file=sys.stderr)
    return _COMPILED_BIN


def ocr_image(image_path: str, timeout: int = 30) -> str:
    """识别图片文件中的文字。

    Args:
        image_path: 图片文件路径
        timeout: 超时秒数

    Returns:
        识别到的文字（多行），失败返回空字符串
    """
    binary = _ensure_compiled()

    try:
        result = subprocess.run(
            [binary, image_path],
            capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        print(f"OCR 超时: {image_path}", file=sys.stderr)
        return ""

    if result.returncode not in (0,):
        print(f"OCR 失败 (exit={result.returncode}): {result.stderr.strip()}", file=sys.stderr)
        return ""

    return result.stdout.strip()


def ocr_bytes(image_bytes: bytes, timeout: int = 30) -> str:
    """识别内存中图片的文字（通过 stdin 传递）。

    Args:
        image_bytes: PNG/JPEG 图片的字节数据
        timeout: 超时秒数

    Returns:
        识别到的文字（多行），失败返回空字符串
    """
    binary = _ensure_compiled()

    try:
        result = subprocess.run(
            [binary, "-"],
            input=image_bytes,
            capture_output=True, text=False, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        print("OCR 超时 (stdin)", file=sys.stderr)
        return ""

    if result.returncode not in (0,):
        stderr_text = result.stderr.decode("utf-8", errors="replace").strip()
        print(f"OCR 失败 (exit={result.returncode}): {stderr_text}", file=sys.stderr)
        return ""

    return result.stdout.decode("utf-8", errors="replace").strip()


def ocr_screenshot(page, selector: str = None, timeout: int = 30) -> str:
    """对 Playwright 页面或元素截图并 OCR。

    Args:
        page: Playwright Page 或 ElementHandle
        selector: 可选 CSS 选择器，指定截图区域
        timeout: OCR 超时秒数

    Returns:
        识别到的文字
    """
    if selector:
        element = page.query_selector(selector)
        if not element:
            print(f"元素不存在: {selector}", file=sys.stderr)
            return ""
        screenshot_bytes = element.screenshot()
    else:
        screenshot_bytes = page.screenshot()

    return ocr_bytes(screenshot_bytes, timeout=timeout)


# CLI 测试入口
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python ocr.py <image_path>", file=sys.stderr)
        sys.exit(1)

    text = ocr_image(sys.argv[1])
    if text:
        print(text)
    else:
        print("未识别到文字", file=sys.stderr)
        sys.exit(2)
