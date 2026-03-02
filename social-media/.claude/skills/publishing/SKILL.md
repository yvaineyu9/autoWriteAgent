---
name: publishing
description: 社媒发布排期和内容管理，数据存入 Project 目录
allowed-tools: Read, Bash, Write, Edit
argument-hint: "[操作指令]"
---

## 任务
管理社媒内容的发布排期，跟踪内容状态。所有排期数据存入仓库 `20_Project/` 目录。

## 功能

### 查看排期
- 读取 `20_Project/` 中与发布相关的项目文件
- 读取 `60_Published/social-media/` 中的已发布内容
- 列出待发布的内容及其计划发布时间

### 添加内容到排期
将生成好的内容添加到对应的 `20_Project/` 项目文件中：
- 平台
- 计划发布时间
- 内容摘要（wikilink 到 `60_Published/` 中的成品）
- 状态（待审核 / 待发布 / 已发布）

### 标记已发布
当内容实际发布后：
- 更新 `20_Project/` 中的状态为"已发布"
- 在 `10_Daily/YYYY-MM-DD.md` 追加发布记录

### 发布建议
根据目标平台的最佳发布时间，推荐发布时段。
