def apply_policy(condition_state: str) -> dict:
    # UI 모드 정의: 카드 수, 알림 강도 등
    if condition_state == "tired":
        return {"ui_mode": "compact", "max_cards": 2, "alert_strength": "low", "tone": "short"}
    if condition_state == "tense":
        return {"ui_mode": "calm", "max_cards": 3, "alert_strength": "mid", "tone": "reassuring"}
    if condition_state == "noresponse":
        return {"ui_mode": "prompt", "max_cards": 2, "alert_strength": "mid", "tone": "call"}
    if condition_state == "noface":
        return {"ui_mode": "idle", "max_cards": 1, "alert_strength": "low", "tone": "idle"}
    return {"ui_mode": "default", "max_cards": 4, "alert_strength": "mid", "tone": "normal"}