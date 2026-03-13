import os
import json
import hashlib
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple

import requests
from icalendar import Calendar
import recurring_ical_events
from dateutil import tz


KST = tz.gettz("Asia/Seoul")
DEFAULT_TIMEOUT_SEC = 15

LOG_DIR = "logs"
OUTCOME_LOG_PATH = os.path.join(LOG_DIR, "task_outcomes.jsonl")
CACHE_PATH = os.path.join(LOG_DIR, "ics_cache.ics")
CACHE_META_PATH = os.path.join(LOG_DIR, "ics_cache_meta.json")

FAIL_REASONS = [
    "깜빡함",
    "시간 부족",
    "준비물 없음",
    "피곤함",
    "교통 지연",
    "기타(직접 입력)",
]


def ensure_dirs():
    os.makedirs(LOG_DIR, exist_ok=True)


def now_kst() -> datetime:
    return datetime.now(tz=KST)


def today_kst() -> date:
    return now_kst().date()


def dt_to_kst(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=KST)
    return dt.astimezone(KST)


def safe_str(x) -> str:
    return "" if x is None else str(x)


def stable_task_id(uid: str, start_dt: Optional[datetime], summary: str) -> str:
    base = f"{uid}|{safe_str(start_dt)}|{summary}"
    h = hashlib.sha1(base.encode("utf-8")).hexdigest()[:12]
    return f"cal_ics_{h}"


def load_json(path: str) -> Optional[dict]:
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: str, obj: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def fetch_ics(ics_url: str, use_cache: bool = True) -> bytes:
    """
    Conditional GET with ETag/Last-Modified when possible.
    Very low load.
    """
    ensure_dirs()
    headers = {}

    meta = load_json(CACHE_META_PATH) if use_cache else None
    if meta:
        if meta.get("etag"):
            headers["If-None-Match"] = meta["etag"]
        if meta.get("last_modified"):
            headers["If-Modified-Since"] = meta["last_modified"]

    r = requests.get(ics_url, headers=headers, timeout=DEFAULT_TIMEOUT_SEC)

    if r.status_code == 304 and use_cache and os.path.exists(CACHE_PATH):
        with open(CACHE_PATH, "rb") as f:
            return f.read()

    r.raise_for_status()

    if use_cache:
        with open(CACHE_PATH, "wb") as f:
            f.write(r.content)
        save_json(CACHE_META_PATH, {
            "fetched_at": now_kst().isoformat(),
            "etag": r.headers.get("ETag"),
            "last_modified": r.headers.get("Last-Modified"),
            "status_code": r.status_code,
        })

    return r.content


def parse_ics(ics_bytes: bytes) -> Calendar:
    return Calendar.from_ical(ics_bytes)


def event_time_range(evt) -> Tuple[Optional[datetime], Optional[datetime], bool]:
    """
    Returns (start_dt, end_dt, all_day)
    """
    dtstart = evt.get("DTSTART")
    dtend = evt.get("DTEND")

    if not dtstart:
        return None, None, False

    start_val = dtstart.dt
    end_val = dtend.dt if dtend else None

    # all-day: date object
    if isinstance(start_val, date) and not isinstance(start_val, datetime):
        start_dt = datetime.combine(start_val, datetime.min.time()).replace(tzinfo=KST)
        if isinstance(end_val, date) and not isinstance(end_val, datetime):
            end_dt = datetime.combine(end_val, datetime.min.time()).replace(tzinfo=KST)
        else:
            end_dt = start_dt + timedelta(days=1)
        return start_dt, end_dt, True

    # datetime
    start_dt = dt_to_kst(start_val) if isinstance(start_val, datetime) else None
    if start_dt is None:
        return None, None, False

    if end_val is None:
        end_dt = None
    elif isinstance(end_val, datetime):
        end_dt = dt_to_kst(end_val)
    else:
        end_dt = datetime.combine(end_val, datetime.min.time()).replace(tzinfo=KST)

    return start_dt, end_dt, False


def get_todays_events(ics_url: str, target_day: Optional[date] = None) -> List[Dict]:
    """
    Fetch + parse + expand recurrences, return today's events (KST).
    """
    if target_day is None:
        target_day = today_kst()

    ics_bytes = fetch_ics(ics_url, use_cache=True)
    cal = parse_ics(ics_bytes)

    day_start = datetime.combine(target_day, datetime.min.time()).replace(tzinfo=KST)
    day_end = day_start + timedelta(days=1)

    expanded = recurring_ical_events.of(cal).between(day_start, day_end)

    events: List[Dict] = []
    for evt in expanded:
        summary = safe_str(evt.get("SUMMARY")) or "(제목 없음)"
        uid = safe_str(evt.get("UID"))
        location = safe_str(evt.get("LOCATION"))
        description = safe_str(evt.get("DESCRIPTION"))

        start_dt, end_dt, all_day = event_time_range(evt)
        if start_dt is None:
            continue

        # overlap check
        if end_dt is None:
            if not (day_start <= start_dt < day_end):
                continue
        else:
            if not (start_dt < day_end and end_dt > day_start):
                continue

        task_id = stable_task_id(uid, start_dt, summary)
        events.append({
            "task_id": task_id,
            "uid": uid,
            "title": summary,
            "start": start_dt,
            "end": end_dt,
            "all_day": all_day,
            "location": location,
            "description": description,
            "source": "google_ics",
        })

    # sort: all-day first, then time
    events.sort(key=lambda e: (0 if e["all_day"] else 1, e["start"]))
    return events


def format_event_line(e: Dict) -> str:
    if e["all_day"]:
        return f"(종일) {e['title']}"
    start = e["start"].strftime("%H:%M")
    end = e["end"].strftime("%H:%M") if e["end"] else "?"
    return f"{start}~{end}  {e['title']}"


def brief_today_summary(events: List[Dict], max_items: int = 3) -> str:
    if not events:
        return "오늘은 등록된 일정이 없어요."
    titles = [e["title"] for e in events]
    brief = " / ".join(titles[:max_items]) + (" ..." if len(titles) > max_items else "")
    return f"오늘 할 일: {brief}"


def append_outcome_log(record: Dict) -> None:
    ensure_dirs()
    with open(OUTCOME_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def load_outcome_logs(days: int = 7) -> List[Dict]:
    if not os.path.exists(OUTCOME_LOG_PATH):
        return []
    cutoff = now_kst() - timedelta(days=days)
    rows = []
    with open(OUTCOME_LOG_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
                ts = datetime.fromisoformat(r["timestamp"])
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=KST)
                if ts >= cutoff:
                    rows.append(r)
            except Exception:
                continue
    return rows


def summarize_failures(days: int = 7) -> str:
    logs = load_outcome_logs(days=days)
    fails = [r for r in logs if r.get("completed") is False]
    if not fails:
        return f"최근 {days}일 동안 기록된 실패가 없어요."

    # recency-weighted (very light)
    reason_score: Dict[str, float] = {}
    reason_count: Dict[str, int] = {}
    today = now_kst().date()

    for r in fails:
        ts = datetime.fromisoformat(r["timestamp"])
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=KST)
        age_days = max(0, min(6, (today - ts.date()).days))
        weight = 1.0 - (age_days * 0.12)
        reason = r.get("reason", "알 수 없음")
        reason_score[reason] = reason_score.get(reason, 0.0) + weight
        reason_count[reason] = reason_count.get(reason, 0) + 1

    top_reason = max(reason_score.items(), key=lambda x: x[1])[0]
    top_cnt = reason_count[top_reason]

    title_count: Dict[str, int] = {}
    for r in fails:
        if r.get("reason") == top_reason:
            t = r.get("task_title", "(제목 없음)")
            title_count[t] = title_count.get(t, 0) + 1
    top_title = max(title_count.items(), key=lambda x: x[1])[0] if title_count else ""

    intervention_map = {
        "깜빡함": "출발 직전에 재확인 알림을 띄울게요.",
        "시간 부족": "다음엔 10분 일찍 출발하는 걸 제안할게요.",
        "준비물 없음": "전날 밤 준비물 체크를 띄울게요.",
        "피곤함": "중요 일정만 우선 안내하고 정보량을 줄일게요.",
        "교통 지연": "교통 상황 확인 후 출발 시각을 조정해볼게요.",
    }
    intervention = intervention_map.get(top_reason, "다음에는 실패를 줄일 수 있게 도와줄게요.")

    if top_title:
        return f"최근 {days}일 실패 원인 1위는 '{top_reason}'({top_cnt}회)이에요. '{top_title}' 같은 일정은 {intervention}"
    return f"최근 {days}일 실패 원인 1위는 '{top_reason}'({top_cnt}회)이에요. {intervention}"