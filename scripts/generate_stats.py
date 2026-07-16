#!/usr/bin/env python3
"""Generate GitHub stats SVG cards for the profile README.

Runs in GitHub Actions with the built-in GITHUB_TOKEN and writes
generated/stats.svg and generated/languages.svg. Uses only the
standard library so there is nothing to install.
"""

import json
import os
import sys
import urllib.request

USERNAME = "ali-jifi"
API = "https://api.github.com"
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "generated")

# GitHub linguist colors for languages likely to show up; anything else gets gray.
LANGUAGE_COLORS = {
    "Python": "#3572A5",
    "JavaScript": "#f1e05a",
    "TypeScript": "#3178c6",
    "Java": "#b07219",
    "C": "#555555",
    "C++": "#f34b7d",
    "C#": "#178600",
    "HTML": "#e34c26",
    "CSS": "#663399",
    "Lua": "#000080",
    "Jupyter Notebook": "#DA5B0B",
    "Shell": "#89e051",
    "Go": "#00ADD8",
    "Rust": "#dea584",
}
FALLBACK_COLOR = "#8b949e"

# Mid-tone palette that stays readable on both light and dark GitHub themes.
TITLE_COLOR = "#539bf5"
LABEL_COLOR = "#768390"
VALUE_COLOR = "#8bb4f7"


def api_get(path):
    req = urllib.request.Request(f"{API}{path}")
    req.add_header("Accept", "application/vnd.github+json")
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def fetch_all_repos():
    repos = []
    page = 1
    while True:
        batch = api_get(f"/users/{USERNAME}/repos?per_page=100&type=owner&page={page}")
        repos.extend(batch)
        if len(batch) < 100:
            return repos
        page += 1


def fetch_commit_count():
    """Total commits authored, via the search API. Returns None on failure."""
    try:
        result = api_get(f"/search/commits?q=author:{USERNAME}&per_page=1")
        return result.get("total_count")
    except Exception as exc:  # noqa: BLE001 - stat is optional, card must still render
        print(f"commit count unavailable: {exc}", file=sys.stderr)
        return None


def svg_header(width, height, title):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" fill="none" role="img" aria-label="{title}">'
        f'<style>text{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif}}</style>'
        f'<text x="25" y="33" font-size="18" font-weight="600" fill="{TITLE_COLOR}">{title}</text>'
    )


def render_stats_card(stats):
    width, height = 420, 190
    rows = [
        ("Total stars earned", stats["stars"]),
        ("Total forks", stats["forks"]),
        ("Public repositories", stats["repos"]),
        ("Followers", stats["followers"]),
    ]
    if stats["commits"] is not None:
        rows.insert(0, ("Total commits", stats["commits"]))
        height += 26

    parts = [svg_header(width, height, "Ali's GitHub Stats")]
    y = 66
    for label, value in rows:
        parts.append(f'<text x="25" y="{y}" font-size="14" fill="{LABEL_COLOR}">{label}:</text>')
        parts.append(
            f'<text x="{width - 25}" y="{y}" font-size="14" font-weight="600" '
            f'text-anchor="end" fill="{VALUE_COLOR}">{value}</text>'
        )
        y += 26
    parts.append("</svg>")
    return "".join(parts)


def render_languages_card(languages):
    width = 420
    total = sum(languages.values()) or 1
    top = sorted(languages.items(), key=lambda kv: kv[1], reverse=True)[:8]

    bar_y, bar_h, bar_w = 52, 10, width - 50
    height = bar_y + bar_h + 22 + ((len(top) + 1) // 2) * 24 + 14

    parts = [svg_header(width, height, "Most Used Languages")]

    # Stacked proportion bar with a clip for rounded corners.
    parts.append(
        f'<clipPath id="bar"><rect x="25" y="{bar_y}" width="{bar_w}" height="{bar_h}" rx="5"/></clipPath>'
    )
    x = 25.0
    for name, size in top:
        seg = bar_w * size / total
        color = LANGUAGE_COLORS.get(name, FALLBACK_COLOR)
        parts.append(
            f'<rect x="{x:.1f}" y="{bar_y}" width="{seg + 1:.1f}" height="{bar_h}" '
            f'fill="{color}" clip-path="url(#bar)"/>'
        )
        x += seg

    # Two-column legend.
    for i, (name, size) in enumerate(top):
        col_x = 25 + (i % 2) * (width // 2 - 12)
        row_y = bar_y + bar_h + 28 + (i // 2) * 24
        color = LANGUAGE_COLORS.get(name, FALLBACK_COLOR)
        pct = 100.0 * size / total
        parts.append(f'<circle cx="{col_x + 5}" cy="{row_y - 4}" r="5" fill="{color}"/>')
        parts.append(
            f'<text x="{col_x + 18}" y="{row_y}" font-size="13" fill="{LABEL_COLOR}">'
            f"{name} {pct:.1f}%</text>"
        )
    parts.append("</svg>")
    return "".join(parts)


def main():
    user = api_get(f"/users/{USERNAME}")
    repos = [r for r in fetch_all_repos() if not r.get("fork")]

    languages = {}
    for repo in repos:
        try:
            for lang, size in api_get(f"/repos/{USERNAME}/{repo['name']}/languages").items():
                languages[lang] = languages.get(lang, 0) + size
        except Exception as exc:  # noqa: BLE001 - one repo must not sink the card
            print(f"skipping languages for {repo['name']}: {exc}", file=sys.stderr)

    stats = {
        "stars": sum(r["stargazers_count"] for r in repos),
        "forks": sum(r["forks_count"] for r in repos),
        "repos": user["public_repos"],
        "followers": user["followers"],
        "commits": fetch_commit_count(),
    }

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "stats.svg"), "w") as f:
        f.write(render_stats_card(stats))
    with open(os.path.join(OUT_DIR, "languages.svg"), "w") as f:
        f.write(render_languages_card(languages))
    print(f"stats: {stats}")
    print(f"languages: {len(languages)} found")


if __name__ == "__main__":
    main()
