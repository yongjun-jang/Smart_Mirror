import time
from logic.face_engine import SmartFaceEngine

class MirrorController:
    def __init__(self):
        self.face_engine = SmartFaceEngine("registered_faces.pkl")
        self.current_user = None
        self.mode = "IDLE"  # IDLE -> IDENTIFY -> MONITOR
        
    def process(self, frame):
        # 1. 대기 상태: 얼굴이 감지되면 식별 모드로 전환
        if self.mode == "IDLE":
            # 가벼운 감지 로직 (또는 바로 식별 시도)
            self.mode = "IDENTIFY"
            return f"시스템 시작 중...", frame

        # 2. 식별 상태: 누군지 확인되면 환영 인사 후 식별 기능 종료
        elif self.mode == "IDENTIFY":
            user_name, frame = self.face_engine.process_frame(frame)
            if user_name != "Unknown" and user_name != "No Face":
                self.current_user = user_name
                self.mode = "MONITOR" # 식별 기능 OFF, 측정 모드 ON
                print(f"인식 성공: {user_name}")
                return f"{user_name}님 안녕하세요!", frame
            return "얼굴을 인식 중입니다...", frame

        # 3. 측정 상태: 식별 연산 없이 피로도 측정만 수행 (저부하 모드)
        elif self.mode == "MONITOR":
            # 여기서 기존에 만드신 피로도 측정 함수를 호출하세요
            # fatigue_score = self.measure_fatigue(frame) 
            return f"{self.current_user}님, 피로도를 측정 중입니다.", frame

        return "시스템 대기 중", frame