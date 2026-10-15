import smtplib
from email.message import EmailMessage
from .base import ChangeEvent, NotificationError

class EmailNotifier:
    name = "Email"
    def __init__(self, host, port, username, password, sender, recipient, starttls=True):
        self.host, self.port = host, port
        self.username, self.password = username, password
        self.sender, self.recipient, self.starttls = sender, recipient, starttls
    def send(self, event: ChangeEvent) -> None:
        if not self.host or not self.sender or not self.recipient:
            raise NotificationError("Email settings are incomplete.")
        msg = EmailMessage()
        msg["Subject"] = f"Watchtower: {event.kind.title()} — {event.monitor_name}"
        msg["From"], msg["To"] = self.sender, self.recipient
        body = f"{event.monitor_name}\n{event.url}\n\n{event.summary}\n\nDetected: {event.detected_at.isoformat()}"
        if event.dashboard_url:
            body += f"\n\nOpen Watchtower dashboard: {event.dashboard_url}"
        msg.set_content(body)
        try:
            with smtplib.SMTP(self.host, self.port, timeout=10) as server:
                if self.starttls: server.starttls()
                if self.username: server.login(self.username, self.password)
                server.send_message(msg)
        except Exception as exc:
            raise NotificationError(f"Email delivery failed ({type(exc).__name__}).") from None
