# 一键发送排版图到飞书群 — 设计

日期：2026-04-10
状态：设计定版，待实现

## 目标

在 Web UI 的生图结果面板里加一个按钮，点击后把该条 content 已生成的所有排版图 (`data/content/typeset/{content_id}/page-*.jpg`) 作为一条富文本消息发到固定的飞书群。

## 范围

- 范围内
  - 单个固定群（硬编码 chat_id）
  - 只发图片，无标题/正文文字/@人
  - 按序发送生成的全部 page-*.jpg
- 范围外 (YAGNI)
  - 多群选择
  - 发送历史入库、去重、重试队列、定时
  - Webhook 方案
  - 正文摘要、@人、平台标签、封面单独突出

## 凭据与安全

- 三个敏感字段放 `/Users/moonvision/autoWriteAgent/.env`
  - `FEISHU_APP_ID`
  - `FEISHU_APP_SECRET`
  - `FEISHU_CHAT_ID`
- `.env` 已在 `.gitignore`，**不 rsync**，只手工放到 Mac Mini
- 飞书自建应用需开权限：`im:message:send_as_bot`、`im:resource`
- 应用对应的机器人必须已加到目标群，否则发消息 API 返回 230001

## 组件

### 后端

#### `ui/backend/services/feishu.py`（新建）

纯粹的飞书 API 封装。三个函数：

- `_get_tenant_access_token() -> str`
  - `POST https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal`
  - 带进程内缓存，有效期用返回的 `expire` 字段减 60s
- `upload_image(path: str) -> str`
  - `POST /open-apis/im/v1/images` (multipart, `image_type=message`)
  - 返回 `image_key`
- `send_post_message(chat_id: str, image_keys: list[str]) -> str`
  - `POST /open-apis/im/v1/messages?receive_id_type=chat_id`
  - 消息体：`msg_type=post`，`content.post.zh_cn` 结构
  - `title` 空字符串
  - `content` 是一个列表，每一行是一个只包含 `{tag: "img", image_key: key}` 的段落
  - 返回 `message_id`

所有失败场景都 raise，由 router 层捕获转 HTTPException。

#### `ui/backend/routers/feishu.py`（新建）

```
POST /api/contents/{content_id}/send-to-feishu
```

流程：
1. 读 `FEISHU_CHAT_ID` / `APP_ID` / `APP_SECRET`，任一缺失 → 500 + 明确提示
2. 扫 `data/content/typeset/{content_id}/` 里所有 `page-*.jpg|png`，按文件名排序
3. 若为空 → 404 `no generated images for this content`
4. 依次 `upload_image` 拿到 `image_keys`
5. `send_post_message(chat_id, image_keys)`
6. 成功返回 `{ok: true, message_id, image_count}`

错误响应：
- 凭据缺失：500 `"Feishu credentials not configured"`
- 无图：404 `"no generated images"`
- API 调用失败（token / upload / send）：502 `"feishu API: {code} {msg}"`

#### `ui/backend/main.py`

- 顶部加 20 行 inline `.env` loader，从 `PROJECT_ROOT/.env` 读，`os.environ.setdefault` 不覆盖已有
- `include_router(feishu.router, prefix="/api")`

### 前端

#### `ui/frontend/src/views/ContentsView.vue`

- `showTypeset=true` 的面板里，`typesetImages` 有内容时在底部加一个按钮"一键发飞书群"
- 新 ref：`sendingFeishu: boolean`, `feishuResult: {ok: boolean, message: string} | null`
- `doSendFeishu()` 方法：
  - 调 `api.sendToFeishu(typesetContentId.value)`
  - 按钮禁用 + 文字变 "发送中..."
  - 成功：提示 "已发送 ✓"（带 message_id 前 8 位）
  - 失败：提示 "失败：{error detail}"
- **不做**重复点击拦截（按钮只在非 sending 时可点，但点了就点了）

#### `ui/frontend/src/api/client.ts`

```ts
sendToFeishu: (content_id: string) =>
  post<{ ok: boolean; message_id: string; image_count: number }>(
    `/contents/${encodeURIComponent(content_id)}/send-to-feishu`,
    {},
  ),
```

## 数据流

```
[Browser: 点按钮]
    ↓
POST /api/contents/{id}/send-to-feishu
    ↓
[Backend feishu router]
    ↓ 1. check env + list files
    ↓ 2. get_tenant_access_token()
    ↓ 3. for each file: upload_image → image_key
    ↓ 4. send_post_message(chat_id, [image_keys])
    ↓
return {ok, message_id, image_count}
    ↓
[Browser: 显示成功/失败]
```

## 错误处理

| 层 | 场景 | 返回 |
|---|---|---|
| router | 凭据未配 | 500 `"Feishu credentials not configured"` |
| router | 无生成图片 | 404 `"no generated images"` |
| service | token 拿不到 | raise → router 转 502 |
| service | 单张图上传失败 | raise，跳过后续 → 502 |
| service | 发消息失败 | raise → 502 |

全部通过标准 HTTPException + 前端现有的 `post<T>` error handler 展示。

## 测试

手动：
1. 生图 → 点发送 → 群里收到一条 post 消息，包含所有 N 张图
2. 删掉 `.env` 里 `FEISHU_APP_ID` → 点发送 → 提示 "Feishu credentials not configured"
3. 删掉 typeset 目录 → 点发送 → 提示 "no generated images"
4. 故意改错 app_secret → 点发送 → 提示 `feishu API: 99991663 app ticket is invalid` 之类

## 实现检查清单

- [ ] Mac Mini 上放 `.env`（手工 scp，不进 rsync）
- [ ] `main.py` 加 .env loader
- [ ] 新建 `services/feishu.py`
- [ ] 新建 `routers/feishu.py`
- [ ] `main.py` 挂 router
- [ ] `ContentsView.vue` 加按钮 + 状态
- [ ] `api/client.ts` 加 `sendToFeishu`
- [ ] 手动全链路测一次

## 非决定事项

无。全部问题已拍板。
