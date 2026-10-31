"""로봇 배달 묶음 구성 (명세 v3.3).

목표 순서
  ① 공용 박스를 가득 채운다 (부피 = 소형 칸 단위, S1·M4·L8, 2층 × 8칸)
  ② 그 안에서 들르는 동·세대 수를 최소로 한다
  ③ 오래 기다린 물품을 우선한다 (aging)

크기 비율 1:4:8 이 서로 나누어떨어지므로 "단위 합 ≤ 16" 이면 두 층에 항상 담긴다.
따라서 묶음 구성은 단위·무게만 보고, 층·칸 배정은 확정된 뒤 assign_cells() 가 한다.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime

import config
from models import Bundle, Item


class _Load:
    """구성 중인 묶음의 누적 상태."""

    def __init__(self):
        self.items: list[Item] = []
        self.units = 0
        self.weight = 0
        self.households: set[tuple[int, int]] = set()
        self.floors: set[tuple[int, int]] = set()
        self.dongs: list[int] = []

    def fits(self, item: Item) -> bool:
        return (self.units + item.units <= config.BOX_UNITS
                and self.weight + item.weight <= config.ROBOT_MAX_WEIGHT)

    def add(self, item: Item):
        self.items.append(item)
        self.units += item.units
        self.weight += item.weight
        self.households.add(item.household)
        self.floors.add((item.dong, item.floor))
        if item.dong not in self.dongs:
            self.dongs.append(item.dong)

    def copy(self) -> "_Load":
        other = _Load()
        other.items = list(self.items)
        other.units, other.weight = self.units, self.weight
        other.households, other.floors = set(self.households), set(self.floors)
        other.dongs = list(self.dongs)
        return other


def _aged(item: Item, now: datetime) -> bool:
    return item.wait_seconds(now) >= config.AGING_LIMIT_SEC


def _fill(load: _Load, candidates: list[Item], now: datetime) -> None:
    """같은 세대 → 같은 층 → 나머지 순, 같은 단계면 aged → 큰 물품 → 오래 기다린 순으로 담는다."""
    remaining = list(candidates)

    def key(it: Item):
        if it.household in load.households:
            tier = 0
        elif (it.dong, it.floor) in load.floors:
            tier = 1
        else:
            tier = 2
        return (tier, 0 if _aged(it, now) else 1, -config.SIZE_RANK[it.size],
                -it.wait_seconds(now), it.receipt_no)

    while remaining and load.units < config.BOX_UNITS:
        remaining.sort(key=key)
        pick = next((it for it in remaining if load.fits(it)), None)
        if pick is None:
            return
        load.add(pick)
        remaining.remove(pick)


def _dong_distance(a: int, b: int) -> int:
    order = config.DONG_ORDER
    if a in order and b in order:
        return abs(order.index(a) - order.index(b))
    return abs(a - b)


def _next_dong(load: _Load, by_dong: dict[int, list[Item]], anchor: int, now: datetime) -> int | None:
    """남은 칸을 채울 다음 동.

    (a) 남은 칸에 대기 물품이 전부 들어가는 동 중 가장 큰 동 (그 동을 통째로 비움)
    (b) 없으면 남은 칸을 가장 많이 채우는 동. 동점이면 aged 보유 → 가까운 동.
    """
    room = config.BOX_UNITS - load.units
    chosen = {it.receipt_no for it in load.items}
    best_key, best_dong = None, None
    for dong, items in by_dong.items():
        if dong in load.dongs:
            continue
        rest = [it for it in items if it.receipt_no not in chosen]
        if not rest:
            continue
        total_units = sum(it.units for it in rest)
        total_weight = sum(it.weight for it in rest)
        fits_all = total_units <= room and load.weight + total_weight <= config.ROBOT_MAX_WEIGHT
        trial = load.copy()
        _fill(trial, rest, now)
        gained = trial.units - load.units
        if gained == 0:
            continue
        key = (1 if fits_all else 0, total_units if fits_all else gained,
               any(_aged(it, now) for it in rest), -_dong_distance(dong, anchor))
        if best_key is None or key > best_key:
            best_key, best_dong = key, dong
    return best_dong


def build_bundle(pool: list[Item], now: datetime) -> Bundle | None:
    """로봇 배달 대상 물품(pool)으로 1회 배달 묶음을 만든다. 대상이 없으면 None."""
    if not pool:
        return None
    by_dong: dict[int, list[Item]] = defaultdict(list)
    for it in pool:
        by_dong[it.dong].append(it)

    aged = [it for it in pool if _aged(it, now)]
    if aged:
        anchor_item = max(aged, key=lambda it: (it.wait_seconds(now), it.receipt_no))
    else:
        anchor_dong = max(by_dong, key=lambda d: (sum(it.units for it in by_dong[d]),
                                                  -_dong_distance(d, config.DONG_ORDER[0])))
        anchor_item = max(by_dong[anchor_dong], key=lambda it: (it.wait_seconds(now), it.receipt_no))
    anchor = anchor_item.dong

    load = _Load()
    load.add(anchor_item)
    _fill(load, [it for it in by_dong[anchor] if it is not anchor_item], now)

    while load.units < config.BOX_UNITS and len(load.dongs) < config.MAX_DONGS_PER_BUNDLE:
        dong = _next_dong(load, by_dong, anchor, now)
        if dong is None:
            break
        chosen = {it.receipt_no for it in load.items}
        _fill(load, [it for it in by_dong[dong] if it.receipt_no not in chosen], now)

    return Bundle(items=load.items, cells=assign_cells(load.items),
                  metrics=bundle_metrics(load.items, now))


def assign_cells(items: list[Item]) -> dict[str, tuple[int, list[int]]]:
    """1×8 두 층에 배치. L → M(절반 위치) → S 순서로 넣어 칸이 조각나지 않게 한다.
    같은 세대의 S 는 가능하면 같은 층에 모은다."""
    layers: list[list[str | None]] = [[None] * config.LAYER_UNITS for _ in range(config.BOX_LAYERS)]
    owner: dict[str, tuple[int, int]] = {it.receipt_no: it.household for it in items}
    result: dict[str, tuple[int, list[int]]] = {}

    def take(layer: int, cells: list[int], receipt: str):
        for c in cells:
            layers[layer][c - 1] = receipt
        result[receipt] = (layer + 1, cells)

    for it in sorted(items, key=lambda i: (-config.SIZE_RANK[i.size], i.dong, i.ho, i.receipt_no)):
        placed = False
        if it.size == "L":
            for li, layer in enumerate(layers):
                if all(c is None for c in layer):
                    take(li, list(range(1, config.LAYER_UNITS + 1)), it.receipt_no)
                    placed = True
                    break
        elif it.size == "M":
            for li, layer in enumerate(layers):
                half = next((h for h in config.M_ALLOWED_CELLS
                             if all(layer[c - 1] is None for c in h)), None)
                if half:
                    take(li, list(half), it.receipt_no)
                    placed = True
                    break
        else:
            same = [li for li, layer in enumerate(layers)
                    if any(r and owner.get(r) == it.household for r in layer)]
            for li in same + [i for i in range(len(layers)) if i not in same]:
                free = next((c for c in range(1, config.LAYER_UNITS + 1)
                             if layers[li][c - 1] is None), None)
                if free:
                    take(li, [free], it.receipt_no)
                    placed = True
                    break
        if not placed:
            raise ValueError(f"공용 박스에 배치할 수 없습니다: {it.receipt_no} ({it.size})")
    return result


def bundle_metrics(items: list[Item], now: datetime) -> dict:
    units = sum(it.units for it in items)
    return {
        "count": {s: sum(1 for it in items if it.size == s) for s in config.SIZES},
        "units": units,
        "utilization": round(units / config.BOX_UNITS, 3),
        "weight_kg": sum(it.weight for it in items),
        "dongs": sorted({it.dong for it in items}),
        "households": len({it.household for it in items}),
        "floors": len({(it.dong, it.floor) for it in items}),
        "max_wait_sec": round(max((it.wait_seconds(now) for it in items), default=0)),
    }
