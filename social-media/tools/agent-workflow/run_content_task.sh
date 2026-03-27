#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${0}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

provider="$(detect_provider)"
model=""
persona=""
platform=""
input_text=""
input_path=""
instruction="按以上要求输出最终成稿。"
output_file=""
format="markdown"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --provider) provider="$2"; shift 2 ;;
    --model) model="$2"; shift 2 ;;
    --persona) persona="$2"; shift 2 ;;
    --platform) platform="$2"; shift 2 ;;
    --input) input_text="$2"; shift 2 ;;
    --input-path) input_path="$2"; shift 2 ;;
    --instruction) instruction="$2"; shift 2 ;;
    --output-file) output_file="$2"; shift 2 ;;
    --format) format="$2"; shift 2 ;;
    *) echo "未知参数: $1" >&2; exit 2 ;;
  esac
done

if [[ -z "$persona" || -z "$platform" ]]; then
  echo "必须提供 --persona 和 --platform" >&2
  exit 2
fi

if [[ -n "$input_path" ]]; then
  [[ -f "$input_path" ]] || { echo "素材文件不存在: $input_path" >&2; exit 1; }
  input_text="$(<"$input_path")"
fi

if [[ -z "${input_text// }" ]]; then
  echo "必须提供 --input 或 --input-path" >&2
  exit 2
fi

prompt_file="$(mktemp)"
stdout_file="$(mktemp)"
stderr_file="$(mktemp)"
trap 'rm -f "$prompt_file" "$stdout_file" "$stderr_file"' EXIT

build_writer_prompt "$persona" "$platform" "$input_text" "$instruction" >"$prompt_file"

attempt=1
while [[ $attempt -le 3 ]]; do
  : >"$stdout_file"
  : >"$stderr_file"
  emit_event "task.progress" "调用 ${provider} 生成内容"
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

body="$(<"$stdout_file")"

if [[ -n "$output_file" ]]; then
  mkdir -p "$(dirname "$output_file")"
  printf '%s' "$body" >"$output_file"
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
  printf '%s' "$body"
fi
