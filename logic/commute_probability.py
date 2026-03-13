# smartmirror_pi5/logic/commute_probability.py
"""
대중교통별 정시 도착 확률 계산 모듈

- 입력으로 받은 '남은 시간(time_budget_min)' 안에 도착할 확률을
  정규분포 CDF로 근사해서 계산합니다.
- 택시 소요시간(카카오 모빌리티) 기반으로 버스/지하철 평균 시간을 근사합니다.
- Flask jsonify가 바로 직렬화할 수 있도록 **dict 형태**로 반환합니다.

주의:
- 실제 버스/지하철은 지역/노선에 따라 편차가 큽니다.
  메이커톤 MVP에서는 "동작/안정"이 우선이므로, 근사+설명(factors)을 함께 제공합니다.
"""

import math
from typing import Optional, Dict, Any
from dataclasses import dataclass, asdict


@dataclass
class ModeResult:
    ok: bool
    mode: str
    mean_min: float = 0.0
    std_min: float = 0.0
    p_on_time: float = 0.0
    factors: list = None
    detail: dict = None
    error: str = ""

    def __post_init__(self):
        if self.factors is None:
            self.factors = []
        if self.detail is None:
            self.detail = {}


def ontime_prob(time_budget: float, mean: float, std: float) -> float:
    """P(소요시간 <= time_budget) = Φ((time_budget - mean)/std)"""
    if std <= 0:
        std = 1.0
    z = (time_budget - mean) / std
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def _to_dict(out: Dict[str, ModeResult]) -> Dict[str, Dict[str, Any]]:
    # Flask jsonify 직렬화 안전
    return {k: asdict(v) for k, v in out.items()}


def compute_probabilities(
    time_budget_min: float,
    taxi_duration_min: Optional[float],
    taxi_distance_m: Optional[float],
    bus_wait_min: Optional[float],
    subway_wait_min: Optional[float],
    bus_available: bool = True,
    subway_available: bool = True,
    current_hour: int = 12,  # 0~23
) -> Dict[str, Dict[str, Any]]:
    """
    각 교통수단별 정시 도착 확률 계산

    Returns:
        {
          "taxi": { ok, mode, mean_min, std_min, p_on_time, factors, detail, error },
          "bus":  { ... },
          "subway": { ... }
        }
    """
    out: Dict[str, ModeResult] = {}

    # 새벽 시간대(대중교통 운행 불확실): 00:00 ~ 05:29
    is_early_morning = current_hour < 6

    # ---- 택시 ----
    if taxi_duration_min is None:
        out["taxi"] = ModeResult(ok=False, mode="taxi", error="택시 소요시간을 구할 수 없음")
    else:
        mean = float(taxi_duration_min) + 3.0  # 호출/승차/신호 대기 보정
        std = max(3.0, mean * 0.18)            # 택시 변동성(대략 18%)
        p = ontime_prob(time_budget_min, mean, std)

        factors = []
        if mean > time_budget_min:
            factors.append("시간이 촉박")
        if taxi_distance_m and float(taxi_distance_m) > 12000:
            factors.append("장거리 이동")
        out["taxi"] = ModeResult(
            ok=True,
            mode="taxi",
            mean_min=round(mean, 1),
            std_min=round(std, 1),
            p_on_time=round(p, 3),
            factors=factors,
            detail={
                "base_drive_min": float(taxi_duration_min),
                "distance_m": float(taxi_distance_m) if taxi_distance_m is not None else None,
            },
        )

    # 버스/지하철은 택시 시간 기반 근사 필요
    base = float(taxi_duration_min) if taxi_duration_min is not None else None

    # ---- 버스 ----
    if base is None:
        out["bus"] = ModeResult(ok=False, mode="bus", error="버스 근사 계산에 필요한 기준(택시시간)이 없음")
    elif is_early_morning and (not bus_available or bus_wait_min is None):
        out["bus"] = ModeResult(
            ok=True,
            mode="bus",
            mean_min=0.0,
            std_min=0.0,
            p_on_time=0.0,
            factors=["현재 버스 운행 없음 (새벽 시간대/정보 없음)"],
            detail={"not_operating": True},
        )
    else:
        walk_to_stop = 4.0
        if bus_wait_min is not None:
            wait = float(bus_wait_min)
            wait_estimated = False
        else:
            wait = 8.0
            wait_estimated = True

        in_vehicle = base * 1.55 + 6.0  # 정차/우회/환승 리스크
        mean = walk_to_stop + wait + in_vehicle
        std = max(5.0, mean * 0.30)     # 변동성 큰 편
        p = ontime_prob(time_budget_min, mean, std)

        factors = []
        if wait_estimated:
            factors.append("실시간 정보 없음 (평균 대기시간 사용)")
        if wait >= 10:
            factors.append("버스 대기 길음")
        if mean > time_budget_min:
            factors.append("시간이 촉박")

        out["bus"] = ModeResult(
            ok=True,
            mode="bus",
            mean_min=round(mean, 1),
            std_min=round(std, 1),
            p_on_time=round(p, 3),
            factors=factors,
            detail={
                "walk_to_stop": walk_to_stop,
                "wait_min": round(wait, 1),
                "in_vehicle_min": round(in_vehicle, 1),
                "wait_estimated": wait_estimated,
            },
        )

    # ---- 지하철 ----
    if base is None:
        out["subway"] = ModeResult(ok=False, mode="subway", error="지하철 근사 계산에 필요한 기준(택시시간)이 없음")
    elif is_early_morning and (not subway_available or subway_wait_min is None):
        out["subway"] = ModeResult(
            ok=True,
            mode="subway",
            mean_min=0.0,
            std_min=0.0,
            p_on_time=0.0,
            factors=["현재 지하철 운행 없음 (새벽 시간대/정보 없음)"],
            detail={"not_operating": True},
        )
    else:
        walk_to_station = 6.0
        if subway_wait_min is not None:
            wait = float(subway_wait_min)
            wait_estimated = False
        else:
            wait = 4.0
            wait_estimated = True

        in_vehicle = base * 1.25 + 4.0
        mean = walk_to_station + wait + in_vehicle
        std = max(4.0, mean * 0.20)  # 버스보다 안정적
        p = ontime_prob(time_budget_min, mean, std)

        factors = []
        if wait_estimated:
            factors.append("실시간/시간표 정보 없음 (평균 대기시간 사용)")
        if wait >= 8:
            factors.append("지하철 대기 길음")
        if mean > time_budget_min:
            factors.append("시간이 촉박")

        out["subway"] = ModeResult(
            ok=True,
            mode="subway",
            mean_min=round(mean, 1),
            std_min=round(std, 1),
            p_on_time=round(p, 3),
            factors=factors,
            detail={
                "walk_to_station": walk_to_station,
                "wait_min": round(wait, 1),
                "in_vehicle_min": round(in_vehicle, 1),
                "wait_estimated": wait_estimated,
            },
        )

    return _to_dict(out)

