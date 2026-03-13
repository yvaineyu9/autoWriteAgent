#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
小红书发布助手 - 半自动化内容发布辅助工具

功能：
1. 从Markdown文件读取内容
2. 格式化为小红书风格
3. 一键复制到剪贴板
4. 可选打开小红书创作中心

使用：
    python xiaohongshu_publish_helper.py <markdown文件路径>
    python xiaohongshu_publish_helper.py --inbox  # 交互式选择Inbox文件

作者：Tars
创建时间：2025-03-13
"""

import sys
import os
import re
import json
import argparse
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Tuple

# 配置路径
WORKSPACE_DIR = Path.home() / "claude-workflows"
INBOX_DIR = WORKSPACE_DIR / "00_Inbox"
SECRETS_DIR = WORKSPACE_DIR / ".secrets"

# 小红书限制
MAX_TITLE_LENGTH = 20
MAX_CONTENT_LENGTH = 1000  # 小红书正文建议长度
RECOMMENDED_TAGS = 3

# 敏感词列表（简化版，实际可扩展）
SENSITIVE_WORDS = [
    "最", "第一", "国家级", "绝对", "永不", "100%",
    "微信", "支付宝", "转账", "扫码", "加我",
    "假货", "仿品", "山寨", "盗版",
]


class Colors:
    """终端颜色"""
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'


def print_header(title: str):
    """打印标题"""
    print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*50}{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.CYAN}  {title}{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.CYAN}{'='*50}{Colors.ENDC}\n")


def print_section(title: str, content: str, color: str = Colors.GREEN):
    """打印章节"""
    print(f"\n{Colors.BOLD}{color}📌 {title}{Colors.ENDC}")
    print(f"{content}")


def parse_frontmatter(content: str) -> Tuple[Dict, str]:
    """解析Markdown Frontmatter"""
    frontmatter = {}
    body = content
    
    if content.startswith('---'):
        parts = content.split('---', 2)
        if len(parts) >= 3:
            try:
                frontmatter = json.loads(parts[1]) if parts[1].strip().startswith('{') else {}
                if not frontmatter:
                    # 尝试YAML格式
                    import yaml
                    frontmatter = yaml.safe_load(parts[1])
            except:
                pass
            body = parts[2].strip()
    
    return frontmatter, body


def extract_title(body: str, max_length: int = MAX_TITLE_LENGTH) -> str:
    """从正文提取或生成标题"""
    lines = body.strip().split('\n')
    
    # 尝试找第一行作为标题
    for line in lines:
        line = line.strip().strip('#').strip()
        if line and len(line) <= max_length:
            return line
        elif line and len(line) > max_length:
            return line[:max_length-1] + "…"
    
    # 生成默认标题
    return "分享今日心得✨"


def format_xiaohongshu_content(body: str) -> str:
    """格式化为小红书风格"""
    # 移除Markdown标题标记
    body = re.sub(r'^#+\s*', '', body, flags=re.MULTILINE)
    
    # 添加段落间距
    paragraphs = body.split('\n\n')
    formatted = []
    
    for p in paragraphs:
        p = p.strip()
        if not p:
            continue
        
        # 如果是列表，添加emoji
        if p.startswith('- ') or p.startswith('* '):
            p = p.replace('- ', '• ').replace('* ', '• ')
        
        formatted.append(p)
    
    return '\n\n'.join(formatted)


def extract_tags(body: str, frontmatter: Dict) -> List[str]:
    """提取标签"""
    tags = []
    
    # 从frontmatter获取
    if 'tags' in frontmatter and isinstance(frontmatter['tags'], list):
        tags = frontmatter['tags'][:RECOMMENDED_TAGS]
    
    # 从正文提取关键词作为标签
    if len(tags) < RECOMMENDED_TAGS:
        # 简单关键词提取（可优化为NLP）
        keywords = [
            ("星座", "#星座运势"), ("占星", "#占星"),
            ("AI", "#AI"), ("科技", "#科技"),
            ("读书", "#读书笔记"), ("成长", "#个人成长"),
            ("美食", "#美食"), ("旅行", "#旅行"),
            ("穿搭", "#穿搭"), ("美妆", "#美妆"),
        ]
        
        for keyword, tag in keywords:
            if keyword in body and tag not in tags:
                tags.append(tag)
                if len(tags) >= RECOMMENDED_TAGS:
                    break
    
    # 补充通用标签
    while len(tags) < RECOMMENDED_TAGS:
        tags.append("#生活记录")
        break
    
    return tags


def check_sensitive_words(text: str) -> List[str]:
    """检查敏感词"""
    found = []
    for word in SENSITIVE_WORDS:
        if word in text:
            found.append(word)
    return found


def copy_to_clipboard(text: str) -> bool:
    """复制到剪贴板"""
    try:
        import subprocess
        
        # macOS
        if sys.platform == 'darwin':
            process = subprocess.Popen(['pbcopy'], stdin=subprocess.PIPE)
            process.communicate(text.encode('utf-8'))
            return True
        
        # Linux
        elif sys.platform.startswith('linux'):
            process = subprocess.Popen(['xclip', '-selection', 'clipboard'], 
                                      stdin=subprocess.PIPE)
            process.communicate(text.encode('utf-8'))
            return True
        
        # Windows
        elif sys.platform == 'win32':
            import win32clipboard
            win32clipboard.OpenClipboard()
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardText(text)
            win32clipboard.CloseClipboard()
            return True
            
    except Exception as e:
        print(f"{Colors.YELLOW}⚠️  复制失败: {e}{Colors.ENDC}")
        return False


def open_creator_center():
    """打开小红书创作者中心"""
    url = "https://creator.xiaohongshu.com/creator/home"
    
    try:
        import subprocess
        
        if sys.platform == 'darwin':
            subprocess.run(['open', url])
        elif sys.platform.startswith('linux'):
            subprocess.run(['xdg-open', url])
        elif sys.platform == 'win32':
            subprocess.run(['start', url], shell=True)
        
        return True
    except Exception as e:
        print(f"{Colors.YELLOW}⚠️  打开网页失败: {e}{Colors.ENDC}")
        return False


def list_inbox_files() -> List[Path]:
    """列出Inbox中的Markdown文件"""
    if not INBOX_DIR.exists():
        return []
    
    files = list(INBOX_DIR.glob("*.md"))
    files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
    return files


def interactive_select_file() -> Optional[Path]:
    """交互式选择文件"""
    files = list_inbox_files()
    
    if not files:
        print(f"{Colors.YELLOW}⚠️  Inbox中没有Markdown文件{Colors.ENDC}")
        return None
    
    print(f"\n{Colors.BOLD}📁 Inbox文件列表：{Colors.ENDC}\n")
    
    for i, f in enumerate(files[:10], 1):
        mtime = datetime.fromtimestamp(f.stat().st_mtime)
        print(f"  {Colors.CYAN}[{i}]{Colors.ENDC} {f.name} ({mtime.strftime('%m-%d %H:%M')})")
    
    print(f"  {Colors.CYAN}[0]{Colors.ENDC} 取消")
    
    try:
        choice = input(f"\n{Colors.BOLD}请选择文件编号: {Colors.ENDC}").strip()
        idx = int(choice) - 1
        
        if choice == '0':
            return None
        elif 0 <= idx < len(files):
            return files[idx]
        else:
            print(f"{Colors.RED}❌ 无效选择{Colors.ENDC}")
            return None
            
    except ValueError:
        print(f"{Colors.RED}❌ 请输入数字{Colors.ENDC}")
        return None


def process_markdown(file_path: Path) -> Optional[Dict]:
    """处理Markdown文件"""
    try:
        content = file_path.read_text(encoding='utf-8')
    except Exception as e:
        print(f"{Colors.RED}❌ 读取文件失败: {e}{Colors.ENDC}")
        return None
    
    # 解析Frontmatter
    frontmatter, body = parse_frontmatter(content)
    
    # 提取标题
    title = frontmatter.get('title', '') or extract_title(body)
    
    # 格式化正文
    formatted_body = format_xiaohongshu_content(body)
    
    # 提取标签
    tags = extract_tags(body, frontmatter)
    
    # 检查敏感词
    sensitive = check_sensitive_words(title + formatted_body)
    
    return {
        'title': title,
        'body': formatted_body,
        'tags': tags,
        'sensitive_words': sensitive,
        'source': str(file_path)
    }


def display_result(result: Dict):
    """显示处理结果"""
    print_header("📝 小红书发布助手")
    
    # 标题
    print_section("标题", result['title'], Colors.YELLOW)
    print(f"{Colors.CYAN}   字数: {len(result['title'])}/{MAX_TITLE_LENGTH}{Colors.ENDC}")
    
    # 正文预览
    body_preview = result['body'][:200] + "..." if len(result['body']) > 200 else result['body']
    print_section("正文预览", body_preview, Colors.GREEN)
    print(f"{Colors.CYAN}   总字数: {len(result['body'])}{Colors.ENDC}")
    
    # 标签
    tags_text = " ".join(result['tags'])
    print_section("推荐标签", tags_text, Colors.BLUE)
    
    # 敏感词警告
    if result['sensitive_words']:
        words = ", ".join(result['sensitive_words'])
        print(f"\n{Colors.RED}⚠️  检测到敏感词: {words}{Colors.ENDC}")
        print(f"{Colors.YELLOW}   建议修改后再发布{Colors.ENDC}")
    else:
        print(f"\n{Colors.GREEN}✅ 未发现敏感词{Colors.ENDC}")


def interactive_menu(result: Dict) -> bool:
    """交互式菜单"""
    while True:
        print(f"\n{Colors.BOLD}{Colors.CYAN}📋 操作选项：{Colors.ENDC}")
        print(f"  {Colors.GREEN}[1]{Colors.ENDC} 复制全部内容（标题+正文+标签）")
        print(f"  {Colors.GREEN}[2]{Colors.ENDC} 仅复制标题")
        print(f"  {Colors.GREEN}[3]{Colors.ENDC} 仅复制正文")
        print(f"  {Colors.GREEN}[4]{Colors.ENDC} 打开小红书创作中心")
        print(f"  {Colors.GREEN}[5]{Colors.ENDC} 重新选择文件")
        print(f"  {Colors.YELLOW}[0]{Colors.ENDC} 退出")
        
        choice = input(f"\n{Colors.BOLD}请选择操作: {Colors.ENDC}").strip()
        
        if choice == '1':
            full_content = f"{result['title']}\n\n{result['body']}\n\n{' '.join(result['tags'])}"
            if copy_to_clipboard(full_content):
                print(f"{Colors.GREEN}✅ 已复制全部内容到剪贴板{Colors.ENDC}")
                print(f"{Colors.YELLOW}💡 提示: 请在小红书中粘贴并上传配图{Colors.ENDC}")
        
        elif choice == '2':
            if copy_to_clipboard(result['title']):
                print(f"{Colors.GREEN}✅ 已复制标题到剪贴板{Colors.ENDC}")
        
        elif choice == '3':
            if copy_to_clipboard(result['body']):
                print(f"{Colors.GREEN}✅ 已复制正文到剪贴板{Colors.ENDC}")
        
        elif choice == '4':
            if open_creator_center():
                print(f"{Colors.GREEN}✅ 已打开小红书创作中心{Colors.ENDC}")
                print(f"{Colors.YELLOW}💡 请登录后点击「发布笔记」{Colors.ENDC}")
        
        elif choice == '5':
            return True  # 重新选择
        
        elif choice == '0':
            return False  # 退出
        
        else:
            print(f"{Colors.RED}❌ 无效选择{Colors.ENDC}")


def main():
    parser = argparse.ArgumentParser(
        description='小红书发布助手 - 半自动化内容发布辅助工具'
    )
    parser.add_argument('file', nargs='?', help='Markdown文件路径')
    parser.add_argument('--inbox', '-i', action='store_true', 
                       help='从Inbox交互式选择文件')
    parser.add_argument('--copy', '-c', action='store_true',
                       help='自动复制到剪贴板（非交互模式）')
    parser.add_argument('--open', '-o', action='store_true',
                       help='自动打开小红书创作中心')
    
    args = parser.parse_args()
    
    # 确定文件路径
    file_path = None
    
    if args.inbox:
        file_path = interactive_select_file()
        if not file_path:
            sys.exit(0)
    elif args.file:
        file_path = Path(args.file)
        if not file_path.exists():
            # 尝试在Inbox中查找
            inbox_file = INBOX_DIR / args.file
            if inbox_file.exists():
                file_path = inbox_file
            else:
                print(f"{Colors.RED}❌ 文件不存在: {args.file}{Colors.ENDC}")
                sys.exit(1)
    else:
        # 默认交互模式
        file_path = interactive_select_file()
        if not file_path:
            sys.exit(0)
    
    # 处理文件
    result = process_markdown(file_path)
    if not result:
        sys.exit(1)
    
    # 显示结果
    display_result(result)
    
    # 非交互模式
    if args.copy:
        full_content = f"{result['title']}\n\n{result['body']}\n\n{' '.join(result['tags'])}"
        if copy_to_clipboard(full_content):
            print(f"{Colors.GREEN}✅ 已复制到剪贴板{Colors.ENDC}")
    
    if args.open:
        if open_creator_center():
            print(f"{Colors.GREEN}✅ 已打开小红书创作中心{Colors.ENDC}")
    
    # 交互模式
    if not args.copy and not args.open:
        while interactive_menu(result):
            # 重新选择文件
            file_path = interactive_select_file()
            if not file_path:
                break
            result = process_markdown(file_path)
            if result:
                display_result(result)
    
    print(f"\n{Colors.GREEN}👋 感谢使用小红书发布助手！{Colors.ENDC}\n")


if __name__ == '__main__':
    main()
