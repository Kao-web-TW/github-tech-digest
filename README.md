# GitHub Tech Digest

This repo drives a daily Claude cloud routine that searches GitHub for newly
created, AI-integrated tools (video generation, data analysis, agents,
automation, etc.), analyzes each candidate's README, and publishes a
curated daily digest — both as an Artifact web page and as a Discord
notification.

## Where to look

- **`.claude/skills/github-tech-digest/SKILL.md`** — the full, current daily
  procedure the routine follows (search, analyze, publish Artifact, write
  audit log, trigger Discord). Start here for how the system actually
  operates today.
- **`digests/audit/`** — human-readable daily audit logs (one Markdown file
  per date), documenting what was found, what was selected, and why.
- **`digests/records/`** — the machine-readable equivalent of the audit
  logs (one JSON file per date), used by the Discord-relay workflow.
- **Actions tab** — run history for the Discord-relay workflow
  (`.github/workflows/notify-discord.yml`).

## About `scripts/*.py`

The Python scripts under `scripts/` are local-dev/testing references, not
what runs in production. The actual daily GitHub search step runs via the
`mcp__github__search_repositories` MCP tool call inside the cloud routine
itself, not the local `github_search.py` script — the routine's network
egress policy blocks direct calls to the GitHub REST Search API. See
`.claude/skills/github-tech-digest/SKILL.md` for the full explanation.

## Running the local tests

```bash
python -m unittest discover -s scripts/tests -t .
```
