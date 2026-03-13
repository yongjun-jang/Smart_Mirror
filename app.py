from flask import Flask, render_template, jsonify, request, Response, session
from datetime import datetime
import threading
import time
import pytz
import cv2
import numpy as np
import uuid
import os

from config import Config
from db import init_db, log_event, log_event_dict, log_telemetry
from cv.condition_cv import ConditionEstimatorCV
# policy 모듈은 ui_mode 결정을 위해 유지하거나, 필요 없다면 제거 가능합니다.
from logic.policy import apply_policy

# 기존 import 하단에 추가
from services.kakao_mobility import get_taxi_time
from services.openweather import get_openweather
from services.tago import get_nearby_stops, get_arrivals_by_stop
from services.calendar_core import get_todays_events, today_kst
import os

app = Flask(__name__, template_folder="web/templates", static_folder="web/static")
app.secret_key = "mirror_secret_key_1234"
init_db()
# ===============================
# 데이터 드리븐용 자동 로그 (UI 변경 없음)
# ===============================

def get_device_id():
    return os.environ.get("DEVICE_ID", "raspberrypi")

@app.before_request
def before_request():
    request._start_time = time.time()
    request.request_id = uuid.uuid4().hex

    if "session_id" not in session:
        session["session_id"] = uuid.uuid4().hex

@app.after_request
def after_request(response):
    try:
        if request.path.startswith("/static"):
            return response

        latency_ms = int((time.time() - request._start_time) * 1000)

        log_telemetry(
            ts_iso=datetime.now(tz).isoformat(),
            request_id=request.request_id,
            session_id=session.get("session_id"),
            device_id=get_device_id(),
            method=request.method,
            path=request.path,
            status_code=response.status_code,
            latency_ms=latency_ms,
            success=200 <= response.status_code < 400,
            error_message=None
        )
    except Exception:
        pass

    return response


tz = pytz.timezone(Config.TZ)

# ====== 글로벌 공유 자원 ======
cv_lock = threading.Lock()
cv_state = {
    "state": "noface",
    "face_detected": False,
    "blink_per_min": 0.0,
    "closed_ratio_10s": 1.0,
    "head_motion_std": 0.0,
    "last_update_ts": 0.0
}
latest_frame = None 

# 라즈베리파이로부터 영상을 받는 입구
@app.route('/upload_frame', methods=['POST'])
def upload_frame():
    global latest_frame
    try:
        # 헤더에서 사용자 ID 추출 및 세션 저장
        user_id = request.headers.get('User-ID', 'Unknown')
        if user_id != "Unknown":
            session['user_id'] = user_id

        img_byte = request.data
        nparr = np.frombuffer(img_byte, np.uint8)
        latest_frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        return "OK", 200
    except Exception as e:
        return str(e), 500

# ====== CV 스레드 (피로도 분석) ======
def cv_loop():
    global latest_frame
    est = ConditionEstimatorCV() 
    
    while True:
        # 전역 변수에 저장된 프레임을 분석기로 전달
        st = est.step(external_frame=latest_frame) 
        
        with cv_lock:
            cv_state.update({
                "state": st.state,
                "face_detected": st.face_detected,
                "blink_per_min": st.blink_per_min,
                "closed_ratio_10s": st.closed_ratio_10s,
                "head_motion_std": st.head_motion_std,
                "last_update_ts": st.last_update_ts
            })
        time.sleep(0.1)

threading.Thread(target=cv_loop, daemon=True).start()

# ====== 영상 송출 (브라우저 전송) ======
@app.route('/video_feed')
def video_feed():
    def generate():
        global latest_frame
        while True:
            if latest_frame is not None:
                frame = cv2.flip(latest_frame, 1)
                ret, buffer = cv2.imencode('.jpg', frame)
                if ret:
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
            time.sleep(0.1)
    return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route("/")
def dashboard():
    current_user = session.get('user_id', 'Unknown')
    now = datetime.now(tz)

    with cv_lock:
        cond = dict(cv_state)

    # UI 모드 결정을 위한 최소한의 정책 적용
    policy = apply_policy(cond["state"])

    # [핵심] 피로도 데이터만 HTML로 전송 (날씨, 버스, 리스크 등 모두 제거)
    return render_template(
        "dashboard.html",
        current_user=current_user,
        now=now.strftime("%Y-%m-%d %H:%M"),
        cond=cond,
        policy=policy
    )

#===============================추가================================

# ===================================================================
# 외출 모드 시퀀스 (교통 -> 할 일 -> 날씨 -> 소지품)
# ===================================================================

# 1단계: 교통 정보 페이지 (시작점)
@app.route("/traffic", methods=["GET", "POST"])
def traffic_page():
    now = datetime.now(tz)
    
    # [버스 정보] TAGO 서비스 연동
    eta_min = None
    chosen_stop = None
    arrivals_preview = []
    try:
        near = get_nearby_stops(Config.TAGO_SERVICE_KEY, Config.BUS_STOP_LAT, Config.BUS_STOP_LON, num_rows=1)
        if near.get("ok") and near["stops"]:
            chosen_stop = near["stops"][0]
            arr = get_arrivals_by_stop(Config.TAGO_SERVICE_KEY, Config.TAGO_CITY_CODE, chosen_stop["nodeId"])
            eta_min = arr.get("eta_min")
            arrivals_preview = (arr.get("arrivals") or [])[:5]
    except Exception as e:
        print(f"Bus API Error: {e}")

    # [택시 정보] 카카오 모빌리티
    # [택시 정보] 카카오 모빌리티 (사용자 선택 목적지 기준)
    dest = session.get("destination")

    taxi = None
    dest_name = "목적지 미설정"

    if dest and dest.get("lat") and dest.get("lon"):
        taxi = get_taxi_time(
            Config.KAKAO_REST_API_KEY,
            Config.HOME_LAT, Config.HOME_LON,
            dest["lat"], dest["lon"]
        )
        dest_name = dest.get("name", dest_name)



    return render_template(
        "traffic.html", 
        now=now.strftime("%H:%M"),
        taxi=taxi,
        dest_name=dest_name,
        stop=chosen_stop,
        eta_min=eta_min,
        arrivals_preview=arrivals_preview
    )

# 2단계: 할 일 체크 (traffic.html에서 이동)
@app.route("/todo")
def todo_page():
    ics_url = os.environ.get("SMARTMIRROR_ICS_URL", "").strip()
    if not ics_url:
        return "ICS URL이 설정되지 않았습니다.", 400
    
    events = get_todays_events(ics_url)
    return render_template(
        "todo.html",
        events=events,
        today=today_kst().strftime("%Y-%m-%d"),
        now=datetime.now(tz).strftime("%H:%M")
    )

# 3단계: 날씨 체크 (todo.html에서 이동)
@app.route("/weather")
def weather_page():
    now = datetime.now(tz)
    weather = get_openweather(Config.OWM_API_KEY, Config.HOME_LAT, Config.HOME_LON)
    
    precip_prob = float(weather.get("precip_prob", 0.0)) if weather.get("ok") else 0.0
    briefing = {
        "action_points": [
            "기상 정보를 확인하고 마지막 소지품을 점검하세요.",
            "오늘도 안전하고 즐거운 하루 되세요!"
        ]
    }

    return render_template(
        "weather.html",
        now=now.strftime("%m월 %d일 %H:%M"),
        weather=weather if weather.get("ok") else {"temp": None, "feels_like": None, "humidity": 0, "weather_desc": "데이터 오류"},
        precip_prob=precip_prob,
        briefing=briefing
    )

# 4단계: 소지품 체크 (weather.html에서 이동 - 최종 단계)
@app.route("/checklist")
def checklist_page():
    # 날씨 상태(비/눈)에 따라 우산 항목을 동적으로 보여주기 위해 날씨 정보 참조
    weather = get_openweather(Config.OWM_API_KEY, Config.HOME_LAT, Config.HOME_LON)
    precip_prob = float(weather.get("precip_prob", 0.0)) if weather.get("ok") else 0.0
    
    # (주의) 여기 체크리스트 DB 로직은 프로젝트 상태에 따라 다를 수 있어.
    # 지금 메이커톤 우선순위는 교통 확률이므로, 기존 코드 유지.
    import sqlite3
    DB_PATH = "checklist.db"

    # DB에서 사용자 등록 소지품 가져오기
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        items = conn.execute("SELECT * FROM items ORDER BY miss DESC").fetchall()
    
    return render_template(
        "checklist.html",
        weather=weather,
        precip_prob=precip_prob,
        user_items=[dict(i) for i in items]
    )
# ===============================
# 소지품 체크 완료 API (점수 계산용)
# ===============================

@app.route("/api/checklist_done", methods=["POST"])
def api_checklist_done():
    data = request.get_json(silent=True) or {}

    total = int(data.get("total", 0))
    done = int(data.get("done", 0))

    if total > 0:
        ratio = done / total
        item_score = int(ratio * 20)  # 0~20
    else:
        item_score = 20

    # ✅ session에 저장 (departure_score에서 사용)
    session["item_score"] = item_score
    session["item_total"] = total
    session["item_done"] = done

    return jsonify({"ok": True, "item_score": item_score})

# ===================================================================
# 보조 API 및 인터랙션
# ===================================================================

@app.route("/api/todo/complete", methods=["POST"])
def complete_todo():
    return jsonify({"ok": True})

@app.route("/api/interaction", methods=['POST'])
def handle_user_interaction():
    data = request.get_json(silent=True) or {}

    log_event_dict(
        ts_iso=datetime.now(tz).isoformat(),
        event_name="ui_interaction",
        metadata={
            "session_id": session.get("session_id"),
            "device_id": get_device_id(),
            "event_type": data.get("type", "touch"),
            "path": request.referrer or request.path,
        }
    )

    return jsonify({"status": "success"}), 200


# 목적지 검색 및 확률 계산 API (기존 유지)
# ... api_search_destination 및 api_commute_prob 코드 ...

# 2. app.js의 목적지 검색 자동완성을 위한 API
@app.route("/api/search_destination")
def api_search_destination():
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify({"ok": False, "error": "검색어가 없습니다"})
    
    # 카카오 로컬 API를 사용하여 장소 검색
    from services.kakao_local import search_keyword
    search_result = search_keyword(Config.KAKAO_REST_API_KEY, query, x=Config.HOME_LON, y=Config.HOME_LAT)
    
    if not search_result.get("ok") or not search_result.get("places"):
        return jsonify({"ok": False, "error": "검색 결과 없음"})
    
    # 검색된 첫 번째 장소를 기준으로 택시 소요 시간 계산
    place = search_result["places"][0]


    taxi_result = get_taxi_time(
        Config.KAKAO_REST_API_KEY, 
        Config.HOME_LAT, Config.HOME_LON, 
        place["lat"], place["lon"]
    )
    
    return jsonify({
        "ok": True,
        "destination": {
            "name": place["name"], 
            "address": place["address"], 
            "lat": place["lat"], 
            "lon": place["lon"]
        },
        "taxi": taxi_result if taxi_result.get("ok") else None,
        "all_places": search_result["places"]
    })
@app.route("/api/set_destination", methods=["POST"])
def api_set_destination():
    data = request.get_json(silent=True) or {}

    session["destination"] = {
        "lat": float(data.get("lat")),
        "lon": float(data.get("lon")),
        "name": data.get("name", "목적지")
    }

    session["arrive_hhmm"] = data.get("arrive_hhmm")

    return jsonify({"ok": True})

@app.route("/api/commute_probability", methods=["POST"])
def api_commute_prob():
    """UI(traffic.html/app.js)에서 호출하는 '정시 도착 확률' API

    ✅ 반드시 dict(JSON)로 내려가야 프론트에서 확률이 표시됩니다.
    ✅ 택시 시간은 카카오 모빌리티 API로 실시간 계산합니다.
    ✅ 버스 대기시간은 TAGO 정류장 도착정보에서 가장 빠른 ETA를 사용(없으면 평균값으로 근사).
    """
    from logic.commute_probability import compute_probabilities

    data = request.get_json(silent=True) or {}
    arrive_hhmm = (data.get("arrive_hhmm") or "").strip()   # "09:00"
    dest = data.get("dest") or {}
    dest_lat = float(dest.get("lat") or 0.0)
    dest_lon = float(dest.get("lon") or 0.0)

    # 1) 남은 시간(time_budget) 계산
    now = datetime.now(tz)
    time_budget_min = None
    if arrive_hhmm:
        try:
            target_time = datetime.strptime(arrive_hhmm, "%H:%M").replace(
                year=now.year, month=now.month, day=now.day
            )
            target_time = tz.localize(target_time)
            time_budget_min = (target_time - now).total_seconds() / 60.0
            if time_budget_min < 0:
                # 입력 시간이 이미 지났으면 '내일'로 간주
                time_budget_min += 1440.0
        except Exception:
            time_budget_min = None

    if time_budget_min is None:
        time_budget_min = 30.0  # 안전 기본값

    # 2) 택시 시간/거리 (카카오 모빌리티)
    taxi = None
    taxi_duration_min = None
    taxi_distance_m = None
    if dest_lat and dest_lon:
        taxi = get_taxi_time(
            Config.KAKAO_REST_API_KEY,
            Config.HOME_LAT, Config.HOME_LON,
            dest_lat, dest_lon
        )
        if taxi.get("ok"):
            taxi_duration_min = float(taxi.get("duration_min") or 0.0)
            taxi_distance_m = float(taxi.get("distance_meter") or 0.0)

    # 3) 버스 ETA (TAGO) - 미리 지정한 기준 정류장 위치(BUS_STOP_LAT/LON) 사용
    bus_wait_min = None
    bus_available = False
    try:
        near = get_nearby_stops(Config.TAGO_SERVICE_KEY, Config.BUS_STOP_LAT, Config.BUS_STOP_LON, num_rows=1)
        if near.get("ok") and near.get("stops"):
            chosen_stop = near["stops"][0]
            arr = get_arrivals_by_stop(Config.TAGO_SERVICE_KEY, Config.TAGO_CITY_CODE, chosen_stop["nodeId"])
            if arr.get("ok"):
                bus_available = True
                bus_wait_min = arr.get("eta_min")  # 가장 빠른 도착(분)
    except Exception as e:
        print(f"[commute_probability] bus ETA error: {e}")

    # 4) 지하철 대기시간: (현재 프로젝트에 역 ID가 없으므로) None 처리
    subway_wait_min = None
    subway_available = False

    # 5) 확률 계산
    probs = compute_probabilities(
        time_budget_min=float(time_budget_min),
        taxi_duration_min=taxi_duration_min,
        taxi_distance_m=taxi_distance_m,
        bus_wait_min=bus_wait_min,
        subway_wait_min=subway_wait_min,
        bus_available=bus_available,
        subway_available=subway_available,
        current_hour=now.hour
    )
    session["last_probabilities"] = probs

    return jsonify({
        "ok": True,
        "now": now.strftime("%H:%M"),
        "time_budget_min": float(time_budget_min),
        "arrive_hhmm": arrive_hhmm,
        "destination": {"lat": dest_lat, "lon": dest_lon},
        "taxi": taxi if taxi else {"ok": False, "error": "택시 정보 없음"},
        "probabilities": probs
    })
@app.route("/api/taxi_preview")
def taxi_preview():
    dest = session.get("destination")
    if not dest:
        return {"ok": False}

    taxi = get_taxi_time(
        Config.KAKAO_REST_API_KEY,
        Config.HOME_LAT, Config.HOME_LON,
        dest["lat"], dest["lon"]
    )

    return {
        "ok": True,
        "name": dest.get("name"),
        "minutes": taxi.get("minutes"),
        "fare": taxi.get("fare"),
        "distance": taxi.get("distance")
    }

# ===============================
# 외출 성공 점수 페이지
# ===============================

@app.route("/departure_score")
def departure_score():

    # ---------------------------
    # 1) 교통 확률 (0~100) -> 교통 점수 (0~45)
    # ---------------------------
    traffic = session.get("last_probabilities", {})
    best_prob = 0
    for mode in ["taxi", "bus", "subway"]:
        p = traffic.get(mode, {}).get("p_on_time", 0)
        best_prob = max(best_prob, int(float(p) * 100))

    traffic_score = int(best_prob * 0.45)  # 0~45

    # ---------------------------
    # 2) 컨디션 점수 (0~25)
    # ---------------------------
    with cv_lock:
        state = cv_state.get("state", "normal")

    if state == "tired":
        cond_score = 8
        comment = "최근 컨디션을 반영해 안전 위주의 외출을 권장합니다."
    elif state == "good":
        cond_score = 25
        comment = "컨디션 상태가 좋아 여유 있는 외출이 가능합니다."
    else:
        cond_score = 16
        comment = "최근 외출 기록을 기준으로 무난한 컨디션입니다."

    # ---------------------------
    # 3) 소지품 준비도 (0~20)
    #   - 기존 DB 방식 유지(부하 매우 작음: COUNT 2번)
    # ---------------------------
    item_score = session.get("item_score", 0)

    # ---------------------------
    # 4) 날씨 리스크 (0 ~ -10)
    # ---------------------------
    weather_penalty = 0
    try:
        weather = get_openweather(Config.OWM_API_KEY, Config.HOME_LAT, Config.HOME_LON)
        precip = float(weather.get("precip_prob", 0) or 0)

        if precip >= 70:
            weather_penalty = 10
        elif precip >= 40:
            weather_penalty = 6
        elif precip >= 20:
            weather_penalty = 3
        else:
            weather_penalty = 0
    except Exception:
        weather_penalty = 0

    # ---------------------------
    # 5) 최종 점수 (0~100)
    # ---------------------------
    # ---------------------------
    # 5) 최종 점수 (0~100) - 사용자별 가중치 적용
    # ---------------------------


    final_score = traffic_score + cond_score + item_score - weather_penalty
    final_score = max(0, min(100, int(final_score)))


    # ---------------------------
    # 6) 점수 구간별 코멘트(아이디어2 강화)
    # ---------------------------
    if final_score >= 85:
        advice = "✅ 외출하기 좋은 상태입니다. 평소 루틴대로 진행하세요."
    elif final_score >= 70:
        advice = "🟡 무난하지만 변수가 있습니다. 체크리스트를 한 번 더 확인하세요."
    elif final_score >= 55:
        advice = "🟠 지연/실수 위험이 있습니다. 여유 출발 또는 대체 수단을 권장합니다."
    else:
        advice = "🔴 오늘은 리스크가 큽니다. 출발 시간을 조정하거나 계획 변경을 고려하세요."


    return render_template(
        "departure_score.html",
        score=final_score,
        comment=comment,
        advice=advice,
        best_prob=best_prob,
        traffic_score=traffic_score,
        cond_score=cond_score,
        item_score=item_score,
        weather_penalty=weather_penalty
    )


#===================================================================

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=False)
