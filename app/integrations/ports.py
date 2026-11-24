"""Contratos de integración: no realizan llamadas externas."""
from typing import Protocol


class MessageChannel(Protocol):
    def send_message(self, customer_id: str, text: str) -> None: ...


class ParkingSystem(Protocol):
    def get_availability(self) -> str | None: ...
