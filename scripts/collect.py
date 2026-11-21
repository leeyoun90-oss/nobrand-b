#!/usr/bin/env python3
"""트민두AI 원데이터 수집기 (AI 분야 전용)

수집 소스
  1. AI 기업 블로그 RSS  : OpenAI, Google DeepMind, Hugging Face
  2. TLDR AI 뉴스레터 RSS : 하루치 뉴스레터 1호 = 항목 1개
  3. GitHub Search API   : 최근 N일 안에 만들어진 AI 저장소 중 별이 많은 순

결과는 data/trends.json 에 저장합니다.
  - 같은 URL은 한 번만 저장합니다 (중복 제거).
  - 이미 저장된 항목의 status(검수 상태)는 덮어쓰지 않습니다.
    검수 담당이 "승인"/"제외"로 바꾼 값이 다음 수집 때도 유지됩니다.
  - 원문 요약문은 저장하지 않습니다 (저작권). 제목·링크·날짜만 저장하고,
    GitHub 저장소는 저장소 설명(description)을 함께 저장합니다.

외부 패키지 없이 파이썬 표준 라이브러리만 사용합니다.

사용법
  python scripts/collect.py                  # 기본: 최근 7일
  python scripts/collect.py --days 14        # 수집 기간 변경
  python scripts/collect.py --out data/trends.json
  GITHUB_TOKEN=... python scripts/collect.py # 토큰이 있으면 GitHub 요청 한도가 늘어납니다
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

KST = timezone(timedelta(hours=9))
USER_AGENT = "tmindu-ai-collector/1.0 (+https://github.com/leeyoun90-oss/nobrand-b)"

# ── 수집 소스 설정 ────────────────────────────────────────────────
# 소스를 추가하려면 이 목록에 한 줄을 더하면 됩니다.
RSS_SOURCES = [
    {"key": "openai", "name": "OpenAI", "type": "AI 기업 블로그", "url": "https://openai.com/news/rss.xml"},
    {"key": "deepmind", "name": "Google DeepMind", "type": "AI 기업 블로그", "url": "https://deepmind.google/blog/rss.xml"},
    {"key": "hf", "name": "Hugging Face", "type": "AI 기업 블로그", "url": "https://huggingface.co/blog/feed.xml"},
    {"key": "tldr", "name": "TLDR AI", "type": "뉴스레터", "url": "https://tldr.tech/api/rss/ai"},
]

# GitHub 저장소 주제(topic). 하나라도 붙어 있으면 AI 저장소로 봅니다.
GITHUB_TOPICS = ["llm", "ai-agents", "generative-ai", "large-language-models", "rag", "mcp"]
GITHUB_MIN_STARS = 30
GITHUB_PER_TOPIC = 15

# 앱의 기존 분류(tag)에 맞춘 간단한 키워드 분류. 위에서부터 먼저 맞는 것을 씁니다.
TAG_RULES = [
    ("개발 도구", ["agent", "sdk", "api", "framework", "library", "tool", "mcp", "code", "coding", "cli", "에이전트"]),
    ("리서치", ["research", "paper", "benchmark", "eval", "study", "arxiv", "연구"]),
    ("AI 모델", ["model", "gemini", "gpt", "llama", "claude", "release", "introducing", "모델"]),
]
DEFAULT_TAG = "AI 활용"

STATUS_PENDING = "검수 대기"
KEEP_DAYS = 30        # 이 기간이 지난 '검수 대기' 항목은 정리합니다 (승인된 항목은 유지)
TIMEOUT = 20


# ── 공통 도우미 ──────────────────────────────────────────────────
def fetch(url: str, headers: dict | None = None) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as res:
        return res.read()


def make_id(source_key: str, url: str) -> str:
    return f"{source_key}-{hashlib.sha1(url.encode()).hexdigest()[:10]}"


def to_date(value: str | None) -> str | None:
    """RSS(RFC 822)·Atom(ISO 8601) 날짜를 한국 시간 YYYY-MM-DD 로 바꿉니다."""
    if not value:
        return None
    value = value.strip()
    try:
        dt = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(KST).date().isoformat()


def classify(text: str) -> str:
    lower = text.lower()
    for tag, words in TAG_RULES:
        if any(w in lower for w in words):
            return tag
    return DEFAULT_TAG


def local(tag: str) -> str:
    """XML 네임스페이스를 떼고 태그 이름만 돌려줍니다."""
    return tag.rsplit("}", 1)[-1]


def child_text(el: ET.Element, name: str) -> str | None:
    for c in el:
        if local(c.tag) == name and c.text:
            return c.text.strip()
    return None


# ── RSS / Atom 수집 ─────────────────────────────────────────────
def parse_feed(xml_bytes: bytes) -> list[dict]:
    """RSS 2.0 과 Atom 을 모두 읽어 {title, url, published} 목록을 돌려줍니다."""
    root = ET.fromstring(xml_bytes)
    entries = []
    for el in root.iter():
        name = local(el.tag)
        if name == "item":  # RSS 2.0
            url = child_text(el, "link") or child_text(el, "guid")
            date = child_text(el, "pubDate") or child_text(el, "date")
        elif name == "entry":  # Atom
            url = None
            for c in el:
                if local(c.tag) == "link" and c.get("rel", "alternate") == "alternate":
                    url = c.get("href")
                    break
            date = child_text(el, "published") or child_text(el, "updated")
        else:
            continue
        title = child_text(el, "title")
        if title and url:
            entries.append({"title": " ".join(title.split()), "url": url.strip(), "published": to_date(date)})
    return entries


def collect_rss(source: dict, since: str) -> list[dict]:
    items = []
    for e in parse_feed(fetch(source["url"])):
        if e["published"] and e["published"] < since:
            continue
        items.append({
            "id": make_id(source["key"], e["url"]),
            "source": source["name"],
            "sourceKey": source["key"],
            "sourceType": source["type"],
            "title": e["title"],
            "url": e["url"],
            "published": e["published"],
            "tag": classify(e["title"]),
        })
    return items


# ── GitHub Search API 수집 ──────────────────────────────────────
def collect_github(since: str) -> list[dict]:
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    repos: dict[str, dict] = {}
    for topic in GITHUB_TOPICS:
        q = f"topic:{topic} created:>={since} stars:>={GITHUB_MIN_STARS} fork:false archived:false"
        url = "https://api.github.com/search/repositories?" + urllib.parse.urlencode(
            {"q": q, "sort": "stars", "order": "desc", "per_page": GITHUB_PER_TOPIC}
        )
        data = json.loads(fetch(url, headers))
        for r in data.get("items", []):
            repos.setdefault(r["html_url"], r)

    items = []
    seen_names: set[str] = set()
    seen_descs: set[str] = set()
    for r in sorted(repos.values(), key=lambda r: r["stargazers_count"], reverse=True):
        desc = (r.get("description") or "").strip()
        # 스팸 거르기: 저장소 이름이나 설명이 똑같은 복제본은 별이 가장 많은 하나만 남깁니다.
        name_key = r["name"].lower().strip("-_. ")
        desc_key = " ".join(desc.lower().split())
        if not desc_key or name_key in seen_names or desc_key in seen_descs:
            continue
        seen_names.add(name_key)
        seen_descs.add(desc_key)
        items.append({
            "id": make_id("github", r["html_url"]),
            "source": "GitHub",
            "sourceKey": "github",
            "sourceType": "GitHub 인기 저장소",
            "title": r["full_name"],
            "url": r["html_url"],
            "published": to_date(r.get("created_at")),
            "tag": classify(f'{r["full_name"]} {desc} {" ".join(r.get("topics", []))}'),
            "description": desc[:300],
            "stars": r["stargazers_count"],
            "language": r.get("language"),
            "topics": r.get("topics", [])[:8],
        })
    return items


# ── 병합·저장 ───────────────────────────────────────────────────
def merge(existing: list[dict], fresh: list[dict], now: str) -> list[dict]:
    by_url = {it["url"]: it for it in existing}
    for it in fresh:
        old = by_url.get(it["url"])
        if old:
            # 검수 상태·처음 수집일은 유지하고, 별 개수 같은 값만 갱신합니다.
            it["status"] = old.get("status", STATUS_PENDING)
            it["collectedAt"] = old.get("collectedAt", now)
            for k in ("note", "reviewedBy"):
                if k in old:
                    it[k] = old[k]
        else:
            it["status"] = STATUS_PENDING
            it["collectedAt"] = now
        by_url[it["url"]] = it

    cutoff = (datetime.now(KST) - timedelta(days=KEEP_DAYS)).date().isoformat()
    kept = [
        it for it in by_url.values()
        if it.get("status") != STATUS_PENDING or (it.get("published") or it["collectedAt"][:10]) >= cutoff
    ]
    return sorted(kept, key=lambda it: (it.get("published") or "", it.get("stars", 0)), reverse=True)


def main() -> int:
    ap = argparse.ArgumentParser(description="트민두AI 원데이터 수집기 (AI 분야)")
    ap.add_argument("--days", type=int, default=7, help="최근 며칠 치를 수집할지 (기본 7)")
    ap.add_argument("--out", default="data/trends.json", help="저장할 파일 경로")
    args = ap.parse_args()

    now_dt = datetime.now(KST)
    now = now_dt.isoformat(timespec="seconds")
    since = (now_dt - timedelta(days=args.days)).date().isoformat()

    fresh: list[dict] = []
    report: dict[str, str] = {}
    jobs = [(s["name"], lambda s=s: collect_rss(s, since)) for s in RSS_SOURCES]
    jobs.append(("GitHub", lambda: collect_github(since)))
    for name, job in jobs:
        try:
            got = job()
            fresh.extend(got)
            report[name] = f"{len(got)}건"
        except (urllib.error.URLError, ET.ParseError, ValueError, KeyError, TimeoutError) as e:
            # 한 소스가 실패해도 나머지는 계속 수집합니다.
            report[name] = f"실패 ({e.__class__.__name__}: {e})"

    out = Path(args.out)
    existing = []
    if out.exists():
        try:
            existing = json.loads(out.read_text(encoding="utf-8")).get("items", [])
        except (json.JSONDecodeError, AttributeError):
            print(f"경고: {out} 을 읽지 못해 새로 만듭니다.", file=sys.stderr)

    items = merge(existing, fresh, now)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "updatedAt": now,
        "since": since,
        "sources": report,
        "count": len(items),
        "items": items,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"수집 기간: {since} ~ {now_dt.date().isoformat()}")
    for name, r in report.items():
        print(f"  - {name}: {r}")
    print(f"저장: {out} (총 {len(items)}건)")
    # 모든 소스가 실패했을 때만 오류로 끝냅니다.
    return 0 if any(not r.startswith("실패") for r in report.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
