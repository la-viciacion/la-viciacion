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
NL = "\n"


class EmailNotConfigured(Exception):
    """SMTP_HOST, SMTP_EMAIL or PUBLIC_URL is missing."""


def missing_settings() -> list[str]:
    """Names of the variables that keep the email feature off (empty when it is configured)."""
    return [
        name
        for name, value in (
            ("SMTP_HOST", config.SMTP_HOST),
            ("SMTP_EMAIL", config.SMTP_EMAIL),
            ("PUBLIC_URL", config.PUBLIC_URL),
        )
        if not value
    ]


def status() -> dict:
    """What the admin panel shows about the mail setup. Never the password."""
    missing = missing_settings()
    return {
        "configured": not missing,
        "missing": missing,
        "host": config.SMTP_HOST,
        "port": config.SMTP_PORT,
        "security": config.SMTP_SECURITY,
        "from": config.SMTP_EMAIL,
        "public_url": config.PUBLIC_URL,
    }


def send_test_email(to: str, sent_by: str) -> None:
    """A diagnostic message: proves the server accepts our login and delivers to `to`."""
    lines = [
        f"Este es un correo de prueba de La Viciación, pedido por {sent_by} desde el panel de administración.",
        "",
        f"Servidor: {config.SMTP_HOST}:{config.SMTP_PORT} ({config.SMTP_SECURITY})",
        f"Remitente: {config.SMTP_EMAIL}",
        f"Dirección pública: {config.PUBLIC_URL}",
        "",
        "Si lo estás leyendo, la recuperación de contraseña podrá enviar sus enlaces.",
    ]
    send_email(to, "Correo de prueba de La Viciación", NL.join(lines) + NL)


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
