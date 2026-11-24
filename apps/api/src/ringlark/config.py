"""Ringlark settings. Subclass of the base settings with this system's variables (names only, never values, in docs)."""

from __future__ import annotations

from pydantic import Field

from sendora_core.settings import BaseAppSettings, Mode


class Settings(BaseAppSettings):
    app_name: str = "ringlark"
    database_url: str = "sqlite:///./ringlark.sqlite3"

    owner_email: str = "owner@example.test"
    owner_password_hash: str | None = None
    approver_email: str | None = None
    approver_password_hash: str | None = None
    viewer_email: str | None = None  # read only role: may look at everything, change nothing
    viewer_password_hash: str | None = None
    login_burst: int = Field(default=5, ge=1, le=1000)  # sign in tries in a row before a short wait; the browser tests raise it

    telephony_adapter: str = "seed"  # seed or telnyx
    voice_adapter: str = "seed"  # seed or ultravox
    sms_adapter: str = "seed"
    calendar_adapter: str = "seed"
    crm_adapter: str = "seed"
    email_adapter: str = "seed"

    telnyx_api_key: str = ""
    telnyx_public_key: str = ""
    telnyx_connection_id: str = ""
    telnyx_from_number: str = ""
    telnyx_base_url: str = "https://api.telnyx.com"

    ultravox_api_key: str = ""
    ultravox_webhook_secret: str = ""
    ultravox_base_url: str = "https://api.ultravox.ai"
    public_base_url: str = ""  # where Ultravox reaches the tool endpoints, for example your Railway URL

    calcom_api_key: str = ""
    calcom_event_type_id: int = 0
    calcom_webhook_secret: str = ""
    calcom_base_url: str = "https://api.cal.com"
    calcom_slots_version: str = "2024-09-04"
    calcom_bookings_version: str = "2026-02-25"

    twenty_base_url: str = ""
    twenty_api_key: str = ""

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = True
    imap_host: str = ""
    imap_port: int = 993
    imap_use_ssl: bool = True
    email_from: str = "calls@example.test"

    webhook_shared_secret: str = ""
    # Decided defaults: a safe starting point the implementer can change per client (docs 04 and 14).
    default_window_start: int = Field(default=9, ge=0, le=23)
    default_window_end: int = Field(default=17, ge=1, le=24)
    default_daily_cap: int = Field(default=50, ge=1, le=5000)
    follow_ups_need_approval: bool = True
    human_transfer_hours: str = "09:00-17:00"  # when a person can take a transferred call (decided default, changeable)
    office_timezone: str = "America/New_York"
    sms_window_start: int = 8
    sms_window_end: int = 21
    handoff_dir: str = "./handoff"
    seed_dir: str = ""

    def problems(self) -> list[str]:
        out = [p for p in super().problems() if not (self.demo_mode and p.startswith("MODE is live while DEMO_MODE"))]
        if not self.demo_mode and not self.owner_password_hash:
            out.append("OWNER_PASSWORD_HASH is empty. Create one with tools/hash_password.py and set it before you run outside demo mode.")
        if self.mode is Mode.LIVE and not self.demo_mode:
            if self.telephony_adapter == "seed":
                out.append("MODE is live but TELEPHONY_ADAPTER is seed, so no real call can be placed. Set TELEPHONY_ADAPTER=telnyx.")
            if self.voice_adapter == "seed":
                out.append("MODE is live but VOICE_ADAPTER is seed. Set VOICE_ADAPTER=ultravox.")
            if not self.telnyx_public_key:
                out.append("TELNYX_PUBLIC_KEY is empty, so Telnyx webhooks are refused.")
            if not self.ultravox_webhook_secret:
                out.append("ULTRAVOX_WEBHOOK_SECRET is empty, so Ultravox webhooks are refused.")
            if not self.public_base_url:
                out.append("PUBLIC_BASE_URL is empty, so Ultravox cannot reach the tool endpoints.")
        return out
