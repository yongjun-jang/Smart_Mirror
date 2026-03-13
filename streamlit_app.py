import sqlite3
import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import matplotlib as mpl
import os

# =========================
# 1. 한글 폰트 설정 (Linux/Raspberry Pi 전용)
# =========================
# 라즈베리파이에 나눔폰트가 설치되는 표준 경로입니다.
font_path = "/usr/share/fonts/truetype/nanum/NanumGothic.ttf"

if os.path.exists(font_path):
    # 폰트 프로퍼티 객체 생성 (이것을 그래프 모든 요소에 주입합니다)
    fp = fm.FontProperties(fname=font_path)
    font_name = fp.get_name()
    
    # Matplotlib 전역 설정 (보조용)
    mpl.rcParams["font.family"] = font_name
    mpl.rcParams["axes.unicode_minus"] = False
else:
    st.error("❌ 한글 폰트가 설치되지 않았습니다. 터미널에서 아래 명령어를 실행하세요.")
    st.code("sudo apt-get install -y fonts-nanum")
    fp = None

# =========================
# 2. 페이지 설정
# =========================
st.set_page_config(
    page_title="Smart Mirror | Data-Driven Dashboard",
    layout="wide"
)

# 커스텀 CSS
st.markdown("""
<style>
body { background-color: #f5f7fa; }
.block-container { padding: 2.5rem 3rem; }
h1, h2, h3 { font-weight: 700; }
.section {
    background-color: white;
    padding: 24px;
    border-radius: 14px;
    margin-bottom: 24px;
    box-shadow: 0 6px 18px rgba(0,0,0,0.06);
}
</style>
""", unsafe_allow_html=True)

# 헤더
st.markdown("## 🪞 스마트 미러 데이터 기반 분석 대시보드")
st.caption("Edge 기반 외출 준비 루틴 지원 시스템 · 운영 데이터 분석 화면")
st.markdown("---")

# =========================
# 3. DB 연결 및 데이터 로드
# =========================
try:
    conn = sqlite3.connect("smartmirror.db")

    events_df = pd.read_sql("""
        SELECT event_name AS 이벤트, COUNT(*) AS 발생_횟수
        FROM events
        GROUP BY event_name
        ORDER BY 발생_횟수 DESC
    """, conn)

    telemetry_df = pd.read_sql("""
        SELECT path AS API, AVG(latency_ms) AS 평균_지연시간_ms
        FROM telemetry
        GROUP BY path
        ORDER BY 평균_지연시간_ms DESC
    """, conn)

    conn.close()
except Exception as e:
    st.error(f"⚠️ DB 연결 오류: {e}")
    st.info("smartmirror.db 파일이 현재 폴더에 있는지 확인하세요.")
    st.stop()

# =========================
# 4. KPI 영역
# =========================
st.markdown("### 📌 핵심 지표 요약")
c1, c2, c3 = st.columns(3)

with c1:
    st.metric(label="총 사용자 상호작용 수", value=int(events_df["발생_횟수"].sum()))
with c2:
    st.metric(label="평균 API 응답 지연 (ms)", value=int(telemetry_df["평균_지연시간_ms"].mean()))
with c3:
    st.metric(label="가장 부하가 큰 기능", value=telemetry_df.iloc[0]["API"])

# =========================
# 5. 사용자 행동 분석 (그래프 폰트 주입 핵심)
# =========================
st.markdown("### 📊 사용자 행동 분석")
col1, col2 = st.columns([3, 2])

with col1:
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.bar(events_df["이벤트"], events_df["발생_횟수"], color="#4C72B0")
    
    # [핵심] 폰트 객체(fp)를 직접 전달하여 한글 깨짐 방지
    ax.set_title("사용자 상호작용 이벤트 분포", fontproperties=fp, fontsize=16)
    ax.set_xlabel("이벤트 유형", fontproperties=fp, fontsize=12)
    ax.set_ylabel("발생 횟수", fontproperties=fp, fontsize=12)
    
    # X축 눈금(이벤트 이름들)에 한글이 있을 경우 처리
    for label in ax.get_xticklabels():
        label.set_fontproperties(fp)
        
    plt.xticks(rotation=45)
    st.pyplot(fig)

with col2:
    st.markdown("**데이터 상세**")
    st.dataframe(events_df, use_container_width=True)

# =========================
# 6. 시스템 성능 분석
# =========================
st.markdown("### ⚙️ 시스템 성능 분석 (Edge 환경)")
fig2, ax2 = plt.subplots(figsize=(8, 4))
ax2.barh(telemetry_df["API"], telemetry_df["평균_지연시간_ms"], color="#55A868")

# [핵심] 폰트 주입
ax2.set_title("API별 평균 응답 지연 시간", fontproperties=fp, fontsize=16)
ax2.set_xlabel("지연 시간 (ms)", fontproperties=fp, fontsize=12)

# Y축 눈금(API 경로) 폰트 설정
for label in ax2.get_yticklabels():
    label.set_fontproperties(fp)

st.pyplot(fig2)

# =========================
# 7. 결론
# =========================
st.markdown("---")
st.markdown("### ✅ 데이터 기반 설계 결론")
st.success("본 대시보드는 라즈베리파이 Edge 환경의 실제 운영 데이터를 기반으로 출력되었습니다.")