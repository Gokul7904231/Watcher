#!/usr/bin/env python3
"""jobwatch: get an instant phone alert when a matching job is posted.

Checks company career boards (Greenhouse, Lever, Ashby) and optional RSS/Atom
feeds, filters by your keywords, remembers what it has seen, and notifies you
via Telegram and/or ntfy.sh.

Usage:
  python jobwatch.py                run once (scheduled runner mode)
  python jobwatch.py --dry-run      print matches, send nothing, save nothing
  python jobwatch.py --test-notify  send a test message
  python jobwatch.py --add URL      add a company from its careers URL
"""

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONFIG = HERE / "config.json"
STATE = HERE / "seen.json"
UA = "Mozilla/5.0 (personal job alert script)"
MAX_INDIVIDUAL = 10  # per run; extra matches are summarised in one message


def load_env_file():
    """Load key-value pairs from .env if present (without third-party dependencies)."""
    env_file = HERE / ".env"
    if not env_file.is_file():
        return
    try:
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip().strip("'\"")
            if key and key not in os.environ:
                os.environ[key] = val
    except Exception:
        pass


def http_get(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def http_post(url, data, headers=None, timeout=20):
    req = urllib.request.Request(url, data=data, headers=headers or {}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


# ---------- Fetchers: each returns a list of {id, title, company, location, url} ----------

def fetch_greenhouse(slug, name):
    data = json.loads(http_get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"))
    return [
        {
            "id": str(j.get("id")),
            "title": j.get("title", ""),
            "company": name,
            "location": (j.get("location") or {}).get("name", ""),
            "url": j.get("absolute_url", ""),
        }
        for j in data.get("jobs", [])
    ]


def fetch_lever(slug, name):
    data = json.loads(http_get(f"https://api.lever.co/v0/postings/{slug}?mode=json"))
    return [
        {
            "id": str(j.get("id")),
            "title": j.get("text", ""),
            "company": name,
            "location": (j.get("categories") or {}).get("location", "") or "",
            "url": j.get("hostedUrl", ""),
        }
        for j in data
    ]


def fetch_ashby(slug, name):
    data = json.loads(http_get(f"https://api.ashbyhq.com/posting-api/job-board/{slug}"))
    out = []
    for j in data.get("jobs", []):
        if j.get("isListed") is False:
            continue
        out.append({
            "id": str(j.get("id")),
            "title": j.get("title", ""),
            "company": name,
            "location": j.get("location", "") or "",
            "url": j.get("jobUrl", ""),
        })
    return out


def _strip_ns(tag):
    return tag.rsplit("}", 1)[-1]


def fetch_feed(url, name):
    root = ET.fromstring(http_get(url))
    out = []
    for el in root.iter():
        if _strip_ns(el.tag) not in ("item", "entry"):
            continue
        f = {_strip_ns(c.tag): c for c in el}
        title = re.sub(r"<[^>]+>", "", (f["title"].text or "") if "title" in f else "").strip()
        link = ""
        if "link" in f:
            link = f["link"].get("href") or (f["link"].text or "")
        gid = (f["id"].text if "id" in f else None) or (f["guid"].text if "guid" in f else None) or link
        # Google Alerts wraps the real URL in a redirect
        m = re.search(r"[?&]url=([^&]+)", link)
        if m:
            link = urllib.parse.unquote(m.group(1))
        out.append({"id": gid or title, "title": title, "company": name, "location": "", "url": link})
    return out


FETCHERS = {"greenhouse": fetch_greenhouse, "lever": fetch_lever, "ashby": fetch_ashby}

URL_PATTERNS = [
    (r"(?:boards|job-boards)\.greenhouse\.io/([\w-]+)", "greenhouse"),
    (r"jobs\.lever\.co/([\w-]+)", "lever"),
    (r"jobs\.ashbyhq\.com/([\w%.-]+)", "ashby"),
]


# ---------- Filtering ----------

def compile_any(words):
    if not words:
        return None
    return re.compile("|".join(r"(?<!\w)" + re.escape(w) + r"(?!\w)" for w in words), re.I)


def matches(job, cfg, check_location=True):
    inc, exc = compile_any(cfg.get("include_title")), compile_any(cfg.get("exclude_title"))
    title = job["title"]
    if inc and not inc.search(title):
        return False
    if exc and exc.search(title):
        return False
    locs = cfg.get("locations")
    if check_location and locs and job["location"]:
        if not any(loc.lower() in job["location"].lower() for loc in locs):
            return False
    return True


# ---------- Notifications ----------

def notify(text, link=None, title="New job"):
    sent = False
    tok = os.getenv("TELEGRAM_BOT_TOKEN")
    chat = os.getenv("TELEGRAM_CHAT_ID")
    if tok and chat:
        body = urllib.parse.urlencode({
            "chat_id": chat,
            "text": text + (f"\n{link}" if link else ""),
            "disable_web_page_preview": "true",
        }).encode("utf-8")
        http_post(f"https://api.telegram.org/bot{tok}/sendMessage", body)
        sent = True
    topic = os.getenv("NTFY_TOPIC")
    if topic:
        h = {"Title": title.encode("ascii", "ignore").decode() or "New job"}
        if link:
            h["Click"] = link
        http_post(f"https://ntfy.sh/{topic}", text.encode("utf-8"), h)
        sent = True
    return sent


def load_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def add_company(url):
    cfg = load_json(CONFIG, {})
    for pat, ats in URL_PATTERNS:
        m = re.search(pat, url)
        if m:
            slug = m.group(1)
            entry = {"name": slug, "ats": ats, "slug": slug}
            if any(c["ats"] == ats and c["slug"] == slug for c in cfg.setdefault("companies", [])):
                print("Already in config.json")
                return
            cfg["companies"].append(entry)
            CONFIG.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
            print(f"Added {ats}:{slug}. Edit 'name' in config.json if you like.")
            return
    print("Couldn't recognise that URL. Supported: boards.greenhouse.io/<slug>, "
          "jobs.lever.co/<slug>, jobs.ashbyhq.com/<slug>.\n"
          "Open the company's careers page, click a job, and use the URL it lands on.")


def main(argv):
    load_env_file()

    if "--add" in argv:
        return add_company(argv[argv.index("--add") + 1])
    if "--test-notify" in argv:
        ok = notify("jobwatch test: alerts are working.", "https://example.com", "jobwatch test")
        print("sent" if ok else "No TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID or NTFY_TOPIC set.")
        return

    dry = "--dry-run" in argv
    cfg = load_json(CONFIG, {})
    state = load_json(STATE, {})
    new_matches, failures = [], []

    sources = [
        (f"{c['ats']}:{c['slug']}", c.get("name", c["slug"]), FETCHERS[c["ats"]], c["slug"], True)
        for c in cfg.get("companies", [])
        if c.get("ats") in FETCHERS
    ]
    sources += [
        (f"feed:{f['url']}", f.get("name", "feed"), fetch_feed, f["url"], False)
        for f in cfg.get("feeds", [])
    ]

    for key, name, fn, arg, check_loc in sources:
        try:
            jobs = fn(arg, name)
        except Exception as e:  # one bad source must not stop the rest
            failures.append(f"{key}: {e}")
            continue
        first_time = key not in state
        seen = set(state.get(key, []))
        for j in jobs:
            if j["id"] in seen:
                continue
            seen.add(j["id"])
            if not first_time and matches(j, cfg, check_loc):
                new_matches.append((key, j))
        state[key] = sorted(seen)
        if first_time:
            print(f"[baseline] {key}: recorded {len(jobs)} existing jobs (no alerts for these)")

    delivered = set()
    for i, (key, j) in enumerate(new_matches):
        line = f"{j['title']}\n{j['company']}" + (f" | {j['location']}" if j["location"] else "")
        if dry:
            print("MATCH:", line.replace("\n", " @ "), j["url"])
            continue
        if i >= MAX_INDIVIDUAL:
            break
        try:
            if notify(line, j["url"], f"New: {j['company']}"):
                delivered.add(j["id"])
            else:
                print("MATCH (no notifier configured):", line.replace("\n", " @ "), j["url"])
        except Exception as e:
            failures.append(f"notify failed: {e}")
            # un-see so it is retried next run
            state[key] = [x for x in state[key] if x != j["id"]]

    extra = new_matches[MAX_INDIVIDUAL:]
    if extra and not dry:
        try:
            notify(f"+{len(extra)} more matching jobs. Check the career pages.", None, "More jobs")
        except Exception as e:
            failures.append(f"notify failed: {e}")

    if not dry:
        STATE.write_text(json.dumps(state, indent=1) + "\n", encoding="utf-8")

    print(f"Done. {len(new_matches)} new matching job(s). {len(failures)} problem(s).")
    for f in failures:
        print("  WARN", f)


if __name__ == "__main__":
    main(sys.argv[1:])
