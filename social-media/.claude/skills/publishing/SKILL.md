---
name: publishing
description: 社媒发布管理 — 多账号分发、状态追踪、数据采集，基于 distribution 工具
allowed-tools: Read, Bash, Write, Edit
argument-hint: "[操作指令]"
---

## 任务

管理社媒内容的多账号分发、发布状态追踪和数据采集。数据存储在 `70_Distribution/distribution.db`（SQLite）。

统一约定见 [../../CONVENTIONS.md](../../CONVENTIONS.md)。

## 工具路径

所有 CLI 工具位于 `social-media/tools/distribution/`，运行时需先 `cd` 到该目录：

```bash
cd <PROJECT_ROOT>/social-media/tools/distribution
```

## 功能

### 1. 账号管理

```bash
# 查看所有账号
python3 publish.py accounts

# 添加账号（一个人设可绑定多个账号）
python3 publish.py add-account --persona chongxiaoyu --name "账号昵称" --account-id "小红书号"
python3 publish.py add-account --persona yuejian --platform xiaohongshu --name "月见主号"
```

人设 ID：`chongxiaoyu`（虫小宇）、`yuejian`（月见）

### 2. 创建发布任务

将内容分发到人设下所有活跃账号：

```bash
# 为虫小宇的所有账号创建发布任务
python3 publish.py create --persona chongxiaoyu --title "文章标题" \
  --content-path "60_Published/social-media/chongxiaoyu/xiaohongshu/2026-03-13_标题/content.md"

# 指定发布时间
python3 publish.py create --persona yuejian --title "标题" --scheduled-at "2026-03-14 20:00"
```

### 3. 标记已发布

手动发布到平台后，回来标记：

```bash
python3 publish.py done --id 1 --url "https://www.xiaohongshu.com/explore/xxx"
```

### 4. 查看发布状态

```bash
# 查看所有
python3 publish.py list

# 按人设筛选
python3 publish.py list --persona chongxiaoyu

# 按状态筛选（draft / published / tracking / archived）
python3 publish.py list --status draft
```

### 5. 数据采集

```bash
# 查看哪些帖子需要采集数据（发布后 1/3/7 天）
python3 metrics.py remind

# 录入数据
python3 metrics.py record --pub-id 1 --views 500 --likes 30 --collects 15 --comments 5 --shares 2

# 查看数据汇总
python3 metrics.py query
python3 metrics.py query --persona chongxiaoyu

# 查看某条帖子的数据变化
python3 metrics.py history --pub-id 1
```

## 工作流

```
内容工厂产出 → 60_Published/social-media/<persona>/<platform>/.../content.md
    ↓
/publishing create（为人设下所有账号创建任务）
    ↓
手动上传到小红书创作者中心 → 手动点击发布
    ↓
/publishing done（录入发布链接）
    ↓
OpenClaw 定时任务触发 → metrics.py remind（提醒采集）
    ↓
手动浏览器查看数据 → metrics.py record（录入数据）
    ↓
metrics.py query / history（查看分析）
```

## 状态流转

```
draft → published → tracking → archived
  ↑        ↑           ↑          ↑
创建任务  标记发布   首次录入数据  7天后自动归档
```

## 注意

- 发布操作始终由人工完成，不自动调用平台 API
- 数据采集通过浏览器手动查看后录入
- OpenClaw 定时任务只负责提醒，不负责执行
- `publishing` 负责发布记录与数据追踪，不负责内容选稿和改稿
- 历史旧路径内容应迁移到 `60_Published/social-media/...` 后再作为正式发布输入
