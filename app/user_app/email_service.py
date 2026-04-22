"""Service for sending user account emails"""

import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path

from app.core.branding import COLOR_PRIMARY, COMPANY_NAME, apply_branding
from app.core.config import settings


logger = logging.getLogger(__name__)


class UserEmailService:
    """Service for sending user account creation emails"""

    def __init__(self):
        self.smtp_host = settings.SMTP_HOST
        self.smtp_port = settings.SMTP_PORT
        self.smtp_user = settings.SMTP_USER
        self.smtp_password = settings.SMTP_PASSWORD
        self.from_email = settings.SMTP_FROM_EMAIL
        self.smtp_tls = settings.SMTP_TLS

    def send_welcome_email(self, email: str, user_name: str, password: str) -> bool:
        """Envoie un email de bienvenue avec les identifiants de connexion"""
        try:
            if not self.smtp_host:
                logger.warning("Configuration SMTP manquante. Email non envoyé.")
                return False

            subject = "Bienvenue - Votre compte a été créé"
            html_content = self._render_welcome_template(email, user_name, password)
            plain_content = self._render_plain_text(email, user_name, password)

            message = MIMEMultipart("alternative")
            message["Subject"] = subject
            message["From"] = self.from_email
            message["To"] = email

            message.attach(MIMEText(plain_content, "plain", "utf-8"))
            message.attach(MIMEText(html_content, "html", "utf-8"))

            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                if self.smtp_tls:
                    server.starttls()
                if self.smtp_user and self.smtp_password:
                    server.login(self.smtp_user, self.smtp_password)
                server.send_message(message)

            logger.info(f"Email de bienvenue envoyé avec succès à {email}")
            return True

        except smtplib.SMTPException as e:
            logger.error(f"Erreur SMTP lors de l'envoi de l'email à {email}: {e}")
            return False
        except Exception as e:
            logger.error(f"Erreur inattendue lors de l'envoi de l'email à {email}: {e}")
            return False

    def _render_welcome_template(self, email: str, user_name: str, password: str) -> str:
        """Charge et rend le template HTML de bienvenue"""
        template_path = Path(__file__).parent / "templates" / "welcome_email.html"

        try:
            with open(template_path, "r", encoding="utf-8") as f:
                template_content = f.read()

            html_content = apply_branding(template_content)
            html_content = html_content.replace("{{ user_name }}", user_name)
            html_content = html_content.replace("{{ user_email }}", email)
            html_content = html_content.replace("{{ password }}", password)
            return html_content

        except FileNotFoundError:
            logger.error(f"Template d'email introuvable: {template_path}")
            return self._render_fallback_html(email, user_name, password)
        except Exception as e:
            logger.error(f"Erreur lors du rendu du template: {e}")
            return self._render_fallback_html(email, user_name, password)

    def _render_plain_text(self, email: str, user_name: str, password: str) -> str:
        """Génère la version texte brut de l'email"""
        lines = [
            COMPANY_NAME,
            "=" * 50,
            "",
            f"Bonjour {user_name},",
            "",
            f"Votre compte a été créé avec succès sur {COMPANY_NAME}.",
            "",
            "VOS IDENTIFIANTS DE CONNEXION",
            "-" * 30,
            f"Email : {email}",
            f"Mot de passe : {password}",
            "",
            "IMPORTANT : Changez votre mot de passe à la première connexion.",
            "",
            f"© 2024 {COMPANY_NAME}.",
        ]
        return "\n".join(lines)

    def _render_fallback_html(self, email: str, user_name: str, password: str) -> str:
        """Template HTML de secours (utilisé si le fichier template est introuvable)."""
        return f"""<!DOCTYPE html>
<html lang="fr">
<head><meta charset="UTF-8"><title>Bienvenue - {COMPANY_NAME}</title></head>
<body style="font-family:Arial,sans-serif;background-color:#F5F7F7;padding:20px;color:#102624;">
  <div style="max-width:600px;margin:0 auto;background:#ffffff;padding:32px;border-radius:12px;border:1px solid #D8DFDE;">
    <h2 style="color:{COLOR_PRIMARY};text-align:center;margin:0 0 20px 0;">Bienvenue sur {COMPANY_NAME}</h2>
    <p>Bonjour <strong>{user_name}</strong>,</p>
    <p>Votre compte a été créé avec succès.</p>
    <div style="background:#E8F2F0;padding:20px;border-radius:8px;border:1px solid #D8DFDE;">
      <p><strong>Email :</strong> {email}</p>
      <p><strong>Mot de passe :</strong> <code style="color:{COLOR_PRIMARY};font-weight:bold;">{password}</code></p>
    </div>
    <p style="color:#78350F;background:#FEF3C7;padding:10px;border-left:4px solid #B45309;border-radius:4px;">
      Changez votre mot de passe à la première connexion.
    </p>
  </div>
</body>
</html>"""
