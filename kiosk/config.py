"""보관소 키오스크 공통 설정.

내부 서버(MQTT broker) 주소와 토픽, 단지 메타데이터를 한곳에서 관리한다.
환경변수로 덮어쓸 수 있어 시뮬레이션 서버 주소만 바꿔 바로 연동할 수 있다.
"""
from __future__ import annotations

import os


# --- MQTT 브로커 (내부 서버) ---------------------------------------------
# 시뮬레이션과 연동할 때는 BROKER_HOST 만 바꾸면 된다.
BROKER_HOST = os.getenv("LOCKER_BROKER_HOST", "localhost")
BROKER_PORT = int(os.getenv("LOCKER_BROKER_PORT", "1883"))
BROKER_KEEPALIVE = 30

# 인증이 필요한 내부 서버라면 환경변수로 지정
BROKER_USERNAME = os.getenv("LOCKER_BROKER_USER") or None
BROKER_PASSWORD = os.getenv("LOCKER_BROKER_PASS") or None


# --- 토픽 ----------------------------------------------------------------
TOPIC_INPUT_REQ = "locker/input/request"
TOPIC_INPUT_RES = "locker/input/response"
TOPIC_PICKUP_REQ = "locker/output/pickup/request"
TOPIC_PICKUP_RES = "locker/output/pickup/response"
TOPIC_ROBOT_REQ = "locker/output/robot/request"
TOPIC_ROBOT_RES = "locker/output/robot/response"
TOPIC_STATUS = "locker/status"
TOPIC_KIOSK_ONLINE = "locker/kiosk/{kiosk_id}/online"

QOS = 1


# --- 크기 규격 -----------------------------------------------------------
SIZES = ("S", "M", "L")
SIZE_LABEL = {"S": "소 (Small)", "M": "중 (Medium)", "L": "대 (Large)"}
SIZE_RANK = {"S": 1, "M": 2, "L": 3}

# 입력구별 허용 최대 무게(kg) — 입력구보다 큰/무거운 물품 거부에 사용
SIZE_MAX_WEIGHT = {"S": 5.0, "M": 15.0, "L": 30.0}


# --- 단지 메타데이터 -----------------------------------------------------
# 실제 단지 정보로 교체. (동 -> 유효 호수 집합은 간단히 층/라인으로 표현)
# line 매핑: 호수 끝자리(1~2호=A라인, 3~4호=B라인) 식. 복도식은 전체 1라인.
VALID_DONGS = [101, 102, 103, 201, 202]
FLOORS_PER_DONG = 20          # 1층 ~ 20층
UNITS_PER_FLOOR = 4           # 01 ~ 04호


def parse_unit(dong: int, ho: int):
    """(동, 호수)를 검증하고 floor/line 을 계산한다.

    반환: (ok: bool, floor: int|None, line: str|None, reason: str)
    """
    if dong not in VALID_DONGS:
        return False, None, None, f"존재하지 않는 동입니다: {dong}동"
    floor = ho // 100
    unit = ho % 100
    if not (1 <= floor <= FLOORS_PER_DONG):
        return False, None, None, f"유효하지 않은 층입니다: {floor}층"
    if not (1 <= unit <= UNITS_PER_FLOOR):
        return False, None, None, f"유효하지 않은 호수입니다: {ho}호"
    # 계단식: 1·2호 = A라인, 3·4호 = B라인
    line = "A" if unit in (1, 2) else "B"
    return True, floor, line, ""
