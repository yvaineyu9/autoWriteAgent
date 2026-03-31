#!/usr/bin/env python3
"""
评审校验：验证评审 JSON 文件格式和规则。
"""

import json
import os
import re
import sys


REQUIRED_FIELDS = ["total", "pass", "scores", "feedback", "highlights"]
SCORE_DIMENSIONS = 5


def validate(data: dict) -> str | None:
    """校验评审数据。返回 None 表示通过，否则返回第一条错误描述。"""

    # 规则 2: 必需字段存在
    for field in REQUIRED_FIELDS:
        if field not in data:
            return f"缺少必需字段: {field}"

    # 规则 3: scores 恰好 5 个维度，每个 0-2
    scores = data["scores"]
    if not isinstance(scores, dict):
        return "scores 必须是一个对象/字典"
    if len(scores) != SCORE_DIMENSIONS:
        return f"scores 必须恰好 {SCORE_DIMENSIONS} 个维度，当前 {len(scores)} 个"
    for key, val in scores.items():
        if not isinstance(val, (int, float)):
            return f"scores[{key}] 必须是数字，当前类型 {type(val).__name__}"
        if val < 0 or val > 2:
            return f"scores[{key}] = {val}，超出范围 0-2"

    # 规则 4: total == sum(scores)
    expected_total = sum(scores.values())
    if data["total"] != expected_total:
        return f"total ({data['total']}) != sum(scores) ({expected_total})"

    # 规则 5: pass == (total >= 7)
    expected_pass = data["total"] >= 7
    if data["pass"] != expected_pass:
        return f"pass 应为 {expected_pass}（total={data['total']}），实际为 {data['pass']}"

    # 规则 6: pass=false 时 feedback 不为 null
    if not data["pass"] and data["feedback"] is None:
        return "pass=false 时 feedback 不能为 null"

    return None


def main():
    if len(sys.argv) < 2:
        print("用法: python3 validate_review.py <json_file>", file=sys.stderr)
        sys.exit(1)

    json_file = sys.argv[1]

    if not os.path.isfile(json_file):
        print(f"文件不存在: {json_file}", file=sys.stderr)
        sys.exit(1)

    try:
        with open(json_file, "r", encoding="utf-8") as f:
            raw = f.read().strip()
    except Exception as e:
        print(f"读取文件失败: {e}", file=sys.stderr)
        sys.exit(1)

    # 去除可能的 ```json 包裹
    if raw.startswith("```"):
        # 去掉第一行和最后一行的 ```
        lines = raw.split("\n")
        # 去掉开头的 ```json 或 ```
        if lines[0].strip().startswith("```"):
            lines = lines[1:]
        # 去掉结尾的 ```
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        raw = "\n".join(lines)

    # 规则 1: 合法 JSON
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"无效的 JSON: {e}", file=sys.stderr)
        sys.exit(1)

    error = validate(data)
    if error:
        print(error, file=sys.stderr)
        sys.exit(1)

    # 输出 clean JSON
    print(json.dumps(data, ensure_ascii=False, indent=2))
    print("校验通过", file=sys.stderr)


if __name__ == "__main__":
    main()
