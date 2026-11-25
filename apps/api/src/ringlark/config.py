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

    # Who the messages come from. Every text and email the system writes names this business, so the placeholders below keep the system in draft mode (docs 04).
    company_name: str = "Your Company"  # COMPANY_NAME: said in greetings, texts and emails
    company_address: str = ""  # COMPANY_ADDRESS: the postal address printed under every email follow up
    booking_url: str = ""  # BOOKING_URL: the page a "booking link" text points to. Empty means that text is not offered outside demo mode
    appointment_name: str = ""  # APPOINTMENT_NAME: what the meeting is called in texts, for example "check up" or "consultation" (empty: "appointment")
    tool_token_secret: str = ""  # TOOL_TOKEN_SECRET: key for the per call tool tokens. Empty means a key made from SESSION_SECRET
    allowed_calling_countries: str = "+1"  # ALLOWED_CALLING_COUNTRIES: country calling codes the dialer may call, comma separated
    allow_extended_hours: bool = False  # ALLOW_EXTENDED_HOURS: lets a campaign call before 08:00 or after 21:00 callee local time (off by default)
    max_inbound_calls: int = Field(default=5, ge=1, le=100)  # MAX_INBOUND_CALLS: inbound calls answered at the same time
    max_inbound_per_number_hour: int = Field(default=6, ge=1, le=100)  # MAX_INBOUND_PER_NUMBER_HOUR: inbound calls answered per caller number per hour

    @property
    def window_bounds(self) -> tuple[int, int]:
        """The earliest start and latest end, in the callee's local hours, that a campaign may use."""
        return (0, 24) if self.allow_extended_hours else (8, 21)

    @property
    def calling_codes(self) -> tuple[str, ...]:
        return tuple(c.strip() for c in self.allowed_calling_countries.split(",") if c.strip().startswith("+"))

    @property
    def real_calling(self) -> bool:
        """True when a real phone or voice adapter is selected (not the offline seed ones)."""
        return self.telephony_adapter != "seed" or self.voice_adapter != "seed"

    def identity_problems(self) -> list[str]:
        """Business facts and addresses the live path needs. While any is missing outside demo mode the system stays in draft mode (see Ctx.effective)."""
        if self.demo_mode:
            return []
        out: list[str] = []
        if self.company_name.strip() in ("", "Your Company"):
            out.append("COMPANY_NAME is still the placeholder, so texts and emails would not say who they are from. Set it to your business name.")
        if self.email_adapter != "seed":
            if not self.company_address.strip():
                out.append("COMPANY_ADDRESS is empty. Every email follow up must carry a postal address.")
            if self.email_from.endswith("example.test"):
                out.append("EMAIL_FROM is still the example address.")
        if self.sms_adapter != "seed" and not self.telnyx_from_number:
            out.append("TELNYX_FROM_NUMBER is empty, so a text could not say which number to reply STOP to.")
        if self.mode is Mode.LIVE and self.real_calling:
            # Without these a live call would carry tool addresses that point nowhere, and its webhooks would be refused: stay in draft until they are set.
            if not self.telnyx_public_key:
                out.append("TELNYX_PUBLIC_KEY is empty, so Telnyx webhooks are refused. Calls stay in draft mode until it is set.")
            if not self.ultravox_webhook_secret:
                out.append("ULTRAVOX_WEBHOOK_SECRET is empty, so Ultravox webhooks are refused. Calls stay in draft mode until it is set.")
            if not self.public_base_url.startswith("https://"):
                out.append("PUBLIC_BASE_URL is empty or not an https address, so Ultravox cannot reach the tool endpoints. Calls stay in draft mode until it is set.")
        return out

    def problems(self) -> list[str]:
        out = [p for p in super().problems() if not (self.demo_mode and p.startswith("MODE is live while DEMO_MODE"))]
        out.extend(self.identity_problems())
        if not self.demo_mode and not self.owner_password_hash:
            out.append("OWNER_PASSWORD_HASH is empty. Create one with tools/hash_password.py and set it before you run outside demo mode.")
        if self.mode is Mode.LIVE and not self.demo_mode:
            if self.telephony_adapter == "seed":
                out.append("MODE is live but TELEPHONY_ADAPTER is seed, so no real call can be placed. Set TELEPHONY_ADAPTER=telnyx.")
            if self.voice_adapter == "seed":
                out.append("MODE is live but VOICE_ADAPTER is seed. Set VOICE_ADAPTER=ultravox.")
        return out
