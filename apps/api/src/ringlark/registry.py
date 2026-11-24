"""One registry of every adapter, with its tier. Demo mode can only build the offline seed adapters."""

from __future__ import annotations

from dataclasses import dataclass

from ringlark.adapters import seed
from ringlark.adapters.calcom import CalcomCalendar
from ringlark.adapters.crm import TwentyCrm
from ringlark.adapters.smtp_imap import SmtpImapEmail
from ringlark.adapters.telnyx import TelnyxCalls, TelnyxSms
from ringlark.adapters.ultravox import UltravoxVoice
from sendora_core.adapters import AdapterError, AdapterRegistry, AdapterSpec

CATEGORIES = ("telephony", "voice", "sms", "calendar", "crm", "email")
ENV_VARS = {
    ("telephony", "telnyx"): ["TELNYX_API_KEY", "TELNYX_PUBLIC_KEY", "TELNYX_CONNECTION_ID", "TELNYX_FROM_NUMBER", "PUBLIC_BASE_URL"],
    ("voice", "ultravox"): ["ULTRAVOX_API_KEY", "ULTRAVOX_WEBHOOK_SECRET", "PUBLIC_BASE_URL"],
    ("sms", "telnyx"): ["TELNYX_API_KEY", "TELNYX_PUBLIC_KEY", "TELNYX_FROM_NUMBER"],
    ("calendar", "calcom"): ["CALCOM_API_KEY", "CALCOM_EVENT_TYPE_ID"],
    ("crm", "twenty"): ["TWENTY_BASE_URL", "TWENTY_API_KEY"],
    ("email", "smtp_imap"): ["SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD"],
}


def build_registry(settings) -> AdapterRegistry:
    reg = AdapterRegistry(settings)
    add = lambda c, n, t, f, notes="": reg.register(AdapterSpec(c, n, t, f, False, notes))  # noqa: E731
    recipe = lambda name: (lambda s: (_ for _ in ()).throw(AdapterError(f"{name} is a recipe only. See prompts/.")))  # noqa: E731
    add("telephony", "seed", "A", seed.SeedTelephony, "Offline. No call is placed.")
    add("telephony", "telnyx", "A", TelnyxCalls, "Tested against a mock written from the public docs, not the real service.")
    add("voice", "seed", "A", seed.SeedVoice, "Offline. No audio.")
    add("voice", "ultravox", "A", UltravoxVoice, "Tested against a mock written from the public docs, not the real service.")
    add("voice", "vapi", "C", recipe("Vapi"), "Recipe prompt, not built.")
    add("sms", "seed", "A", seed.SeedSms, "Offline.")
    add("sms", "telnyx", "A", TelnyxSms, "Tested against a mock written from the public docs, not the real service.")
    add("calendar", "seed", "A", seed.SeedCalendar, "Offline example times.")
    add("calendar", "calcom", "A", CalcomCalendar, "Tested against a mock written from the public docs, not the real service.")
    add("crm", "seed", "A", seed.SeedCrm, "Offline. The Ringlark database is the CRM.")
    add("crm", "twenty", "A", TwentyCrm, "Tested against a mock. The real field names are unverified.")
    add("email", "seed", "A", seed.SeedEmail, "Offline. Nothing leaves this machine.")
    add("email", "smtp_imap", "B", SmtpImapEmail, "Tested against a fake SMTP and IMAP server, not a real mail host.")
    add("email", "sendkit", "C", recipe("SendKit"), "Recipe prompt, not built.")
    return reg


@dataclass
class AdapterSet:
    telephony: object
    voice: object
    sms: object
    calendar: object
    crm: object
    email: object


def build_adapters(settings, registry: AdapterRegistry | None = None) -> AdapterSet:
    reg = registry or build_registry(settings)
    choice = {c: getattr(settings, f"{c}_adapter") for c in CATEGORIES}
    if settings.demo_mode:
        bad = {c: n for c, n in choice.items() if n != "seed"}
        if bad:
            raise AdapterError(f"DEMO_MODE is on, so only offline adapters can be used. Change {', '.join(f'{c.upper()}_ADAPTER' for c in bad)} or turn DEMO_MODE off.")
    return AdapterSet(**{c: reg.get(c, n) for c, n in choice.items()})
