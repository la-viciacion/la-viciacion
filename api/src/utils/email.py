import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from ..config import Config
from ..utils.logger import LogManager

log_manager = LogManager()
logger = log_manager.get_logger()

config = Config()


class Email:
    def __init__(self):
        self.smtp_server = config.SMTP_HOST
        self.port = config.SMTP_PORT  # For starttls
        self.sender_email = config.SMTP_EMAIL
        self.username = config.SMTP_USER
        self.password = config.SMTP_PASS

    def send_mail(self, receivers, subject, msg):
        message = MIMEMultipart()
        message["Subject"] = subject
        message["From"] = "La Viciacion <" + self.sender_email + ">"
        html_message = MIMEText(msg, "html")
        message.attach(html_message)
        context = ssl.create_default_context()
        logger.info("Sending email...")
        try:
            server = smtplib.SMTP(self.smtp_server, self.port)
            server.starttls(context=context)  # Secure the connection
            server.login(self.sender_email, self.password)
            for email in receivers:
                message["To"] = email
                server.sendmail(self.sender_email, email, message.as_string())
            logger.info("Email sent!")
        except Exception as e:
            logger.error(e)
            return e
        finally:
            server.quit()
        return "Email sent!"
