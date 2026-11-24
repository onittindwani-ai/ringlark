"""Adapter interfaces and shared helpers. Every category has an offline `seed` adapter."""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol
from urllib.parse import urlparse

from sendora_core.adapters import AdapterError


@dataclass
class InboundEmail:
    external_id: str
    from_addr: str
    to_addr: str
    subject: str
    body: str
    received_at: datetime | None = None


@dataclass
class InboundSms:
    external_id: str
    from_number: str
    to_number: str
    text: str


@dataclass
class Booking:
    external_id: str
    starts_at: datetime
    ends_at: datetime


@dataclass
class PersonRecord:
    email: str = ""
    first_name: str = ""
    last_name: str = ""
    title: str = ""
    phone: str = ""
    company: str = ""
    extra: dict = field(default_factory=dict)


@dataclass
class VoiceCall:
    """What the voice engine gives back when a call is created."""
    call_id: str
    join_url: str


@dataclass
class PlacedCall:
    call_control_id: str
    call_session_id: str = ""


class EmailAdapter(Protocol):
    def send(self, *, from_addr: str, to: str, subject: str, body: str) -> str: ...
    def fetch_replies(self) -> list[InboundEmail]: ...
    def healthcheck(self) -> tuple[bool, str]: ...


class SmsAdapter(Protocol):
    def send(self, *, to: str, text: str) -> str: ...
    def healthcheck(self) -> tuple[bool, str]: ...


class TelephonyAdapter(Protocol):
    """Places and controls phone calls (Telnyx Call Control)."""
    def place_call(self, *, to: str, from_number: str, client_state: str, amd: bool) -> PlacedCall: ...
    def answer(self, call_control_id: str) -> None: ...
    def start_stream(self, call_control_id: str, join_url: str) -> None: ...
    def transfer(self, call_control_id: str, to: str) -> None: ...
    def send_dtmf(self, call_control_id: str, digits: str) -> None: ...
    def speak(self, call_control_id: str, text: str) -> None: ...
    def hangup(self, call_control_id: str) -> None: ...
    def healthcheck(self) -> tuple[bool, str]: ...


class VoiceAdapter(Protocol):
    """Creates a call on the voice engine (Ultravox) and reads back what was said."""
    def create_call(self, *, system_prompt: str, voice: str, first_message: str, tools: list[dict], max_seconds: int, external_voice: dict | None = None) -> VoiceCall: ...
    def transcript(self, call_id: str) -> list[dict]: ...
    def healthcheck(self) -> tuple[bool, str]: ...


class CalendarAdapter(Protocol):
    def slots(self, start: datetime, end: datetime) -> list[datetime]: ...
    def book(self, *, start: datetime, name: str, email: str, timezone: str) -> Booking: ...
    def healthcheck(self) -> tuple[bool, str]: ...


class CrmAdapter(Protocol):
    def upsert_person(self, person: PersonRecord) -> str: ...
    def find_by_phone(self, phone: str) -> PersonRecord | None: ...
    def healthcheck(self) -> tuple[bool, str]: ...


def safe_base_url(url: str, *, allow_http_local: bool = False) -> str:
    """Refuse base URLs that point at the local network or non web schemes (SSRF guard for URLs a user can set).

    Only https is accepted. Hosts that resolve to private, loopback, link local or reserved addresses are refused,
    unless `allow_http_local` is set (tests and a self hosted CRM on the same machine, a deliberate choice).
    """
    u = urlparse(url)
    if u.scheme not in {"https", "http"} or not u.hostname:
        raise AdapterError("The URL must start with https:// and include a host name.")
    if u.username or u.password:
        raise AdapterError("Put credentials in the key field, not in the URL.")
    local_ok = allow_http_local
    if u.scheme == "http" and not local_ok:
        raise AdapterError("Use an https:// URL.")
    try:
        infos = socket.getaddrinfo(u.hostname, u.port or (443 if u.scheme == "https" else 80), proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise AdapterError(f"The host {u.hostname} could not be found.") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified) and not local_ok:
            raise AdapterError("That URL points at a private or local address, which is refused.")
    return url.rstrip("/")
