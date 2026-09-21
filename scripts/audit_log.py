"""Render and persist the daily audit log, then publish it to the GitHub remote."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def render_audit_markdown(record: dict) -> str:
    """Render a daily digest run record as a Markdown audit document."""
    lines = [
        f"# Digest Audit Log — {record['date']}",
        "",
        f"**Status:** {record['status']}",
        "",
        "## Search Query",
        "",
        f"```\n{record['query']}\n```",
        "",
        f"## Candidates ({len(record['candidates'])} found)",
        "",
    ]
    for candidate in record["candidates"]:
        verdict = "SELECTED" if candidate["selected"] else "REJECTED"
        lines.append(f"### [{verdict}] {candidate['full_name']} (★{candidate['stars']})")
        lines.append("")
        lines.append(f"- URL: {candidate['html_url']}")
        lines.append(f"- Reason: {candidate['reason']}")
        lines.append("")
    if record.get("error"):
        lines.append("## Error")
        lines.append("")
        lines.append(record["error"])
        lines.append("")
    return "\n".join(lines)


def write_audit_log(record: dict, repo_root: Path) -> Path:
    """Write the rendered audit markdown to digests/audit/<date>.md under repo_root."""
    audit_dir = repo_root / "digests" / "audit"
    audit_dir.mkdir(parents=True, exist_ok=True)
    path = audit_dir / f"{record['date']}.md"
    path.write_text(render_audit_markdown(record), encoding="utf-8")
    return path


def write_record_json(record: dict, repo_root: Path) -> Path:
    """Write the raw record JSON to digests/records/<date>.json.

    This is the machine-readable counterpart to the audit markdown, read by
    the GitHub Actions Discord-relay workflow (the cloud routine's own
    network egress cannot reach discord.com, so that workflow does the
    actual webhook call once this file lands on the remote).
    """
    records_dir = repo_root / "digests" / "records"
    records_dir.mkdir(parents=True, exist_ok=True)
    path = records_dir / f"{record['date']}.json"
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def commit_and_push(paths: list[Path], repo_root: Path, message: str) -> None:
    """Stage, commit, and push the given files from within repo_root."""
    relatives = [str(path.relative_to(repo_root)) for path in paths]
    subprocess.run(["git", "add", *relatives], cwd=repo_root, check=True)
    subprocess.run(["git", "commit", "-m", message], cwd=repo_root, check=True)
    subprocess.run(["git", "push"], cwd=repo_root, check=True)


if __name__ == "__main__":
    record_path = Path(sys.argv[1])
    repo_root_arg = Path(sys.argv[2])
    loaded_record = json.loads(record_path.read_text(encoding="utf-8"))
    markdown_path = write_audit_log(loaded_record, repo_root_arg)
    json_path = write_record_json(loaded_record, repo_root_arg)
    commit_and_push(
        [markdown_path, json_path],
        repo_root_arg,
        f"chore: digest audit log for {loaded_record['date']}",
    )
    print(str(markdown_path))
    print(str(json_path))
