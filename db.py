# db.py
import sqlite3
import json
from pathlib import Path
from typing import Any, Dict, Optional

DB_PATH = Path("smartmirror.db")


def conn() -> sqlite3.Connection:
    # 요청마다 새 커넥션 (가벼움, thread-safe 쪽으로 유리)
    c = sqlite3.connect(DB_PATH)
    c.execute("PRAGMA journal_mode=WAL;")  # 동시성/안정성 개선
    return c


def init_db():
    with conn() as c:
        # (기존) 이벤트 로그
        c.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            event_name TEXT NOT NULL,
            metadata_json TEXT NOT NULL
        )""")

        # (추가) 텔레메트리 로그
        c.execute("""
        CREATE TABLE IF NOT EXISTS telemetry (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            request_id TEXT NOT NULL,
            session_id TEXT,
            device_id TEXT,
            method TEXT,
            path TEXT,
            status_code INTEGER,
            latency_ms INTEGER,
            success INTEGER,
            error_message TEXT
        )""")

        # (기존) 간단 통계/카운터 저장
        c.execute("""
        CREATE TABLE IF NOT EXISTS stats (
            k TEXT PRIMARY KEY,
            v TEXT NOT NULL
        )""")

        defaults = {
            "avg_departure_hhmm": "08:10",
            "late_count_7days": "0",
            "rain_cnt": "0",
            "rain_umbrella_missed_cnt": "0",
            "miss_car_key": "0",
            "miss_wallet": "0",
            "miss_phone": "0",
            "miss_umbrella": "0",
        }
        # 사용자별 외출 점수 가중치
        c.execute("""
        CREATE TABLE IF NOT EXISTS user_weights (
            user_id TEXT PRIMARY KEY,
            w_traffic REAL,
            w_condition REAL,
            w_item REAL,
            w_weather REAL,
            updated_ts TEXT
        )
        """)




        for k, v in defaults.items():
            c.execute("INSERT OR IGNORE INTO stats(k,v) VALUES(?,?)", (k, v))


def log_event(ts_iso: str, event_name: str, metadata_json: str):
    with conn() as c:
        c.execute(
            "INSERT INTO events(ts,event_name,metadata_json) VALUES (?,?,?)",
            (ts_iso, event_name, metadata_json)
        )


def log_event_dict(ts_iso: str, event_name: str, metadata: Dict[str, Any]):
    # 개인정보/민감정보는 원문 저장 지양(가이드라인 준수)
    safe_json = json.dumps(metadata, ensure_ascii=False)
    log_event(ts_iso, event_name, safe_json)


def get_stat(k: str, default: str = "0") -> str:
    with conn() as c:
        row = c.execute("SELECT v FROM stats WHERE k=?", (k,)).fetchone()
    return row[0] if row else default


def set_stat(k: str, v: str):
    with conn() as c:
        c.execute(
            "INSERT INTO stats(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v",
            (k, v)
        )


def log_telemetry(
    ts_iso: str,
    request_id: str,
    session_id: Optional[str],
    device_id: Optional[str],
    method: str,
    path: str,
    status_code: int,
    latency_ms: int,
    success: bool,
    error_message: Optional[str] = None,
):
    # error_message는 스택/민감정보 없이 짧게(마스킹/요약)
    if error_message and len(error_message) > 160:
        error_message = error_message[:160] + "..."

    with conn() as c:
        c.execute("""
            INSERT INTO telemetry(
              ts, request_id, session_id, device_id, method, path,
              status_code, latency_ms, success, error_message
            ) VALUES (?,?,?,?,?,?,?,?,?,?)
        """, (
            ts_iso, request_id, session_id, device_id, method, path,
            status_code, int(latency_ms), 1 if success else 0, error_message
        ))
def get_user_weights(user_id: str) -> dict:
    with conn() as c:
        row = c.execute("""
            SELECT w_traffic, w_condition, w_item, w_weather
            FROM user_weights
            WHERE user_id=?
        """, (user_id,)).fetchone()

    # 처음 쓰는 사용자 → 기본 가중치
    if not row:
        return {
            "w_traffic": 1.0,
            "w_condition": 1.0,
            "w_item": 1.0,
            "w_weather": 1.0,
        }

    return {
        "w_traffic": row[0],
        "w_condition": row[1],
        "w_item": row[2],
        "w_weather": row[3],
    }
