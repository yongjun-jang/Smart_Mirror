import cv2
import requests
import time
import face_recognition
import pickle
import os
import threading
from flask import Flask

limit=40

# --- [신규 추가] 종료 제어를 위한 Flask 설정 ---
app = Flask(__name__)
should_stop = False

@app.route('/stop')
def stop_stream():
    global should_stop
    should_stop = True
    print("\n[SIGNAL] 카메라 종료 요청 수신!") 
    return "OK"

def run_server():
    app.run(host='0.0.0.0', port=5000)

threading.Thread(target=run_server, daemon=True).start()

# --- 1. 얼굴 식별 설정 ---
PKL_PATH = "/home/hardcarry/mirror/registered_faces.pkl"
known_encodings = []
known_names = []

if os.path.exists(PKL_PATH):
    with open(PKL_PATH, "rb") as f:
        data = pickle.load(f)
        known_encodings = data["encodings"]
        known_names = data["names"]
    print(f"얼굴 데이터 로드 완료: {len(known_names)}명")
else:
    print("경고: registered_faces.pkl 파일이 없습니다. 식별 없이 진행합니다.")

identified_user = "Unknown"
is_identified = False  
start_time = None  # [추가] 타이머 측정을 위한 변수

# --- 2. AWS 서버 설정 ---
AWS_IP = "15.164.225.121" 
BASE_URL = f"http://{AWS_IP}:8080/upload_frame"

# --- 3. 카메라 설정 ---
cap = cv2.VideoCapture(0, cv2.CAP_V4L2)

if not cap.isOpened():
    print("❌ 카메라를 열 수 없습니다. USB 포트를 확인하세요.")
    exit()

cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 480)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 270)
cap.set(cv2.CAP_PROP_FPS, 30)
cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

print(f"영상 송신 시작: {BASE_URL}")

try:
    while True:
        # [우선순위 1] 웹 버튼 신호 확인
        if should_stop:
            print("\n[SIGNAL] 종료 신호가 확인되었습니다. 루프를 탈출합니다.")
            break

        # [우선순위 2] 시간 제한(1분) 확인
        if is_identified:
            if start_time is None:
                start_time = time.time()  # 식별된 첫 순간에 타이머 시작
            
            elapsed = time.time() - start_time
            if elapsed > limit:
                print(f"\n[TIMER] 40초가 경과하여 안전을 위해 종료합니다. (경과: {int(elapsed)}초)")
                break

        ret, frame = cap.read()
        if not ret:
            print("카메라 프레임을 읽을 수 없습니다.")
            break

        # 얼굴 식별 로직
        if not is_identified and len(known_encodings) > 0:
            small_frame = cv2.resize(frame, (0, 0), fx=0.25, fy=0.25)
            rgb_small_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)
            face_locations = face_recognition.face_locations(rgb_small_frame)
            if face_locations:
                face_encodings = face_recognition.face_encodings(rgb_small_frame, face_locations)
                for face_encoding in face_encodings:
                    matches = face_recognition.compare_faces(known_encodings, face_encoding, tolerance=0.5)
                    if True in matches:
                        first_match_index = matches.index(True)
                        identified_user = known_names[first_match_index]
                        is_identified = True
                        print(f"\n{identified_user}님 식별 완료! 측정을 시작합니다.")
                        break

        # 이미지 전송
        _, img_encoded = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 40])
        
        try:
            headers = {'User-ID': identified_user}
            response = requests.post(BASE_URL, data=img_encoded.tobytes(), headers=headers, timeout=0.5)
            if response.status_code == 200:
                print("*" if is_identified else ".", end="", flush=True)
        except:
            print("T", end="", flush=True)
        
        time.sleep(0.05)

finally:
    cap.release()
    cv2.destroyAllWindows()
    print("\n카메라 자원을 해제했습니다.")
    os._exit(0)