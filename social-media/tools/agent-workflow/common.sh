#!/bin/zsh
set -euo pipefail

emit_event() {
  local event="$1"
  local message="$2"
  printf '{"event":"%s","payload":{"message":"%s"}}\n' "$event" "${message//\"/\\\"}" >&2
}

detect_provider() {
  printf '%s\n' "${AI_PROVIDER:-${LLM_PROVIDER:-claude}}"
}

trim_file_in_place() {
  local target="$1"
  python3 - <<'PY' "$target"
from pathlib import Path
import sys

path = Path(sys.argv[1])
path.write_text(path.read_text(encoding="utf-8").strip() + "\n", encoding="utf-8")
PY
}

run_provider_prompt() {
  local provider="$1"
  local prompt_file="$2"
  local stdout_file="$3"
  local stderr_file="$4"
  local model="${5:-}"

  case "$provider" in
    claude)
      local cmd=(claude -p --no-session-persistence --permission-mode dontAsk --output-format text)
      if [[ -n "$model" ]]; then
        cmd+=(--model "$model")
      fi
      "${cmd[@]}" <"$prompt_file" >"$stdout_file" 2>"$stderr_file"
      ;;
    codex)
      local cmd=(codex exec - --skip-git-repo-check --sandbox read-only --output-last-message "$stdout_file")
      if [[ -n "$model" ]]; then
        cmd+=(--model "$model")
      fi
      OTEL_SDK_DISABLED=true NO_COLOR=1 "${cmd[@]}" <"$prompt_file" >/dev/null 2>"$stderr_file"
      [[ -s "$stdout_file" ]] || return 1
      ;;
    *)
      printf '不支持的 provider: %s\n' "$provider" >&2
      return 2
      ;;
  esac
}

build_writer_prompt() {
  local persona="$1"
  local platform="$2"
  local source_text="$3"
  local instruction="$4"

  if [[ "$persona" == "yuejian" && "$platform" == "xiaohongshu" ]]; then
    cat <<EOF
你是月见，一个写关系心理学与文艺情感内容的小红书作者，语气温柔克制，有画面感，共情但不说教，不用鸡汤、PUA话术、互联网黑话和恐吓表达。你会先讲清关系心理，再自然结合星宿关系、星座、合⭐️盘做辅助翻译，但不要写成玄学号。标题要有信息承诺，正文适合小红书卡片阅读，短句分行；需要时带 2-4 个 ## 分段、可收藏框架段、自然互动钩子，结尾用“我是月见，…… 🌙”收束。审核敏感词必须打断成占⭐️、星⭐️盘、合⭐️盘、能⭐️量、运⭐️等。请根据这条素材完成任务：$source_text。具体要求：$instruction 只输出最终结果，不要解释。
EOF
  else
    cat <<EOF
你现在为 persona "$persona" 在平台 "$platform" 写稿。只根据当前消息完成任务，不要读取文件、不要调用工具、不要引用外部上下文。素材：$source_text。任务要求：$instruction 只输出最终结果，不要解释。
EOF
  fi
}

build_revision_prompt() {
  local persona="$1"
  local platform="$2"
  local current_content="$3"
  local instruction="$4"

  if [[ "$persona" == "yuejian" && "$platform" == "xiaohongshu" ]]; then
    cat <<EOF
你是月见，一个写关系心理学与文艺情感内容的小红书作者，语气温柔克制，有画面感，共情但不说教，不用鸡汤、PUA话术、互联网黑话和恐吓表达。你会先讲清关系心理，再自然结合星宿关系、星座、合⭐️盘做辅助翻译，但不要写成玄学号。标题要有信息承诺，正文适合小红书卡片阅读，短句分行；需要时带 2-4 个 ## 分段、可收藏框架段、自然互动钩子，结尾用“我是月见，…… 🌙”收束。审核敏感词必须打断成占⭐️、星⭐️盘、合⭐️盘、能⭐️量、运⭐️等。请按下面的修改要求重写这篇稿子。修改要求：$instruction 当前稿件：$current_content 只输出最终结果，不要解释。
EOF
  else
    cat <<EOF
你现在为 persona "$persona" 在平台 "$platform" 修改稿件。只根据当前消息完成任务，不要读取文件、不要调用工具、不要引用外部上下文。修改要求：$instruction 当前稿件：$current_content 只输出最终结果，不要解释。
EOF
  fi
}

build_review_prompt() {
  local persona="$1"
  local platform="$2"
  local body="$3"

  if [[ "$persona" == "yuejian" && "$platform" == "xiaohongshu" ]]; then
    cat <<EOF
你是内容审核官，请审核这篇月见风格的小红书稿件。评分只根据当前消息，不要读取文件、不要调用工具、不要引用外部上下文。重点看 5 个维度：内容质量、人设一致性、平台适配、情感共鸣、传播潜力。月见风格要温柔克制、有画面感、共情但不说教；小红书稿要有信息承诺、适合卡片排版，并避开重 AI 味和违规词。待审核稿件：$body 请输出纯 JSON，不要代码块。格式必须为：{"total":数字,"pass":true/false,"scores":{"内容质量":数字,"人设一致性":数字,"平台适配":数字,"情感共鸣":数字,"传播潜力":数字},"feedback":"字符串或null","highlights":"字符串"} 总分 10 分，>=7 为通过。
EOF
  else
    cat <<EOF
请审核 persona "$persona" 在平台 "$platform" 的稿件。只根据当前消息评分，不要读取文件、不要调用工具、不要引用外部上下文。待审核稿件：$body 请输出纯 JSON，不要代码块。
EOF
  fi
}
