"""
Email sending via SMTP (aiosmtplib), with a safe fallback to logging when SMTP
isn't configured.

For Gmail specifically: requires an App Password, not the account's normal
password. See server/.env.example for setup steps.
"""
from email.message import EmailMessage

import aiosmtplib

from app.core.config import settings
from app.core.logging import logger


async def send_email(to: str, subject: str, body: str, html_body: str | None = None) -> None:
    if not settings.smtp_configured:
        logger.info(f"[DEV EMAIL - SMTP not configured] To: {to} | Subject: {subject}\n{body}")
        return

    message = EmailMessage()
    message["From"] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL}>"
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)
    if html_body:
        message.add_alternative(html_body, subtype="html")

    try:
        await aiosmtplib.send(
            message,
            hostname=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            username=settings.SMTP_USERNAME,
            password=settings.SMTP_PASSWORD,
            start_tls=settings.SMTP_USE_TLS,
        )
        logger.info(f"Email sent to {to}: {subject}")
    except Exception as exc:  # noqa: BLE001
        logger.error(f"Failed to send email to {to}: {exc}")
