#!/usr/bin/env python3
"""
小红书文章批量抓取脚本
"""
import json
import time
import re
import os
from datetime import datetime
from playwright.sync_api import sync_playwright

# 文章链接列表
articles = [
    # 星宿关系类
    {"url": "https://www.xiaohongshu.com/discovery/item/68ea30c70000000004017329", "title": "1分钟入门星宿", "likes": "3735"},
    {"url": "https://www.xiaohongshu.com/discovery/item/69460b9f000000001e0380c1", "title": "14种星宿关系谁更爱谁", "likes": "2560"},
    {"url": "https://www.xiaohongshu.com/discovery/item/67b35238000000001800a35a", "title": "各类星宿食用指南", "likes": "2407"},
    {"url": "https://www.xiaohongshu.com/discovery/item/6951e6c7000000001e022d06", "title": "星宿关系-安坏", "likes": "1057"},
    # 合盘类
    {"url": "https://www.xiaohongshu.com/discovery/item/62d894b40000000001024614", "title": "一篇笔记弄懂各种合盘", "likes": "4418"},
    {"url": "https://www.xiaohongshu.com/discovery/item/6763d864000000001300e9f1", "title": "月亮星座进阶分享", "likes": "1347"},
    {"url": "https://www.xiaohongshu.com/discovery/item/639af48f000000001f0103a9", "title": "婚恋系列合盘", "likes": "3804"},
    {"url": "https://www.xiaohongshu.com/discovery/item/66efdeb6000000000c019ccc", "title": "合盘中土冥业力", "likes": "1088"},
    # 亲密关系类
    {"url": "https://www.xiaohongshu.com/discovery/item/69987808000000001b01dd88", "title": "真正的亲密关系从愿意聊感受开始", "likes": "5675"},
    {"url": "https://www.xiaohongshu.com/discovery/item/698e29f9000000000c035c11", "title": "为什么你会陷入混乱型依恋", "likes": "10000"},
    {"url": "https://www.xiaohongshu.com/discovery/item/69590f3e000000002202c0c0", "title": "长期关系降低对方恶意", "likes": "4708"},
    {"url": "https://www.xiaohongshu.com/discovery/item/69789534000000000b01122d", "title": "ta并不爱你只是爱你的功能性", "likes": "4042"},
]

VAULT_PATH = os.path.expanduser(os.getenv("VAULT_PATH", "~/Desktop/vault"))
OUTPUT_DIR = os.path.join(VAULT_PATH, "00_Inbox")

def extract_id_from_url(url):
    """从URL提取文章ID"""
    match = re.search(r'/item/([a-z0-9]+)', url)
    return match.group(1) if match else "unknown"

def sanitize_filename(title):
    """清理文件名"""
    # 移除非法字符，限制长度
    title = re.sub(r'[\\/*?"<>|:]', '', title)
    return title[:30]  # 限制长度

def scrape_xiaohongshu(url, title, likes):
    """抓取单篇文章"""
    article_id = extract_id_from_url(url)
    
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp("http://127.0.0.1:18800")
        context = browser.contexts[0] if browser.contexts else browser.new_context()
        page = context.new_page()
        
        try:
            print(f"正在抓取: {title}...")
            page.goto(url, wait_until="networkidle", timeout=30000)
            
            # 等待页面加载
            time.sleep(3)
            
            # 尝试提取正文内容
            content_selectors = [
                '.note-content', 
                '.content',
                '.note-text',
                '[class*="content"]',
                '[class*="desc"]',
                'article'
            ]
            
            content = ""
            for selector in content_selectors:
                try:
                    element = page.query_selector(selector)
                    if element:
                        content = element.inner_text()
                        if len(content) > 50:
                            break
                except:
                    continue
            
            # 如果上面的选择器都没找到，尝试更通用的方法
            if not content:
                # 获取页面所有文本
                content = page.inner_text('body')
                # 过滤掉导航、footer等
                lines = [line.strip() for line in content.split('\n') if line.strip()]
                content = '\n'.join(lines)
            
            # 提取作者
            author = "未知作者"
            try:
                author_elem = page.query_selector('.author-name, [class*="author"], [class*="nickname"]')
                if author_elem:
                    author = author_elem.inner_text().strip()
            except:
                pass
            
            page.close()
            
            return {
                "success": True,
                "id": article_id,
                "title": title,
                "author": author,
                "likes": likes,
                "url": url,
                "content": content
            }
            
        except Exception as e:
            page.close()
            return {
                "success": False,
                "id": article_id,
                "title": title,
                "url": url,
                "error": str(e)
            }

def save_to_markdown(article):
    """保存为Markdown格式"""
    safe_title = sanitize_filename(article['title'])
    filename = f"小红书_{article['id']}_{safe_title}.md"
    filepath = os.path.join(OUTPUT_DIR, filename)
    
    md_content = f"""# {article['title']}

> **来源**: 小红书  
> **作者**: {article['author']}  
> **点赞**: {article['likes']}  
> **链接**: {article['url']}  
> **抓取时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

---

{article['content']}

---

*从灵感库自动采集*
"""
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(md_content)
    
    return filepath

def main():
    results = {"success": [], "failed": []}
    
    for i, article in enumerate(articles):
        print(f"\n[{i+1}/{len(articles)}] 处理中...")
        
        result = scrape_xiaohongshu(article['url'], article['title'], article['likes'])
        
        if result['success']:
            filepath = save_to_markdown(result)
            results["success"].append({
                "id": result['id'],
                "title": result['title'],
                "filepath": filepath
            })
            print(f"  ✓ 成功保存: {filepath}")
        else:
            results["failed"].append({
                "id": result['id'],
                "title": result['title'],
                "error": result.get('error', 'Unknown error')
            })
            print(f"  ✗ 失败: {result.get('error', 'Unknown error')}")
        
        # 间隔5-10秒，避免风控
        if i < len(articles) - 1:
            delay = 5 + (i % 3)  # 5, 6, 7 秒循环
            print(f"  等待 {delay} 秒...")
            time.sleep(delay)
    
    # 输出结果摘要
    print("\n" + "="*50)
    print("抓取完成！")
    print(f"成功: {len(results['success'])} 篇")
    print(f"失败: {len(results['failed'])} 篇")
    
    if results['failed']:
        print("\n失败列表:")
        for item in results['failed']:
            print(f"  - {item['title']}: {item['error']}")
    
    # 保存结果JSON
    result_file = os.path.join(OUTPUT_DIR, f"xhs_crawl_result_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    with open(result_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n结果已保存: {result_file}")

if __name__ == "__main__":
    main()
