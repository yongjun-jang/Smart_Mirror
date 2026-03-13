import cv2
import time
import numpy as np
from dataclasses import dataclass

@dataclass
class ConditionState:
    state: str               # tired / tense / neutral / noface / noresponse
    face_detected: bool
    blink_per_min: float
    closed_ratio_10s: float
    head_motion_std: float
    last_update_ts: float

class ConditionEstimatorCV:
    def __init__(self):
        # [수정] AWS에는 카메라가 없으므로 VideoCapture 제거
        self.face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        self.eye_cascade  = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_eye.xml")

        self.win_sec = 10.0
        self.samples = []  # (t, face_found, eyes_found, face_cx, face_cy)
        self.last_state = "noface"
        self.last_interaction_ts = time.time()

        # baseline (개인 기준선) - 자동 적응
        self.baseline_closed = 0.25
        self.baseline_motion = 6.0

    def mark_interaction(self):
        self.last_interaction_ts = time.time()

    def _append_sample(self, t, face_found, eyes_found, cx, cy):
        self.samples.append((t, face_found, eyes_found, cx, cy))
        cut = t - self.win_sec
        while self.samples and self.samples[0][0] < cut:
            self.samples.pop(0)

    def _compute_metrics(self):
        if not self.samples:
            return 0.0, 1.0, 0.0, False

        face_flags = [s[1] for s in self.samples]
        eye_flags  = [s[2] for s in self.samples]
        face_found_ratio = sum(face_flags) / len(face_flags)
        face_detected = face_found_ratio >= 0.3

        if not face_detected:
            return 0.0, 1.0, 0.0, False

        face_indices = [i for i, f in enumerate(face_flags) if f]
        if not face_indices:
            return 0.0, 1.0, 0.0, False

        eyes_missing = 0
        for i in face_indices:
            if not eye_flags[i]:
                eyes_missing += 1
        closed_ratio = eyes_missing / len(face_indices)

        cxs = [self.samples[i][3] for i in face_indices if self.samples[i][3] is not None]
        cys = [self.samples[i][4] for i in face_indices if self.samples[i][4] is not None]
        if len(cxs) >= 3:
            head_motion_std = float(np.sqrt(np.var(cxs) + np.var(cys)))
        else:
            head_motion_std = 0.0

        blinks = 0
        prev = None
        for i in face_indices:
            cur = eye_flags[i]
            if prev is False and cur is True:
                blinks += 1
            prev = cur

        blink_per_min = (blinks / self.win_sec) * 60.0
        return blink_per_min, float(closed_ratio), float(head_motion_std), True

    def _classify(self, blink_per_min, closed_ratio, head_motion_std, face_detected):
        now = time.time()
        if not face_detected:
            return "noface"

        if (now - self.last_interaction_ts) > 12 and head_motion_std < (self.baseline_motion * 0.7):
            return "noresponse"

        if closed_ratio > (self.baseline_closed + 0.20):
            return "tired"

        if head_motion_std > (self.baseline_motion + 10.0):
            return "tense"

        return "neutral"

    def _update_baseline(self, closed_ratio, head_motion_std, face_detected):
        if not face_detected:
            return
        alpha = 0.02
        self.baseline_closed = (1 - alpha) * self.baseline_closed + alpha * closed_ratio
        self.baseline_motion = (1 - alpha) * self.baseline_motion + alpha * head_motion_std

    # [수정] 외부 프레임을 인자로 받도록 변경
    def step(self, external_frame=None) -> ConditionState:
        t = time.time()
        
        if external_frame is None:
            return ConditionState("noface", False, 0.0, 1.0, 0.0, t)

        frame = external_frame
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        faces = self.face_cascade.detectMultiScale(gray, scaleFactor=1.2, minNeighbors=5, minSize=(80, 80))
        face_found = len(faces) > 0
        eyes_found = False
        cx = cy = None

        if face_found:
            x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
            cx, cy = x + w / 2.0, y + h / 2.0
            roi = gray[y:y+h, x:x+w]
            eyes = self.eye_cascade.detectMultiScale(roi, scaleFactor=1.2, minNeighbors=6, minSize=(20, 20))
            eyes_found = len(eyes) >= 1

        self._append_sample(t, face_found, eyes_found, cx, cy)
        blink_per_min, closed_ratio, head_motion_std, face_detected = self._compute_metrics()
        state = self._classify(blink_per_min, closed_ratio, head_motion_std, face_detected)

        if state == "neutral":
            self._update_baseline(closed_ratio, head_motion_std, face_detected)

        self.last_state = state
        return ConditionState(
            state=state,
            face_detected=face_detected,
            blink_per_min=float(round(blink_per_min, 2)),
            closed_ratio_10s=float(round(closed_ratio, 3)),
            head_motion_std=float(round(head_motion_std, 2)),
            last_update_ts=t
        )

    def release(self):
        pass