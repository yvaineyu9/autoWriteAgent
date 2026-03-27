#!/bin/zsh
set -euo pipefail

persona=""
platform=""
instruction=""
input_file=""
output_file=""
format="markdown"

emit_event() {
  local event="$1"
  local message="$2"
  printf '{"event":"%s","payload":{"message":"%s"}}\n' "$event" "${message//\"/\\\"}" >&2
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
    --instruction)
      instruction="$2"
      shift 2
      ;;
    --input-file)
      input_file="$2"
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

if [[ -z "$persona" || -z "$platform" || -z "$instruction" || -z "$input_file" ]]; then
  echo "必须提供 --persona --platform --instruction --input-file" >&2
  exit 2
fi

if [[ ! -f "$input_file" ]]; then
  echo "输入文件不存在: $input_file" >&2
  exit 1
fi

current_content="$(<"$input_file")"
[[ -z "$output_file" ]] && output_file="$input_file"

run_claude_once() {
  if [[ "$persona" == "yuejian" && "$platform" == "xiaohongshu" ]]; then
    cat <<EOF | claude -p --no-session-persistence --permission-mode dontAsk --output-format text
你是月见，一个写关系心理学与文艺情感内容的小红书作者，语气温柔克制，有画面感，共情但不说教，不用鸡汤、PUA话术、互联网黑话和恐吓表达。你会先讲清关系心理，再自然结合星宿关系、星座、合⭐️盘做辅助翻译，但不要写成玄学号。标题要有信息承诺，正文适合小红书卡片阅读，短句分行；需要时带 2-4 个 \`##\` 分段、可收藏框架段、自然互动钩子，结尾用“我是月见，…… 🌙”收束。审核敏感词必须打断成占⭐️、星⭐️盘、合⭐️盘、能⭐️量、运⭐️等。请按下面的修改要求重写这篇稿子。修改要求：$instruction 当前稿件：$current_content 只输出最终结果，不要解释。
EOF
  else
    cat <<EOF | claude -p --no-session-persistence --permission-mode dontAsk --output-format text
你现在为 persona "$persona" 在平台 "$platform" 修改稿件。只根据当前消息完成任务，不要读取文件、不要调用工具、不要引用外部上下文。修改要求：$instruction 当前稿件：$current_content 只输出最终结果，不要解释。
EOF
  fi
}

body=""
attempt=1
stdout_file="$(mktemp)"
stderr_file="$(mktemp)"
trap 'rm -f "$stdout_file" "$stderr_file"' EXIT
while [[ $attempt -le 3 ]]; do
  : >"$stdout_file"
  : >"$stderr_file"
  emit_event "task.progress" "调用本地 writer shell 路径修改内容"
  if run_claude_once >"$stdout_file" 2>"$stderr_file"; then
    body="$(<"$stdout_file")"
    break
  fi
  if [[ -s "$stderr_file" ]]; then
    cat "$stderr_file" >&2
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
mkdir -p "$(dirname "$output_file")"
printf '%s\n' "$body" > "$output_file"
printf '{"event":"task.output_file","payload":{"path":"%s"}}\n' "${output_file//\"/\\\"}" >&2

if [[ "$format" == "json" ]]; then
  python3 - <<'PY' "$output_file" "$body"
import json, sys
print(json.dumps({"output_file": sys.argv[1], "body": sys.argv[2]}, ensure_ascii=False))
PY
else
  printf '%s\n' "$body"
fi
