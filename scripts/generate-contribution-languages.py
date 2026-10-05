#!/usr/bin/env python3
"""Generate a language chart from the account's visible GitHub commit contributions."""

from __future__ import annotations

import html
import json
import os
import re
import sys
import urllib.request
from collections import defaultdict
from datetime import datetime
from pathlib import Path


API_URL = "https://api.github.com/graphql"
QUERY = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      startedAt
      endedAt
      totalCommitContributions
      commitContributionsByRepository(maxRepositories: 100) {
        repository { primaryLanguage { name color } }
        contributions { totalCount }
      }
    }
  }
}
"""
OUTPUT = Path("profile-3d-contrib/languages-by-contributions.svg")
FALLBACK_COLORS = ["#3572A5", "#dea584", "#f1e05a", "#563d7c", "#4F5D95", "#89e051"]


def fetch_contributions(token: str, username: str) -> dict:
    body = json.dumps({"query": QUERY, "variables": {"login": username}}).encode()
    request = urllib.request.Request(
        API_URL,
        data=body,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "github-profile-contribution-languages",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read())
    if payload.get("errors"):
        messages = "; ".join(error.get("message", "GraphQL request failed") for error in payload["errors"])
        raise RuntimeError(messages)
    user = payload.get("data", {}).get("user")
    if not user:
        raise RuntimeError(f"GitHub returned no profile for {username}")
    return user["contributionsCollection"]


def safe_color(color: str | None, index: int) -> str:
    if color and re.fullmatch(r"#[0-9a-fA-F]{6}", color):
        return color
    return FALLBACK_COLORS[index % len(FALLBACK_COLORS)]


def make_svg(username: str, collection: dict) -> str:
    language_commits: dict[str, int] = defaultdict(int)
    known_language_commits = 0
    language_colors: dict[str, str] = {}

    for item in collection.get("commitContributionsByRepository", []):
        repository = item.get("repository") or {}
        language = repository.get("primaryLanguage")
        count = (item.get("contributions") or {}).get("totalCount", 0)
        if language and language.get("name"):
            name = language["name"]
            language_commits[name] += count
            known_language_commits += count
            language_colors.setdefault(name, language.get("color"))

    total = collection.get("totalCommitContributions", 0)
    other_commits = max(0, total - known_language_commits)
    if other_commits:
        language_commits["Other / unclassified"] += other_commits

    languages = sorted(language_commits.items(), key=lambda item: (-item[1], item[0].lower()))
    width = 960
    top = 112
    row_height = 34
    height = max(190, top + max(1, len(languages)) * row_height + 30)
    max_count = max((count for _, count in languages), default=1)
    bar_x = 250
    bar_width = 590
    total_x = 930

    started = collection.get("startedAt", "")[:10]
    ended = collection.get("endedAt", "")[:10]
    title = "Languages in GitHub commit contributions"
    subtitle = f"{username}  ·  {started} to {ended}  ·  {total:,} commits"

    elements = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<style>text{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}.title{font-size:25px;font-weight:700;fill:#24292f}.subtitle{font-size:14px;fill:#57606a}.label{font-size:15px;fill:#24292f}.count{font-size:13px;fill:#57606a}</style>',
        f'<rect width="{width}" height="{height}" rx="8" fill="#ffffff"/>',
        f'<text class="title" x="32" y="42">{html.escape(title)}</text>',
        f'<text class="subtitle" x="32" y="70">{html.escape(subtitle)}</text>',
    ]

    if not languages:
        elements.append('<text class="label" x="32" y="125">No visible commit contributions in this period.</text>')
    else:
        for index, (name, count) in enumerate(languages):
            y = top + index * row_height
            length = max(2, bar_width * count / max_count)
            percent = (100 * count / total) if total else 0
            color = safe_color(language_colors.get(name), index)
            elements.extend(
                [
                    f'<text class="label" x="32" y="{y + 18}">{html.escape(name)}</text>',
                    f'<rect x="{bar_x}" y="{y}" width="{bar_width}" height="20" rx="5" fill="#eaeef2"/>',
                    f'<rect x="{bar_x}" y="{y}" width="{length:.1f}" height="20" rx="5" fill="{color}"/>',
                    f'<text class="count" x="{total_x}" y="{y + 15}" text-anchor="end">{count:,} · {percent:.1f}%</text>',
                ]
            )

    elements.append("</svg>")
    return "\n".join(elements) + "\n"


def main() -> None:
    token = os.environ.get("GITHUB_TOKEN")
    username = os.environ.get("USERNAME")
    if not token or not username:
        raise RuntimeError("GITHUB_TOKEN and USERNAME must be set")
    collection = fetch_contributions(token, username)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(make_svg(username, collection), encoding="utf-8")
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:  # fail the workflow visibly instead of publishing stale data
        print(f"Unable to generate contribution language chart: {error}", file=sys.stderr)
        sys.exit(1)
