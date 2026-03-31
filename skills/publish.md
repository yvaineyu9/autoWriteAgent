# /publish <子命令>

发布管理：查看、标记、采集数据。

## /publish list [--status <status>]
  python3 tools/publish.py list [--status <status>]

## /publish done <pub_id> --url <url>
  python3 tools/publish.py done --id <pub_id> --url "<url>"

## /publish metrics <pub_id> --views N --likes N --collects N --comments N --shares N
  python3 tools/metrics.py record --pub-id <pub_id> --views N --likes N --collects N --comments N --shares N

## /publish remind
  python3 tools/metrics.py remind
