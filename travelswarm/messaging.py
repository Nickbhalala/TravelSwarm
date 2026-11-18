"""Message broker abstraction with RabbitMQ and in-memory implementations."""

from __future__ import annotations

import json
import logging
from collections import defaultdict, deque
from collections.abc import Callable
from typing import Any, Protocol

log = logging.getLogger(__name__)

Message = dict[str, Any]
Handler = Callable[[Message], None]


class Broker(Protocol):
    def publish(self, queue: str, message: Message) -> None: ...


class InMemoryBroker:
    """For tests and single-process demos. `drain` delivers queued messages to a handler."""

    def __init__(self) -> None:
        self.queues: dict[str, deque[Message]] = defaultdict(deque)

    def publish(self, queue: str, message: Message) -> None:
        self.queues[queue].append(json.loads(json.dumps(message)))  # same copy semantics as wire

    def drain(self, queue: str, handler: Handler, limit: int = 100) -> int:
        n = 0
        while self.queues[queue] and n < limit:
            handler(self.queues[queue].popleft())
            n += 1
        return n


class RabbitMQBroker:
    """Durable queues, persistent messages, manual acks, prefetch 1.

    A message is acked only after the handler returns, so a worker crash mid-plan means
    RabbitMQ redelivers it to another worker. Handlers must therefore be idempotent
    (the worker uses an atomic DB claim for that).
    """

    def __init__(self, url: str, queues: list[str]) -> None:
        import pika  # imported here so the gateway's tests don't need a broker

        self._pika = pika
        self._params = pika.URLParameters(url)
        self._queues = queues
        self._connection: Any = None
        self._channel: Any = None

    def _ensure_channel(self) -> Any:
        if self._channel is None or self._channel.is_closed:
            self._connection = self._pika.BlockingConnection(self._params)
            self._channel = self._connection.channel()
            for q in self._queues:
                self._channel.queue_declare(queue=q, durable=True)
            self._channel.confirm_delivery()
        return self._channel

    def publish(self, queue: str, message: Message) -> None:
        body = json.dumps(message).encode()
        props = self._pika.BasicProperties(
            content_type="application/json",
            delivery_mode=self._pika.DeliveryMode.Persistent,
        )
        try:
            self._ensure_channel().basic_publish("", queue, body, props, mandatory=True)
        except (self._pika.exceptions.AMQPConnectionError, self._pika.exceptions.ChannelClosed):
            # One reconnect attempt covers idle connections dropped by the broker.
            self._channel = None
            self._ensure_channel().basic_publish("", queue, body, props, mandatory=True)

    def consume(self, queue: str, handler: Handler) -> None:
        channel = self._ensure_channel()
        channel.basic_qos(prefetch_count=1)

        def on_message(ch: Any, method: Any, _props: Any, body: bytes) -> None:
            try:
                handler(json.loads(body))
            except Exception:
                # The handler records its own failures; anything escaping is a bug or an
                # infrastructure error, so let RabbitMQ redeliver.
                log.exception("handler crashed; message will be redelivered")
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
                return
            ch.basic_ack(delivery_tag=method.delivery_tag)

        channel.basic_consume(queue=queue, on_message_callback=on_message)
        log.info("consuming from %s", queue)
        channel.start_consuming()

    def close(self) -> None:
        if self._connection and self._connection.is_open:
            self._connection.close()
