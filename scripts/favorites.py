"""Build the favorites recap page from the user-maintained starred list."""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

REPO_LINE_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def parse_starred_list(text: str) -> list:
    """Extract repo full_names (owner/repo) from the starred list file.

    Ignores blank lines, comments, and anything that isn't a bare
    `owner/repo` line. Preserves file order, drops duplicates.
    """
    seen = set()
    result = []
    for line in text.splitlines():
        candidate = line.strip()
        if not candidate or candidate.startswith("#") or candidate.startswith("<!--"):
            continue
        if REPO_LINE_RE.match(candidate) and candidate not in seen:
            seen.add(candidate)
            result.append(candidate)
    return result


def load_all_records(repo_root: Path) -> list:
    """Load every digests/records/*.json file, oldest first."""
    records_dir = repo_root / "digests" / "records"
    if not records_dir.exists():
        return []
    records = []
    for path in sorted(records_dir.glob("*.json")):
        records.append(json.loads(path.read_text(encoding="utf-8")))
    return records


def build_favorites(starred: list, records: list) -> list:
    """Match each starred repo against its most recent digest appearance."""
    latest_by_name = {}
    for record in records:
        for candidate in record.get("candidates", []):
            latest_by_name[candidate["full_name"]] = {
                "date": record["date"],
                "html_url": candidate.get("html_url", f"https://github.com/{candidate['full_name']}"),
                "stars": candidate.get("stars"),
                "reason": candidate.get("reason"),
            }

    favorites = []
    for full_name in starred:
        info = latest_by_name.get(full_name)
        if info is None:
            favorites.append({
                "full_name": full_name,
                "html_url": f"https://github.com/{full_name}",
                "stars": None,
                "reason": None,
                "date": None,
            })
        else:
            favorites.append({"full_name": full_name, **info})
    return favorites


def render_favorites_markdown(favorites: list) -> str:
    """Render the favorites recap as Markdown."""
    lines = ["# 我的收藏", ""]
    if not favorites:
        lines.append("目前 `digests/starred.md` 裡還沒有任何收藏項目。")
        lines.append("")
        return "\n".join(lines)
    for item in favorites:
        lines.append(f"## {item['full_name']}")
        lines.append("")
        lines.append(f"- URL: {item['html_url']}")
        if item["stars"] is not None:
            lines.append(f"- Stars（收錄當時）: {item['stars']}")
        if item["date"]:
            lines.append(f"- 出現於每日精選日期: {item['date']}")
        if item["reason"]:
            lines.append(f"- 原始推薦/淘汰理由: {item['reason']}")
        else:
            lines.append("- 註記: 未出現在每日精選稽查紀錄中（可能是自行加入的收藏）")
        lines.append("")
    return "\n".join(lines)


def write_favorites(repo_root: Path) -> Path:
    """Read digests/starred.md + all records, write digests/favorites.md."""
    starred_path = repo_root / "digests" / "starred.md"
    starred_text = starred_path.read_text(encoding="utf-8") if starred_path.exists() else ""
    starred = parse_starred_list(starred_text)
    records = load_all_records(repo_root)
    favorites = build_favorites(starred, records)
    output_path = repo_root / "digests" / "favorites.md"
    output_path.write_text(render_favorites_markdown(favorites), encoding="utf-8")
    return output_path


def commit_and_push_if_changed(path: Path, repo_root: Path, message: str) -> bool:
    """Stage and commit path if it actually changed; push only when committed.

    Returns True if a commit was made and pushed, False if there was
    nothing to commit.
    """
    relative = path.relative_to(repo_root)
    subprocess.run(["git", "add", str(relative)], cwd=repo_root, check=True)
    diff_check = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=repo_root)
    if diff_check.returncode == 0:
        return False
    subprocess.run(["git", "commit", "-m", message], cwd=repo_root, check=True)
    subprocess.run(["git", "push"], cwd=repo_root, check=True)
    return True


if __name__ == "__main__":
    repo_root_arg = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
    written_path = write_favorites(repo_root_arg)
    pushed = commit_and_push_if_changed(written_path, repo_root_arg, "chore: refresh favorites recap")
    print(str(written_path))
    print("pushed" if pushed else "no changes")
