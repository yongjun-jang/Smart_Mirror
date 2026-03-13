import os
import time
import logging
import json
from dotenv import load_dotenv
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_fixed
from config import Config

# 0. 환경 변수 및 로깅 설정
load_dotenv()
if not os.path.exists('evidence'):
    os.makedirs('evidence')

# 가이드라인 준수: m1_log.txt에 실행 기록 저장 [cite: 208]
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("evidence/m1_log.txt", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class SmartMirrorBriefing:
    def __init__(self):
        # 사전미션 M1: OpenAI 호환 클라이언트 및 환경변수 사용 [cite: 212, 217]
        api_key = Config.MINIMAX_API_KEY
        self.client = OpenAI(
            api_key=api_key,
            base_url="https://api.minimaxi.chat/v1", # URL 규격 준수
        )
        
        # [페르소나 설정] 따뜻한 격려와 명확한 정보를 동시에 제공 
        self.system_prompt = (
            "너는 2030 1인 가구를 위한 현관 스마트미러 속 '다정한 루틴 관리자'야. "
            "사용자의 날씨, 일정, 교통 정보를 분석해서 외출 전략을 짧고 명확하게 알려줘. "
            "마지막에는 반드시 혼자 사는 사용자의 마음을 어루만지는 따뜻하고 격려 섞인 한마디를 덧붙여야 해."
        )

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2)) # M1 필수: 재시도 로직 
    def generate_strategy(self, payload: dict) -> dict:
        # 1. 룰 기반 멘트 생성 (백업용 및 기술 유기성 확보) 
        weather = payload.get("weather", {})
        temp = weather.get("temp")
        depart_in = payload.get("recommend_depart_in_min", 5)
        
        action_points = []
        if weather.get("is_rain"): action_points.append("비가 오니 우산을 꼭 챙기세요.")
        if temp is not None and temp <= 0: action_points.append("날씨가 춥습니다. 목도리를 챙기세요.")
        action_points.append(f"{depart_in}분 후 출발을 추천합니다.")

        # 2. LLM 인사이트 생성 (데이터 가공 및 개인화) 
        context_input = f"날씨: {weather}, 일정: {payload.get('todos')}, 소지품: {payload.get('items')}"
        
        start_time = time.time()
        try:
            # M1 필수: System/User 역할 분리 및 타임아웃 [cite: 220, 222]
            response = self.client.chat.completions.create(
                model="minimax-text-01",
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": f"현재 상황: {context_input}. 한 줄 전략과 따뜻한 격려를 해줘."}
                ],
                timeout=10.0
            )
            
            # 가이드라인 준수: Telemetry 데이터(지연시간, 토큰 사용량) 로깅 
            latency = (time.time() - start_time) * 1000
            answer = response.choices[0].message.content
            usage = response.usage

            logger.info(f"AI Insight: {answer}")
            logger.info(f"Latency: {latency:.2f}ms | Tokens: {usage.total_tokens}")

            return {
                "summary": answer,
                "action_points": action_points,
                "latency_ms": latency
            }

        except Exception as e:
            logger.error(f"API 호출 실패: {e}")
            raise e

# app.py에서 호출할 인터페이스
briefing_service = SmartMirrorBriefing()

def make_briefing(payload: dict) -> dict:
    return briefing_service.generate_strategy(payload)