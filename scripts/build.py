"""Rebuild the profile README and its SVG cards from live GitHub data.

Run by .github/workflows/refresh.yml every day. Edit README.tpl.md, not README.md.

  python scripts/build.py           # regenerate README.md and assets/*.svg
  python scripts/build.py --health  # also print the repo health report (markdown) to stdout
"""

import collections
import datetime as dt
import html
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

USER = "HarshavardhanReddy585"
ROOT = Path(__file__).resolve().parent.parent
TOKEN = os.environ.get("GITHUB_TOKEN", "")
TODAY = dt.datetime.now(dt.timezone.utc)

# "Hello" of the day: one per day, cycling. Nods to the translation work.
GREETINGS = [
    ("Hello", "English"), ("Hallo", "German"), ("నమస్కారం", "Telugu"),
    ("नमस्ते", "Hindi"), ("ನಮಸ್ಕಾರ", "Kannada"), ("வணக்கம்", "Tamil"),
    ("Bonjour", "French"), ("Hola", "Spanish"), ("こんにちは", "Japanese"),
    ("Ciao", "Italian"), ("Olá", "Portuguese"), ("안녕하세요", "Korean"),
]

LANG_COLORS = {
    "Jupyter Notebook": "#DA5B0B", "Python": "#3572A5", "HTML": "#E34C26",
    "CSS": "#663399", "JavaScript": "#F1E05A", "C": "#8C8C8C", "Shell": "#89E051",
    "TeX": "#3D6117", "PowerShell": "#012456", "Java": "#B07219",
}


def api(path, body=None):
    url = path if path.startswith("http") else f"https://api.github.com{path}"
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body else None)
    req.add_header("Accept", "application/vnd.github+json")
    if TOKEN:
        req.add_header("Authorization", f"Bearer {TOKEN}")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def own_repos():
    repos = api(f"/users/{USER}/repos?per_page=100&type=owner")
    return [r for r in repos if not r["fork"] and r["name"] != USER and not r["archived"]]


def pinned_names():
    """Pinned repos in display order. Needs a token (GraphQL); falls back to None."""
    if not TOKEN:
        return None
    q = ('query{user(login:"%s"){pinnedItems(first:6,types:REPOSITORY)'
         "{nodes{... on Repository{name}}}}}" % USER)
    try:
        data = api("https://api.github.com/graphql", {"query": q})
        return [n["name"] for n in data["data"]["user"]["pinnedItems"]["nodes"]]
    except Exception as e:  # never fail the build over pins
        print(f"pinned lookup failed: {e}", file=sys.stderr)
        return None


def ago(iso):
    days = (TODAY - dt.datetime.fromisoformat(iso.replace("Z", "+00:00"))).days
    if days == 0:
        return "today"
    if days < 31:
        return f"{days}d ago"
    if days < 365:
        return f"{days // 30}mo ago"
    return f"{days // 365}y ago"


def esc(s):
    return html.escape(s or "", quote=True)


def md_escape(s):
    for ch in "\\`*_[]<>|#":
        s = s.replace(ch, "\\" + ch)
    return s


# ---------- README sections ----------

def featured_table(repos, pinned):
    by_name = {r["name"]: r for r in repos}
    if pinned:
        chosen = [by_name[n] for n in pinned if n in by_name]
    else:  # no token: most recently pushed repos
        chosen = sorted(repos, key=lambda r: r["pushed_at"], reverse=True)[:6]
    rows = ["| Project | What it is | Tags |", "|---|---|---|"]
    for r in chosen:
        desc = (r["description"] or "_No description yet._").replace("|", "\\|")
        tags = " ".join(f"`{t}`" for t in r["topics"][:4]) or (r["language"] or "")
        rows.append(f"| [**{r['name']}**]({r['html_url']}) | {desc} | {tags} |")
    return "\n".join(rows)


def recent_activity(repos):
    """Latest non-merge commit of the 5 most recently pushed repos.

    Read from each repo directly: the public events feed lags by hours and drops commit text.
    """
    out = []
    for r in sorted(repos, key=lambda r: r["pushed_at"], reverse=True)[:5]:
        commits = api(f"/repos/{USER}/{r['name']}/commits?per_page=5")
        c = next((c for c in commits if len(c["parents"]) < 2), None)
        if c:
            out.append((r["name"], c["commit"]["message"].splitlines()[0][:80], c["commit"]["committer"]["date"]))
    return out


def recent_list(activity):
    return "\n".join(
        f"- **[{repo}](https://github.com/{USER}/{repo})**: {md_escape(msg)} <sub>{ago(when)}</sub>"
        for repo, msg, when in activity)


# ---------- SVG cards ----------

def header_svg():
    word, lang = GREETINGS[TODAY.timetuple().tm_yday % len(GREETINGS)]
    # A tiny attention map between an English and a German phrase: the visual motif.
    src, tgt = ["I", "build", "models", "that", "translate"], ["Ich", "baue", "Modelle,", "die", "übersetzen"]
    # Soft attention: mostly diagonal, with some spill to neighbours ("translate" leans on "die").
    weight = [[2.7 ** -abs(i - j) * (1.6 if (i, j) == (4, 3) else 1) for j in range(5)] for i in range(5)]
    x0s, y0, y1, step = 576, 62, 146, 66  # token centres
    arcs, labels = [], []
    for i, w in enumerate(src):
        labels.append(f'<text x="{x0s + i * step}" y="{y0 - 10}" class="tok">{esc(w)}</text>')
    for j, w in enumerate(tgt):
        labels.append(f'<text x="{x0s + j * step}" y="{y1 + 22}" class="tok de">{esc(w)}</text>')
    for i in range(5):
        for j in range(5):
            w = min(weight[i][j], 1)
            if w < 0.05:
                continue
            x0, x1 = x0s + i * step, x0s + j * step
            arcs.append(f'<path d="M{x0},{y0} C{x0},{(y0 + y1) / 2} {x1},{(y0 + y1) / 2} {x1},{y1}" class="arc" '
                        f'style="animation-delay:{0.25 * i + 0.1 * abs(i - j):.2f}s;opacity:{0.12 + 0.8 * w:.2f};'
                        f'stroke-width:{0.8 + 2 * w:.1f}"/>')
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 210" width="900" height="210" role="img" aria-label="{esc(word)} ({esc(lang)}), I'm Harshavardhan Reddy">
<style>
  .bg{{fill:#0b1020}} .t{{font:700 34px 'Segoe UI',Ubuntu,'Noto Sans','Noto Sans Telugu','Noto Sans Devanagari',sans-serif;fill:#f5f7ff}}
  .s{{font:400 16px 'Segoe UI',Ubuntu,sans-serif;fill:#9aa7c7}} .l{{font:500 12px ui-monospace,Consolas,monospace;fill:#6ee7b7}}
  .tok{{font:500 12px ui-monospace,Consolas,monospace;fill:#c7d2fe;text-anchor:middle}} .de{{fill:#fcd34d}}
  .arc{{fill:none;stroke:#818cf8;stroke-width:2;stroke-dasharray:200;animation:draw 1.6s ease both}}
  @keyframes draw{{from{{stroke-dashoffset:200}}to{{stroke-dashoffset:0}}}}
  @media (prefers-reduced-motion:reduce){{.arc{{animation:none}}}}
</style>
<rect class="bg" width="900" height="210" rx="16"/>
<text x="36" y="58" class="l">// hello of the day · {esc(lang.lower())}</text>
<text x="36" y="104" class="t">{esc(word)}, I'm Harshavardhan</text>
<text x="36" y="138" class="s">ML / generative AI · applied security</text>
<text x="36" y="164" class="s">Final-year CS @ MIT Manipal</text>
{"".join(labels)}
{"".join(arcs)}
</svg>
'''


def stack_svg(repos, langs):
    total = sum(langs.values()) or 1
    top = langs.most_common(5)
    topics = collections.Counter(t for r in repos for t in r["topics"]).most_common(6)
    last = max(repos, key=lambda r: r["pushed_at"])
    lines = [
        ("$ whoami", "cmd"),
        (f"{USER} · {len(repos)} public projects · {sum(len(r['topics']) for r in repos)} topics", "out"),
        ("$ git log -1 --all", "cmd"),
        (f"{last['name']} · pushed {ago(last['pushed_at'])}", "out"),
        ("$ cat interests.txt", "cmd"),
        ("  ".join(f"#{t}" for t, _ in topics), "out"),
        ("$ du --languages", "cmd"),
    ]
    rows, y = [], 66
    for text, cls in lines:
        rows.append(f'<text x="24" y="{y}" class="{cls}">{esc(text)}</text>')
        y += 24
    bar_x, bar_w = 24, 852
    x = bar_x
    segs, legend = [], []
    for name, b in top:
        w = bar_w * b / total
        segs.append(f'<rect x="{x:.1f}" y="{y - 8}" width="{max(w, 2):.1f}" height="10" fill="{LANG_COLORS.get(name, "#8b949e")}"/>')
        x += w
    lx = 24
    for name, b in top:
        legend.append(f'<circle cx="{lx + 5}" cy="{y + 22}" r="5" fill="{LANG_COLORS.get(name, "#8b949e")}"/>'
                      f'<text x="{lx + 14}" y="{y + 26}" class="out">{esc(name)} {100 * b / total:.0f}%</text>')
        lx += 22 + 8 * len(f"{name} {100 * b / total:.0f}%")
    h = y + 48
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 {h}" width="900" height="{h}" role="img" aria-label="Profile stats generated from GitHub data">
<style>
  .bg{{fill:#0b1020}} .bar{{fill:#151b2e}} .cmd{{font:600 13px ui-monospace,Consolas,monospace;fill:#6ee7b7}}
  .out{{font:400 13px ui-monospace,Consolas,monospace;fill:#c9d1d9}} .ttl{{font:500 12px ui-monospace,Consolas,monospace;fill:#6b7280}}
</style>
<rect class="bg" width="900" height="{h}" rx="12"/>
<rect class="bar" width="900" height="34" rx="12"/><rect class="bar" y="20" width="900" height="14"/>
<circle cx="22" cy="17" r="6" fill="#ff5f57"/><circle cx="42" cy="17" r="6" fill="#febc2e"/><circle cx="62" cy="17" r="6" fill="#28c840"/>
<text x="450" y="22" text-anchor="middle" class="ttl">harsha@manipal: ~ · refreshed {TODAY:%Y-%m-%d}</text>
{"".join(rows)}
<clipPath id="c"><rect x="{bar_x}" y="{y - 8}" width="{bar_w}" height="10" rx="5"/></clipPath>
<g clip-path="url(#c)">{"".join(segs)}</g>
{"".join(legend)}
</svg>
'''


# ---------- health check: the "what to improve next" list ----------

def health(repos):
    issues = []
    for r in sorted(repos, key=lambda r: r["name"].lower()):
        probs = []
        if not r["description"]:
            probs.append("add a description")
        if len(r["topics"]) < 3:
            probs.append(f"add topics ({len(r['topics'])}/3)")
        if not r["license"]:
            probs.append("add a LICENSE so others know how they may reuse it")
        try:
            api(f"/repos/{USER}/{r['name']}/readme")
        except urllib.error.HTTPError as e:
            if e.code != 404:
                raise
            probs.append("add a README")
        if (TODAY - dt.datetime.fromisoformat(r["pushed_at"].replace("Z", "+00:00"))).days > 540:
            probs.append("untouched for 18+ months: polish it or archive it")
        if probs:
            issues.append(f"- [ ] **[{r['name']}]({r['html_url']})**: " + "; ".join(probs))
    return issues


def main():
    # Any API failure below raises, so a rate-limited run exits without touching the files.
    repos = own_repos()
    langs = collections.Counter()
    for r in repos:
        langs.update(api(r["languages_url"]))

    tpl = (ROOT / "README.tpl.md").read_text(encoding="utf-8")
    readme = (tpl.replace("{{featured}}", featured_table(repos, pinned_names()))
                 .replace("{{recent}}", recent_list(recent_activity(repos)))
                 .replace("{{updated}}", TODAY.strftime("%Y-%m-%d")))
    (ROOT / "README.md").write_text(readme, encoding="utf-8")
    (ROOT / "assets").mkdir(exist_ok=True)
    (ROOT / "assets" / "header.svg").write_text(header_svg(), encoding="utf-8")
    (ROOT / "assets" / "stack.svg").write_text(stack_svg(repos, langs), encoding="utf-8")

    if "--health" in sys.argv:
        items = health(repos)
        print("\n".join(items) if items else "")


if __name__ == "__main__":
    main()
