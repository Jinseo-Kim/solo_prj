"""테스트용 택배 자동 투입 스크립트.

입력 키오스크를 손으로 여러 번 누르지 않고도 로봇 배차/수령을 시험할 수 있게
INPUT_REQUEST 를 여러 건 발행한다.

사용: python seed_packages.py [건수]   (기본 12건)
"""
from __future__ import annotations

import json
import random
import sys
import time

import paho.mqtt.client as mqtt

import config


def main(n: int):
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="seeder")
    if config.BROKER_USERNAME:
        client.username_pw_set(config.BROKER_USERNAME, config.BROKER_PASSWORD)
    client.connect(config.BROKER_HOST, config.BROKER_PORT, config.BROKER_KEEPALIVE)
    client.loop_start()
    time.sleep(1)

    for i in range(n):
        dong = random.choice(config.VALID_DONGS)
        floor = random.randint(1, config.FLOORS_PER_DONG)
        unit = random.randint(1, config.UNITS_PER_FLOOR)
        ho = floor * 100 + unit
        size = random.choices(config.SIZES, weights=[0.5, 0.35, 0.15])[0]
        weight = round(random.uniform(0.3, config.SIZE_MAX_WEIGHT[size] * 0.8), 1)
        payload = {
            "type": "INPUT_REQUEST",
            "request_id": f"seed-{i}",
            "kiosk_id": "SEEDER",
            "dong": dong, "ho": ho, "size": size, "weight": weight,
        }
        client.publish(config.TOPIC_INPUT_REQ,
                       json.dumps(payload, ensure_ascii=False), qos=config.QOS)
        print(f"투입 {i+1}/{n}: {dong}동 {ho}호 [{size}] {weight}kg")
        time.sleep(0.2)

    time.sleep(1)
    client.loop_stop()
    client.disconnect()
    print("완료.")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 12)
