"""배달 묶음 구성 테스트.  실행: server 폴더에서 python -m unittest discover tests"""
import random
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402
from bundler import build_bundle  # noqa: E402
from models import Item  # noqa: E402

NOW = datetime(2026, 10, 31, 15, 0, tzinfo=config.KST)
_seq = iter(range(1, 1_000_000))


def item(dong, ho, size, wait_min=10):
    n = next(_seq)
    at = (NOW - timedelta(minutes=wait_min)).isoformat()
    return Item(receipt_no=f"20261031-{n:08X}", dong=dong, ho=ho, size=size, mode="ROBOT",
                status="STORED", pickup_code=f"{n:06d}", registered_at=at, stored_at=at)


class BundleTests(unittest.TestCase):
    def assertValid(self, bundle):
        units = sum(it.units for it in bundle.items)
        self.assertLessEqual(units, config.BOX_UNITS)
        self.assertLessEqual(sum(it.weight for it in bundle.items), config.ROBOT_MAX_WEIGHT)
        used = set()
        for it in bundle.items:
            layer, cells = bundle.cells[it.receipt_no]
            self.assertIn(layer, (1, 2))
            self.assertEqual(len(cells), it.units)
            if it.size == "L":
                self.assertEqual(cells, list(range(1, 9)))
            if it.size == "M":
                self.assertIn(cells, config.M_ALLOWED_CELLS)
            for c in cells:
                self.assertNotIn((layer, c), used, "칸이 겹침")
                used.add((layer, c))
        self.assertEqual(bundle.metrics["units"], units)

    def test_empty_pool(self):
        self.assertIsNone(build_bundle([], NOW))

    def test_single_item_ships_alone(self):
        b = build_bundle([item(101, 101, "S")], NOW)
        self.assertEqual(len(b.items), 1)
        self.assertValid(b)

    def test_max_count_per_size(self):
        self.assertEqual(len(build_bundle([item(101, 101, "S") for _ in range(40)], NOW).items), 16)
        self.assertEqual(len(build_bundle([item(101, 101, "M") for _ in range(10)], NOW).items), 4)
        self.assertEqual(len(build_bundle([item(101, 101, "L") for _ in range(5)], NOW).items), 2)

    def test_keeps_single_dong_when_it_fills_box(self):
        pool = [item(101, 100 + i % 12 + 1, "S") for i in range(16)]
        pool += [item(102, 201, "L"), item(102, 202, "L")]
        b = build_bundle(pool, NOW)
        self.assertEqual(b.metrics["units"], 16)
        self.assertEqual(len(b.metrics["dongs"]), 1)

    def test_fills_box_across_dongs(self):
        pool = [item(101, 101, "M"), item(101, 102, "S"), item(101, 103, "S"),   # 6
                item(102, 201, "M"), item(102, 202, "S"),                        # 5
                item(103, 301, "M"), item(103, 302, "S")]                        # 5
        b = build_bundle(pool, NOW)
        self.assertEqual(b.metrics["units"], 16)
        self.assertEqual(b.metrics["dongs"], [101, 102, 103])
        self.assertValid(b)

    def test_prefers_dong_that_can_be_cleared(self):
        pool = [item(101, 101, "L", wait_min=4 * 60)]                  # aged → 기준 동, 8단위
        pool += [item(102, 201 + i, "S") for i in range(8)]            # 8단위, 통째로 들어감
        pool += [item(103, 301 + i % 12, "S") for i in range(12)]      # 12단위, 일부만 들어감
        b = build_bundle(pool, NOW)
        self.assertEqual(b.metrics["units"], 16)
        self.assertIn(102, b.metrics["dongs"])
        self.assertNotIn(103, b.metrics["dongs"])

    def test_aged_item_becomes_anchor(self):
        pool = [item(101, 100 + i % 12 + 1, "S") for i in range(16)]
        old = item(105, 412, "L", wait_min=4 * 60)
        b = build_bundle(pool + [old], NOW)
        self.assertIn(old, b.items)

    def test_layer_layout(self):
        pool = [item(101, 412, "L"), item(101, 305, "M"), item(101, 305, "S"),
                item(101, 203, "S"), item(101, 203, "S"), item(101, 410, "S")]
        b = build_bundle(pool, NOW)
        self.assertEqual(b.metrics["units"], 16)
        self.assertValid(b)
        layers = {it.size: b.cells[it.receipt_no][0] for it in b.items if it.size != "S"}
        self.assertNotEqual(layers["L"], layers["M"])

    def test_random_pools_valid_and_maximal(self):
        rng = random.Random(7)
        for _ in range(300):
            pool = [item(rng.choice(config.VALID_DONGS), rng.randint(1, 4) * 100 + rng.randint(1, 12),
                         rng.choices(config.SIZES, [0.5, 0.35, 0.15])[0], wait_min=rng.randint(0, 300))
                    for _ in range(rng.randint(1, 40))]
            b = build_bundle(pool, NOW)
            self.assertValid(b)
            leftover = [it for it in pool if it not in b.items]
            units = b.metrics["units"]
            for it in leftover:       # 더 실을 수 있는 물품이 남아 있으면 안 됨
                self.assertGreater(units + it.units, config.BOX_UNITS)


if __name__ == "__main__":
    unittest.main()
