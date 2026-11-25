"""Email over SMTP (send) and IMAP (read replies). Works with Gmail (app password), Outlook and most mail hosts."""

from __future__ import annotations

import email
import imaplib
import smtplib
import ssl
from email.message import EmailMessage
from email.policy import default as default_policy
from email.utils import make_msgid, parseaddr

from ringlark.adapters.base import InboundEmail
from ringlark.util import clean_header, is_valid_email
from sendora_core.adapters import AdapterError
from sendora_core.safety import write_action
from sendora_core.settings import BaseAppSettings


LOOPBACK = {"localhost", "127.0.0.1", "::1"}


def _tls_context() -> ssl.SSLContext:
    """Certificates and host names are checked. Python's own default for smtplib and imaplib does not check them."""
    return ssl.create_default_context()


class SmtpImapEmail:
    def __init__(self, settings):
        self.settings: BaseAppSettings = settings

    def _need(self, *names: str) -> None:
        missing = [n.upper() for n in names if not getattr(self.settings, n)]
        if missing:
            raise AdapterError(f"Set {', '.join(missing)} in your environment first (see docs/04-ENVIRONMENT-VARIABLES.md).")

    def _smtp(self) -> smtplib.SMTP:
        s = self.settings
        if (s.smtp_port != 465 and not s.smtp_use_tls) and s.smtp_host not in LOOPBACK:
            raise AdapterError("SMTP_USE_TLS=false sends the mailbox password in clear text, so it is only allowed for a mail server on this computer.")
        c = smtplib.SMTP_SSL(s.smtp_host, s.smtp_port, timeout=20, context=_tls_context()) if s.smtp_port == 465 else smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=20)
        if s.smtp_port != 465 and s.smtp_use_tls:
            c.starttls(context=_tls_context())
        if s.smtp_user:
            c.login(s.smtp_user, s.smtp_password)
        return c

    def _imap(self) -> imaplib.IMAP4:
        s = self.settings
        if not s.imap_use_ssl and s.imap_host not in LOOPBACK:
            raise AdapterError("IMAP_USE_SSL=false sends the mailbox password in clear text, so it is only allowed for a mail server on this computer.")
        c = imaplib.IMAP4_SSL(s.imap_host, s.imap_port, ssl_context=_tls_context()) if s.imap_use_ssl else imaplib.IMAP4(s.imap_host, s.imap_port)
        c.login(s.smtp_user, s.smtp_password)
        return c

    @write_action("email.send")
    def send(self, *, from_addr: str, to: str, subject: str, body: str) -> str:
        self._need("smtp_host")
        if not is_valid_email(to):
            raise AdapterError("The recipient must be one plain email address.")  # never a list: one booking email must not reach several people
        m = EmailMessage()
        m["From"], m["To"], m["Subject"] = clean_header(from_addr), clean_header(to), clean_header(subject)
        m["Message-ID"] = make_msgid(domain=from_addr.rsplit("@", 1)[-1] or "localhost")
        m.set_content(body)
        try:
            with self._smtp() as c:
                c.send_message(m, to_addrs=[to.strip()])
        except smtplib.SMTPAuthenticationError as exc:
            raise AdapterError("The mail server rejected the user name or password. For Gmail use an app password.") from exc
        except (smtplib.SMTPException, OSError) as exc:
            raise AdapterError(f"Could not send through {self.settings.smtp_host}: {type(exc).__name__}.") from exc
        return m["Message-ID"]

    def fetch_replies(self) -> list[InboundEmail]:
        self._need("imap_host", "smtp_user")
        out: list[InboundEmail] = []
        try:
            c = self._imap()
            try:
                c.select("INBOX")
                _, data = c.uid("SEARCH", None, "UNSEEN")
                for uid in (data[0] or b"").split():
                    _, parts = c.uid("FETCH", uid.decode(), "(RFC822)")
                    if not parts or not parts[0]:
                        continue
                    msg = email.message_from_bytes(parts[0][1], policy=default_policy)
                    body_part = msg.get_body(preferencelist=("plain",))
                    text = body_part.get_content() if body_part else ""
                    out.append(InboundEmail(external_id=str(msg["Message-ID"] or f"imap-{uid.decode()}"), from_addr=parseaddr(str(msg["From"] or ""))[1],
                                            to_addr=parseaddr(str(msg["To"] or ""))[1], subject=str(msg["Subject"] or ""), body=text[:20000]))
                    c.uid("STORE", uid.decode(), "+FLAGS", "(\\Seen)")
            finally:
                try:
                    c.logout()
                except Exception:
                    pass
        except imaplib.IMAP4.error as exc:
            raise AdapterError("The inbox rejected the login or the command. Check the user name and app password.") from exc
        except OSError as exc:
            raise AdapterError(f"Could not reach the inbox at {self.settings.imap_host}: {type(exc).__name__}.") from exc
        return out

    def healthcheck(self) -> tuple[bool, str]:
        try:
            self._need("smtp_host", "imap_host")
            with self._smtp() as c:
                c.noop()
            c = self._imap()
            c.logout()
            return True, "Connected to the mail server and the inbox."
        except AdapterError as exc:
            return False, str(exc)
        except Exception as exc:
            return False, f"Could not connect: {type(exc).__name__}. Check host, port and password."
