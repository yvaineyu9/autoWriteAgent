#!/bin/zsh
set -euo pipefail

persona=""
platform=""
input_file=""
output_file=""

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
    --input-file)
      input_file="$2"
      shift 2
      ;;
    --output-file)
      output_file="$2"
      shift 2
      ;;
    *)
      echo "未知参数: $1" >&2
      exit 2
      ;;
  esac
done

if [[ -z "$persona" || -z "$platform" || -z "$input_file" ]]; then
  echo "必须提供 --persona --platform --input-file" >&2
  exit 2
fi

if [[ ! -f "$input_file" ]]; then
  echo "输入文件不存在: $input_file" >&2
  exit 1
fi

body="$(<"$input_file")"

if [[ "$persona" == "yuejian" && "$platform" == "xiaohongshu" ]]; then
  prompt=$(cat <<EOF
你是内容审核官，请审核这篇月见风格的小红书稿件。评分只根据当前消息，不要读取文件、不要调用工具、不要引用外部上下文。重点看 5 个维度：内容质量、人设一致性、平台适配、情感共鸣、传播潜力。月见风格要温柔克制、有画面感、共情但不说教；小红书稿要有信息承诺、适合卡片排版，并避开重 AI 味和违规词。待审核稿件：$body 请输出纯 JSON，不要代码块。格式必须为：{"total":数字,"pass":true/false,"scores":{"内容质量":数字,"人设一致性":数字,"平台适配":数字,"情感共鸣":数字,"传播潜力":数字},"feedback":"字符串或null","highlights":"字符串"} 总分 10 分，>=7 为通过。
EOF
)
else
  prompt=$(cat <<EOF
请审核 persona "$persona" 在平台 "$platform" 的稿件。只根据当前消息评分，不要读取文件、不要调用工具、不要引用外部上下文。待审核稿件：$body 请输出纯 JSON，不要代码块。
EOF
)
fi

raw=""
attempt=1
while [[ $attempt -le 3 ]]; do
  emit_event "task.progress" "调用本地 reviewer shell 路径审核内容"
  if raw="$(printf %s "$prompt" | claude -p --permission-mode dontAsk --output-format text 2> >(cat >&2))"; then
    break
  fi
  emit_event "task.retry" "第 ${attempt} 次执行失败，准备重试"
  if [[ $attempt -eq 3 ]]; then
    exit 1
  fi
  sleep $((attempt * 3))
  attempt=$((attempt + 1))
done

raw="${raw#"${raw%%[![:space:]]*}"}"
raw="${raw%"${raw##*[![:space:]]}"}"

if [[ -n "$output_file" ]]; then
  mkdir -p "$(dirname "$output_file")"
  printf '%s\n' "$raw" > "$output_file"
  printf '{"event":"task.output_file","payload":{"path":"%s"}}\n' "${output_file//\"/\\\"}" >&2
fi

printf '%s\n' "$raw"
