"""SMTP 이메일 알림."""

from __future__ import annotations

import smtplib
from email.message import EmailMessage

from ..config import MailConfig


class EmailNotifier:
    name = "email"

    def __init__(self, config: MailConfig | None = None) -> None:
        self.config = config or MailConfig.from_env()

    def build(self, subject: str, text: str, html: str) -> EmailMessage:
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = self.config.sender
        message["To"] = ", ".join(self.config.recipients)
        message.set_content(text)
        if html:
            message.add_alternative(html, subtype="html")
        return message

    def send(self, subject: str, text: str, html: str) -> None:  # noqa: A002
        message = self.build(subject, text, html)
        config = self.config
        if config.port == 465:
            with smtplib.SMTP_SSL(config.host, config.port, timeout=30) as server:
                server.login(config.user, config.password)
                server.send_message(message)
            return
        with smtplib.SMTP(config.host, config.port, timeout=30) as server:
            server.ehlo()
            server.starttls()
            server.login(config.user, config.password)
            server.send_message(message)
