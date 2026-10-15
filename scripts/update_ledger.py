"""Rebuilds the ledger section of README.md from the public GitHub API.
Uses only the standard library. Run by .github/workflows/ledger.yml, or locally:
    GH_TOKEN=<token> python scripts/update_ledger.py
"""
import json, os, re, sys, urllib.request, urllib.parse
from datetime import datetime

USER = "avik22835"
# Repos whose latest build status is shown. Confirm these names match your repos.
FEATURED = ["graphmem", "clicksense", "jarvis-ai", "polyglot-intel"]
MAX_PRS, MAX_COMMITS = 15, 10
START, END = "<!--LEDGER:START-->", "<!--LEDGER:END-->"


def api(path, params=None):
    url = "https://api.github.com" + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": USER + "-profile-ledger",
        **({"Authorization": "Bearer " + os.environ["GH_TOKEN"]} if os.environ.get("GH_TOKEN") else {}),
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def day(iso):
    return datetime.strptime(iso[:10], "%Y-%m-%d").strftime("%d %b %Y") if iso else "-"


def cell(s):
    return str(s).replace("|", "\\|").replace("\n", " ").strip()


def fetch_prs():
    q = f"author:{USER} is:pr is:public -user:{USER}"  # pull requests to other people's repos
    items = api("/search/issues", {"q": q, "sort": "updated", "order": "desc", "per_page": 100})["items"]
    rows = []
    for it in items:
        repo = it["repository_url"].split("/repos/")[1]
        merged = (it.get("pull_request") or {}).get("merged_at")
        state = "Merged" if merged else ("Open" if it["state"] == "open" else "Closed, not merged")
        rows.append({"repo": repo, "n": it["number"], "title": it["title"], "state": state,
                     "date": merged or it.get("closed_at") or it["created_at"], "url": it["html_url"]})
    order = {"Merged": 0, "Open": 1, "Closed, not merged": 2}
    rows.sort(key=lambda r: (order[r["state"]], r["date"]), reverse=False)
    merged_first = [r for r in rows if r["state"] == "Merged"][::-1]
    rest = [r for r in rows if r["state"] != "Merged"]
    return merged_first + rest


def fetch_commits():
    events = api(f"/users/{USER}/events/public", {"per_page": 100})
    out = []
    for e in events:
        if e["type"] != "PushEvent":
            continue
        repo = e["repo"]["name"]
        for c in reversed(e["payload"].get("commits", [])):
            out.append({"repo": repo, "sha": c["sha"], "msg": c["message"].split("\n")[0],
                        "date": e["created_at"]})
    return out[:MAX_COMMITS]


def fetch_builds():
    rows = []
    for name in FEATURED:
        try:
            runs = api(f"/repos/{USER}/{name}/actions/runs", {"per_page": 1})["workflow_runs"]
        except Exception:
            runs = []
        if not runs:
            rows.append((name, "No workflow runs yet", "-", None))
            continue
        r = runs[0]
        res = r["conclusion"] or r["status"]
        label = {"success": "Passing", "failure": "Failing", "cancelled": "Cancelled",
                 "in_progress": "Running", "queued": "Queued"}.get(res, res)
        rows.append((name, label, day(r["updated_at"]), r["html_url"]))
    return rows


def render(prs, commits, builds):
    L = []
    L.append("**Pull requests to other projects** (every state, newest first within each)\n")
    if prs:
        L.append("| Project | PR | What it does | Status | Date |")
        L.append("|:--|:--|:--|:--|:--|")
        for p in prs[:MAX_PRS]:
            mark = {"Merged": "✓ Merged", "Open": "○ Open", "Closed, not merged": "✗ Closed, not merged"}[p["state"]]
            L.append(f"| [{p['repo']}](https://github.com/{p['repo']}) | [#{p['n']}]({p['url']}) | {cell(p['title'])} | {mark} | {day(p['date'])} |")
    else:
        L.append("_No pull requests found yet._")
    L.append("\n**Latest commits** (public, across my repos)\n")
    if commits:
        L.append("| Date | Repo | Commit | Message |")
        L.append("|:--|:--|:--|:--|")
        for c in commits:
            L.append(f"| {day(c['date'])} | [{c['repo'].split('/')[-1]}](https://github.com/{c['repo']}) | [`{c['sha'][:7]}`](https://github.com/{c['repo']}/commit/{c['sha']}) | {cell(c['msg'])} |")
    else:
        L.append("_No recent public commits._")
    L.append("\n**Latest build on each project**\n")
    L.append("| Project | Build | Last run |")
    L.append("|:--|:--|:--|")
    for name, label, when, url in builds:
        icon = {"Passing": "✓", "Failing": "✗"}.get(label, "○")
        link = f"[{icon} {label}]({url})" if url else f"{icon} {label}"
        L.append(f"| [{name}](https://github.com/{USER}/{name}) | {link} | {when} |")
    return "\n".join(L)


def main():
    path = os.path.join(os.path.dirname(__file__), "..", "README.md")
    text = open(path, encoding="utf-8").read()
    if START not in text or END not in text:
        sys.exit("README.md is missing the LEDGER markers")
    body = render(fetch_prs(), fetch_commits(), fetch_builds())
    new = re.sub(re.escape(START) + r".*?" + re.escape(END), lambda m: f"{START}\n{body}\n{END}", text, flags=re.S)
    if new != text:
        open(path, "w", encoding="utf-8").write(new)
        print("README updated")
    else:
        print("No changes")


if __name__ == "__main__":
    main()
