"""보관소 도메인 데이터 구조 (주로 모의 서버에서 사용).

설계 문서의 Item / Slot / Zone 을 단순화해 옮긴 것.
키오스크 자체는 MQTT 메시지(dict)만 주고받으므로 이 모듈이 없어도 동작한다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Item:
    id: str
    dong: int
    ho: int
    floor: int
    line: str
    size: str                 # S / M / L
    weight: float
    option: str               # DOOR / PICKUP
    slot_id: str | None = None
    pickup_code: str | None = None
    eta: str | None = None
    arrived_at: str = field(default_factory=lambda: datetime.now().isoformat())
    status: str = "STORED"    # STORED / DISPATCHED / PICKED


@dataclass
class Slot:
    id: str                   # 예: B1-C03-L2
    size: str                 # 셀 크기 S/M/L
    band: str                 # B1(Hot) / B2(Warm) / B3(Cold)
    col: int
    level: int
    occupied: bool = False
    item_id: str | None = None
