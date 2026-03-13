import cv2
import face_recognition
import pickle
import numpy as np

class SmartFaceEngine:
    def __init__(self, model_path="registered_faces.pkl"):
        # 1. 저장된 얼굴 데이터 로드
        with open(model_path, "rb") as f:
            data = pickle.load(f)
            self.known_encodings = data["encodings"]
            self.known_names = data["names"]
        
        self.current_user = "Unknown"
        self.is_identified = False

    def process_frame(self, frame):
        # 성능을 위해 프레임 크기 축소 (1/4)
        small_frame = cv2.resize(frame, (0, 0), fx=0.25, fy=0.25)
        rgb_small_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)

        # 2. 얼굴 위치 감지 (Mediapipe 대신 face_recognition 기본 기능 활용 가능)
        face_locations = face_recognition.face_locations(rgb_small_frame)

        if not face_locations:
            # 얼굴이 사라지면 상태 초기화 (다음 사람을 위해)
            self.current_user = "Unknown"
            self.is_identified = False
            return "No Face", frame

        # 3. 얼굴이 있는데 아직 누구인지 모를 때만 식별 연산 수행 (핵심!)
        if not self.is_identified:
            face_encodings = face_recognition.face_encodings(rgb_small_frame, face_locations)
            
            for face_encoding in face_encodings:
                matches = face_recognition.compare_faces(self.known_encodings, face_encoding, tolerance=0.5)
                name = "Unknown"

                if True in matches:
                    first_match_index = matches.index(True)
                    name = self.known_names[first_match_index]
                
                self.current_user = name
                self.is_identified = True # 식별 완료 상태로 변경 (연산 정지)

        # 4. 화면에 이름 표시
        for (top, right, bottom, left) in face_locations:
            # 축소했던 좌표를 다시 원복
            top *= 4; right *= 4; bottom *= 4; left *= 4
            cv2.rectangle(frame, (left, top), (right, bottom), (0, 255, 0), 2)
            cv2.putText(frame, self.current_user, (left, top - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)

        return self.current_user, frame