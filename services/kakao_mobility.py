"""
카카오 모빌리티 API 모듈

카카오 모빌리티(내비) API를 사용하여 택시 예상 시간 및 요금을 조회합니다.

API 문서: https://developers.kakao.com/docs/latest/ko/kakaonavi/common

사용 예:
    from transport_module.services.kakao_mobility import get_taxi_time
    
    result = get_taxi_time(api_key, origin_lat, origin_lon, dest_lat, dest_lon)
    print(f"소요시간: {result['duration_min']}분, 요금: {result['taxi_fare']}원")
"""
import requests

def get_taxi_time(api_key: str, origin_lat: float, origin_lon: float, dest_lat: float, dest_lon: float) -> dict:
    """
    카카오 모빌리티 API를 사용하여 택시 예상 시간 및 요금을 조회합니다.
    
    Args:
        api_key: 카카오 REST API 키
        origin_lat: 출발지 위도
        origin_lon: 출발지 경도
        dest_lat: 도착지 위도
        dest_lon: 도착지 경도
    
    Returns:
        {
            "ok": True/False,
            "duration_min": int,  # 예상 소요시간 (분)
            "taxi_fare": int,     # 예상 택시 요금 (원)
            "distance_meter": int, # 거리 (미터)
            "error": str         # 실패 시 에러 메시지
        }
    """
    if not api_key:
        return {"ok": False, "error": "No API Key"}
    
    # 목적지나 출발지 좌표가 0.0이면 스킵
    if (origin_lat == 0.0 and origin_lon == 0.0) or (dest_lat == 0.0 and dest_lon == 0.0):
        return {"ok": False, "error": "Invalid coordinates"}

    url = "https://apis-navi.kakaomobility.com/v1/directions"
    # origin, destination: "lon,lat"
    params = {
        "origin": f"{origin_lon},{origin_lat}",
        "destination": f"{dest_lon},{dest_lat}",
        "priority": "RECOMMEND",
        "car_type": 1,  # 일반 승용차 기준 (택시 요금 추산용)
        "summary": True
    }
    
    headers = {
        "Authorization": f"KakaoAK {api_key}"
    }
    
    try:
        res = requests.get(url, params=params, headers=headers, timeout=3)
        if res.status_code != 200:
            return {"ok": False, "error": f"HTTP {res.status_code}", "raw": res.text}
        
        data = res.json()
        routes = data.get("routes", [])
        if not routes:
            return {"ok": False, "error": "No routes found"}
        
        summary = routes[0].get("summary", {})
        duration_sec = summary.get("duration", 0)
        fare = summary.get("fare", {})
        taxi_fare = fare.get("taxi", 0)  # 예상 택시 요금
        
        return {
            "ok": True,
            "duration_min": duration_sec // 60,
            "taxi_fare": taxi_fare,
            "distance_meter": summary.get("distance", 0)
        }
            
    except Exception as e:
        return {"ok": False, "error": str(e)}
