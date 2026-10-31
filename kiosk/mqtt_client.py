"""paho-mqtt 래퍼.

키오스크/서버가 공통으로 쓰는 얇은 MQTT 클라이언트.
- JSON 자동 직렬화/역직렬화
- 토픽별 콜백 등록
- LWT(Last Will) 로 온라인/오프라인 표시
- 백그라운드 네트워크 루프(loop_start) 사용 → Tkinter 메인 루프와 공존
"""
from __future__ import annotations

import json
import threading
import uuid
from typing import Callable

import paho.mqtt.client as mqtt

import config


class MqttClient:
    def __init__(self, client_id: str, online_topic: str | None = None):
        self.client_id = client_id
        self._handlers: dict[str, Callable[[dict], None]] = {}
        self._connect_cbs: list[Callable[[bool], None]] = []
        self._lock = threading.Lock()
        self.connected = False

        self._client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"{client_id}-{uuid.uuid4().hex[:6]}",
            clean_session=True,
        )
        if config.BROKER_USERNAME:
            self._client.username_pw_set(config.BROKER_USERNAME, config.BROKER_PASSWORD)

        self._online_topic = online_topic
        if online_topic:
            # 비정상 종료 시 브로커가 자동으로 offline 을 발행
            self._client.will_set(online_topic, "offline", qos=config.QOS, retain=True)

        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message

    # --- 공개 API --------------------------------------------------------
    def on(self, topic: str, handler: Callable[[dict], None]) -> None:
        """토픽에 대한 메시지 핸들러 등록(payload 는 dict)."""
        self._handlers[topic] = handler

    def on_connection_change(self, cb: Callable[[bool], None]) -> None:
        self._connect_cbs.append(cb)

    def connect(self) -> None:
        self._client.connect_async(
            config.BROKER_HOST, config.BROKER_PORT, config.BROKER_KEEPALIVE
        )
        self._client.loop_start()

    def publish(self, topic: str, payload: dict, retain: bool = False) -> None:
        self._client.publish(
            topic, json.dumps(payload, ensure_ascii=False), qos=config.QOS, retain=retain
        )

    def disconnect(self) -> None:
        if self._online_topic:
            self._client.publish(self._online_topic, "offline", qos=config.QOS, retain=True)
        self._client.loop_stop()
        self._client.disconnect()

    @staticmethod
    def new_request_id() -> str:
        return uuid.uuid4().hex[:8]

    # --- 내부 콜백 -------------------------------------------------------
    def _on_connect(self, client, userdata, flags, reason_code, properties):
        self.connected = not reason_code.is_failure
        if self.connected:
            for topic in self._handlers:
                client.subscribe(topic, qos=config.QOS)
            if self._online_topic:
                client.publish(self._online_topic, "online", qos=config.QOS, retain=True)
        for cb in self._connect_cbs:
            cb(self.connected)

    def _on_disconnect(self, client, userdata, flags, reason_code, properties):
        self.connected = False
        for cb in self._connect_cbs:
            cb(False)

    def _on_message(self, client, userdata, msg):
        handler = self._handlers.get(msg.topic)
        if not handler:
            return
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return
        handler(payload)
