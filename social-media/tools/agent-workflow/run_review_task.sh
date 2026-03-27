#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${0}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

provider="$(detect_provider)"
model=""
persona=""
platform=""
input_file=""
output_file=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --provider) provider="$2"; shift 2 ;;
    --model) model="$2"; shift 2 ;;
    --persona) persona="$2"; shift 2 ;;
    --platform) platform="$2"; shift 2 ;;
    --input-file) input_file="$2"; shift 2 ;;
    --output-file) output_file="$2"; shift 2 ;;
    *) echo "未知参数: $1" >&2; exit 2 ;;
  esac
done

if [[ -z "$persona" || -z "$platform" || -z "$input_file" ]]; then
  echo "必须提供 --persona --platform --input-file" >&2
  exit 2
fi

[[ -f "$input_file" ]] || { echo "输入文件不存在: $input_file" >&2; exit 1; }

prompt_file="$(mktemp)"
stdout_file="$(mktemp)"
stderr_file="$(mktemp)"
trap 'rm -f "$prompt_file" "$stdout_file" "$stderr_file"' EXIT

build_review_prompt "$persona" "$platform" "$(cat "$input_file")" >"$prompt_file"

attempt=1
while [[ $attempt -le 3 ]]; do
  : >"$stdout_file"
  : >"$stderr_file"
  emit_event "task.progress" "调用 ${provider} 审核内容"
  if run_provider_prompt "$provider" "$prompt_file" "$stdout_file" "$stderr_file" "$model"; then
    trim_file_in_place "$stdout_file"
    break
  fi
  [[ -s "$stderr_file" ]] && cat "$stderr_file" >&2
  emit_event "task.retry" "第 ${attempt} 次执行失败，准备重试"
  [[ $attempt -eq 3 ]] && exit 1
  sleep $((attempt * 3))
  attempt=$((attempt + 1))
done

raw="$(<"$stdout_file")"

if [[ -n "$output_file" ]]; then
  mkdir -p "$(dirname "$output_file")"
  printf '%s' "$raw" >"$output_file"
  printf '{"event":"task.output_file","payload":{"path":"%s"}}\n' "${output_file//\"/\\\"}" >&2
fi

printf '%s' "$raw"
