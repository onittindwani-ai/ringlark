import email
import imaplib
import smtplib
from email.message import EmailMessage

from mock.mail_servers import FakeMailServers


def test_smtp_accepts_and_stores_message():
    with FakeMailServers() as srv:
        m = EmailMessage()
        m["From"], m["To"], m["Subject"] = "a@x.example.test", "b@y.example.test", "Hello"
        m.set_content("Body text")
        with smtplib.SMTP(srv.host, srv.smtp_port) as s:
            s.send_message(m)
        assert len(srv.store.outbox) == 1
        assert srv.store.outbox[0]["to"] == ["b@y.example.test"]
        assert "Body text" in srv.store.outbox[0]["data"]


def test_imap_search_fetch_and_mark_seen():
    with FakeMailServers() as srv:
        raw = b"From: lead@x.example.test\r\nTo: a@y.example.test\r\nSubject: Re: Hi\r\n\r\nYes please\r\n"
        uid = srv.store.deliver(raw)
        c = imaplib.IMAP4(srv.host, srv.imap_port)
        c.login("demo", "demo-password")
        c.select("INBOX")
        _, data = c.uid("SEARCH", None, "UNSEEN")
        assert data[0].split() == [str(uid).encode()]
        _, parts = c.uid("FETCH", str(uid), "(RFC822)")
        msg = email.message_from_bytes(parts[0][1])
        assert msg["Subject"] == "Re: Hi"
        c.uid("STORE", str(uid), "+FLAGS", "(\\Seen)")
        _, after = c.uid("SEARCH", None, "UNSEEN")
        assert after[0].split() == []
        c.logout()


def test_imap_rejects_bad_login():
    with FakeMailServers() as srv:
        c = imaplib.IMAP4(srv.host, srv.imap_port)
        try:
            c.login("demo", "wrong")
            raise AssertionError("login should fail")
        except imaplib.IMAP4.error:
            pass
