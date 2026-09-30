"""Outgoing email (the password recovery link).

Blocking (`smtplib`): call it from a background task or a worker thread, never from the event loop.
It raises on any failure, so the caller decides what to log; nothing here swallows an error.
"""
import smtplib
import ssl
from email.message import EmailMessage

from ..config import Config

config = Config()

SMTP_TIMEOUT_SECONDS = 15
SENDER_NAME = "La Viciación"


class EmailNotConfigured(Exception):
    """SMTP_HOST, SMTP_EMAIL or PUBLIC_URL is missing."""


def build_message(to: str, subject: str, text: str, html: str | None = None) -> EmailMessage:
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = f"{SENDER_NAME} <{config.SMTP_EMAIL}>"
    message["To"] = to
    message.set_content(text)
    if html:
        message.add_alternative(html, subtype="html")
    return message


def send_email(to: str, subject: str, text: str, html: str | None = None) -> None:
    """Send one message to one recipient."""
    if not config.MAIL_ENABLED:
        raise EmailNotConfigured("SMTP_HOST, SMTP_EMAIL and PUBLIC_URL must be set")
    message = build_message(to, subject, text, html)
    context = ssl.create_default_context()
    if config.SMTP_SECURITY == "ssl":
        server = smtplib.SMTP_SSL(config.SMTP_HOST, config.SMTP_PORT, timeout=SMTP_TIMEOUT_SECONDS, context=context)
    else:  # starttls, or "none" (no encryption at all: only for a local mail catcher, never for a real server)
        server = smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=SMTP_TIMEOUT_SECONDS)
    with server:
        if config.SMTP_SECURITY == "starttls":
            server.starttls(context=context)
        if config.SMTP_PASS:
            server.login(config.SMTP_USER, config.SMTP_PASS)
        server.send_message(message)
