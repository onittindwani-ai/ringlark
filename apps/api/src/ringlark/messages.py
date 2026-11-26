"""The words of every text and email the system writes on its own. They name the real business (settings and the agent), never a demo company,
and the compliance lines are added here, so no path can send a message without them."""

from __future__ import annotations

from ringlark.models import Agent

STOP_LINE = "Reply STOP to opt out."
DEMO_LINK = "https://example.test/book (demo link)"
SMS_KINDS = ("booking_link", "confirmation", "callback")
DEMO_MARKERS = ("sample practice", "example.test")


def company_of(settings, agent: Agent | None) -> str:
    """The business the person hears about: the agent's own company when it has one, else COMPANY_NAME."""
    name = ((agent.company if agent else "") or "").strip()
    return name or settings.company_name.strip()


def appointment(settings) -> str:
    return settings.appointment_name.strip() or ("check up" if settings.demo_mode else "appointment")


def booking_link(settings) -> str:
    """The booking page for the text. Empty outside demo mode when BOOKING_URL is not set, and then that text is not offered."""
    return settings.booking_url.strip() or (DEMO_LINK if settings.demo_mode else "")


def ensure_stop_line(text: str) -> str:
    """Every text carries the opt out line, whoever wrote the body."""
    return text if "stop" in text.lower() and "opt out" in text.lower() else f"{text.rstrip()} {STOP_LINE}"


def sms_text(settings, agent: Agent | None, kind: str) -> str | None:
    """The fixed text for one kind, or None when it cannot be written (no booking link configured)."""
    company, what = company_of(settings, agent), appointment(settings)
    if kind == "booking_link":
        link = booking_link(settings)
        return ensure_stop_line(f"Hi from {company}. Here is where to manage your booking: {link}") if link else None
    if kind == "confirmation":
        return ensure_stop_line(f"{company}: your {what} is booked. We will see you then.")
    if kind == "callback":
        return ensure_stop_line(f"{company}: sorry we caught you at a busy time. We will call you back at a better time.")
    return None


def email_footer(settings, company: str) -> str:
    parts = [company]
    if settings.company_address.strip():
        parts.append(settings.company_address.strip())
    line = "\n".join(parts)
    if settings.telnyx_from_number:
        line += f"\nDo not want these texts or emails? Text STOP to {settings.telnyx_from_number} and we will stop sending them."
    else:
        line += "\nDo not want these texts or emails? Tell us on the phone and we will stop sending them."
    return line


def booked_email(settings, agent: Agent | None) -> tuple[str, str]:
    """(subject, body) of the email after a booked call."""
    company, what = company_of(settings, agent), appointment(settings)
    body = f"Hello,\n\nYour {what} is booked. Reply to this email if you need to change it.\n\n{company}"
    if settings.demo_mode:
        body += " (a sample practice)"
    return f"Your {what} at {company}", f"{body}\n\n--\n{email_footer(settings, company)}"


def has_demo_text(body: str) -> bool:
    low = (body or "").lower()
    return any(m in low for m in DEMO_MARKERS)
