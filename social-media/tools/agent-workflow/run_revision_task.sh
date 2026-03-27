#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${0}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

provider="$(detect_provider)"
model=""
persona=""
platform=""
instruction=""
input_file=""
output_file=""
format="markdown"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --provider) provider="$2"; shift 2 ;;
    --model) model="$2"; shift 2 ;;
    --persona) persona="$2"; shift 2 ;;
    --platform) platform="$2"; shift 2 ;;
    --instruction) instruction="$2"; shift 2 ;;
    --input-file) input_file="$2"; shift 2 ;;
    --output-file) output_file="$2"; shift 2 ;;
    --format) format="$2"; shift 2 ;;
    *) echo "未知参数: $1" >&2; exit 2 ;;
  esac
done

if [[ -z "$persona" || -z "$platform" || -z "$instruction" || -z "$input_file" ]]; then
  echo "必须提供 --persona --platform --instruction --input-file" >&2
  exit 2
fi

[[ -f "$input_file" ]] || { echo "输入文件不存在: $input_file" >&2; exit 1; }
[[ -z "$output_file" ]] && output_file="$input_file"

prompt_file="$(mktemp)"
stdout_file="$(mktemp)"
stderr_file="$(mktemp)"
trap 'rm -f "$prompt_file" "$stdout_file" "$stderr_file"' EXIT

build_revision_prompt "$persona" "$platform" "$(cat "$input_file")" "$instruction" >"$prompt_file"

attempt=1
while [[ $attempt -le 3 ]]; do
  : >"$stdout_file"
  : >"$stderr_file"
  emit_event "task.progress" "调用 ${provider} 修改内容"
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
mkdir -p "$(dirname "$output_file")"
printf '%s' "$body" >"$output_file"
printf '{"event":"task.output_file","payload":{"path":"%s"}}\n' "${output_file//\"/\\\"}" >&2

if [[ "$format" == "json" ]]; then
  python3 - <<'PY' "$output_file" "$body"
import json, sys
print(json.dumps({"output_file": sys.argv[1], "body": sys.argv[2]}, ensure_ascii=False))
PY
else
  printf '%s' "$body"
fi
