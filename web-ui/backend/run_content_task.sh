#!/bin/zsh
set -euo pipefail

persona=""
platform=""
input_text=""
input_path=""
instruction=""
output_file=""
format="markdown"

emit_event() {
  local event="$1"
  local message="$2"
  printf '{"event":"%s","payload":{"message":"%s"}}\n' "$event" "${message//\"/\\\"}" >&2
}

json_escape() {
  python3 - <<'PY' "$1"
import json, sys
print(json.dumps(sys.argv[1], ensure_ascii=False))
PY
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --persona)
      persona="$2"
      shift 2
      ;;
    --platform)
      platform="$2"
      shift 2
      ;;
    --input)
      input_text="$2"
      shift 2
      ;;
    --input-path)
      input_path="$2"
      shift 2
      ;;
    --instruction)
      instruction="$2"
      shift 2
      ;;
    --output-file)
      output_file="$2"
      shift 2
      ;;
    --format)
      format="$2"
      shift 2
      ;;
    *)
      echo "未知参数: $1" >&2
      exit 2
      ;;
  esac
done

if [[ -z "$persona" || -z "$platform" ]]; then
  echo "必须提供 --persona 和 --platform" >&2
  exit 2
fi

if [[ -n "$input_path" ]]; then
  if [[ ! -f "$input_path" ]]; then
    echo "素材文件不存在: $input_path" >&2
    exit 1
  fi
  input_text="$(<"$input_path")"
fi

if [[ -z "${input_text// }" ]]; then
  echo "必须提供 --input 或 --input-path" >&2
  exit 2
fi

if [[ -z "$instruction" ]]; then
  instruction="按以上要求输出最终成稿。"
fi

if [[ "$persona" == "yuejian" && "$platform" == "xiaohongshu" ]]; then
  prompt=$(cat <<EOF
你是月见，一个写关系心理学与文艺情感内容的小红书作者，语气温柔克制，有画面感，共情但不说教，不用鸡汤、PUA话术、互联网黑话和恐吓表达。你会先讲清关系心理，再自然结合星宿关系、星座、合⭐️盘做辅助翻译，但不要写成玄学号。标题要有信息承诺，正文适合小红书卡片阅读，短句分行；需要时带 2-4 个 \`##\` 分段、可收藏框架段、自然互动钩子，结尾用“我是月见，…… 🌙”收束。审核敏感词必须打断成占⭐️、星⭐️盘、合⭐️盘、能⭐️量、运⭐️等。请根据这条素材完成任务：$input_text。具体要求：$instruction 只输出最终结果，不要解释。
EOF
)
else
  prompt=$(cat <<EOF
你现在为 persona "$persona" 在平台 "$platform" 写稿。只根据当前消息完成任务，不要读取文件、不要调用工具、不要引用外部上下文。素材：$input_text。任务要求：$instruction 只输出最终结果，不要解释。
EOF
)
fi

body=""
attempt=1
while [[ $attempt -le 3 ]]; do
  emit_event "task.progress" "调用本地 writer shell 路径生成内容"
  if body="$(printf %s "$prompt" | claude -p --permission-mode dontAsk --output-format text 2> >(cat >&2))"; then
    break
  fi
  emit_event "task.retry" "第 ${attempt} 次执行失败，准备重试"
  if [[ $attempt -eq 3 ]]; then
    exit 1
  fi
  sleep $((attempt * 3))
  attempt=$((attempt + 1))
done

body="${body#"${body%%[![:space:]]*}"}"
body="${body%"${body##*[![:space:]]}"}"

if [[ -n "$output_file" ]]; then
  mkdir -p "$(dirname "$output_file")"
  printf '%s\n' "$body" > "$output_file"
  printf '{"event":"task.output_file","payload":{"path":"%s"}}\n' "${output_file//\"/\\\"}" >&2
fi

if [[ "$format" == "json" ]]; then
  title="$(printf '%s\n' "$body" | awk '/^# /{sub(/^# /,""); print; exit}')"
  [[ -z "$title" ]] && title="未命名"
  python3 - <<'PY' "$title" "$body" "$output_file"
import json, sys
print(json.dumps({
    "title": sys.argv[1],
    "body": sys.argv[2],
    "output_file": sys.argv[3] or None,
}, ensure_ascii=False))
PY
else
  printf '%s\n' "$body"
fi
