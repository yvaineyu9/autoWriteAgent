Run the Astrology Content Creator Skill (Pro Max).

Usage: /podcast [URL or Text]

Steps:
1. Read the skill definition from `.claude/skills/astrology_content_creator.md`.
2. Adopt the persona and logic defined in that skill.
3. If the input is a URL, use the `bash` tool to transcribe it first (using whisper or yt-dlp as needed).
4. If the input is text, use it directly.
5. Generate a deep-dive podcast script (5000-8000 chars) based on the input.
