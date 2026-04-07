# /publish <子命令>

发布后的监控与数据管理。选文和发布流程已合并到 /select。

## 数据采集规则
- 所有数据采集只在账号主页完成，**不进入详情页**，降低风险。
- 只采集**点赞数**（来自账号页卡片），不采集收藏、评论。
- 不保存 `post_url`（小红书链接），避免不必要的数据存储。
- 如果某条库内记录当前没有在账号页匹配到，不要编造映射关系；保留原记录，并明确标记平台状态。
- 回填目标是"真实、可解释"，不是"尽量把所有东西都匹配上"。

## /publish list [--status <status>]
  python3 tools/publish.py list [--status <status>]

## /publish sync-account <persona> [--platform xiaohongshu] [--limit N]
  python3 tools/monitor.py sync-account --persona <persona> [--platform xiaohongshu] [--limit N]
  对齐账号页发布状态 + 采集卡片点赞数，一条命令完成。

## /publish remind
  python3 tools/monitor.py remind

## /publish metrics <pub_id> --likes N
  python3 tools/metrics.py record --pub-id <pub_id> --likes N
  手工补录点赞数，视为兜底。
