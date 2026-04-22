"""Service for sending OTP emails"""

import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from typing import Optional

from app.core.branding import COLOR_PRIMARY, COMPANY_NAME, apply_branding
from app.core.config import settings


logger = logging.getLogger(__name__)


class EmailService:
    """Service for sending OTP emails"""

    def __init__(self):
        """Initialize email service with SMTP configuration"""
        self.smtp_host = settings.SMTP_HOST
        self.smtp_port = settings.SMTP_PORT
        self.smtp_user = settings.SMTP_USER
        self.smtp_password = settings.SMTP_PASSWORD
        self.from_email = settings.SMTP_FROM_EMAIL
        self.smtp_tls = settings.SMTP_TLS

    async def send_otp_email(
        self,
        email: str,
        otp: str,
        user_name: Optional[str] = None
    ) -> bool:
        """
        Envoie un email contenant le code OTP

        Args:
            email: Adresse email du destinataire
            otp: Code OTP à 6 chiffres
            user_name: Nom de l'utilisateur (optionnel)

        Returns:
            bool: True si l'email a été envoyé avec succès, False sinon

        Raises:
            RuntimeError: Si la configuration SMTP n'est pas définie
        """
        try:
            # Vérifier la configuration SMTP
            if not self.smtp_host:
                logger.error("Configuration SMTP manquante. Impossible d'envoyer l'email.")
                raise RuntimeError("Configuration SMTP non définie")

            subject = "Code de vérification - Réinitialisation mot de passe"

            # Charger le template HTML
            html_content = self._render_otp_template(otp, user_name)
            plain_content = self._render_plain_text(otp, user_name)

            # Créer le message
            message = MIMEMultipart("alternative")
            message["Subject"] = subject
            message["From"] = self.from_email
            message["To"] = email

            # Attacher les versions texte et HTML
            part1 = MIMEText(plain_content, "plain", "utf-8")
            part2 = MIMEText(html_content, "html", "utf-8")
            message.attach(part1)
            message.attach(part2)

            # Envoyer l'email
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                if self.smtp_tls:
                    server.starttls()
                if self.smtp_user and self.smtp_password:
                    server.login(self.smtp_user, self.smtp_password)
                server.send_message(message)

            logger.info(f"Email OTP envoyé avec succès à {email}")
            return True

        except smtplib.SMTPAuthenticationError as e:
            logger.exception(
                "Authentification SMTP refusée lors de l'envoi à %s "
                "(code=%s). Vérifier SMTP_USER/SMTP_PASSWORD: pour Gmail, "
                "il faut un App Password (2FA requise) et non le mot de "
                "passe du compte. Message serveur: %r",
                email,
                getattr(e, "smtp_code", "?"),
                getattr(e, "smtp_error", b""),
            )
            return False
        except smtplib.SMTPException as e:
            logger.exception(
                "Erreur SMTP lors de l'envoi de l'email à %s: %s",
                email,
                e,
            )
            return False
        except Exception:
            logger.exception(
                "Erreur inattendue lors de l'envoi de l'email à %s",
                email,
            )
            return False

    async def send_password_changed_email(
        self,
        email: str,
        user_name: Optional[str] = None,
    ) -> bool:
        """Send a confirmation email after a successful password reset.

        Args:
            email: Destination email address.
            user_name: Recipient display name (optional).

        Returns:
            ``True`` if the email was sent, ``False`` otherwise. Failures
            are logged but never raised — the password has already been
            reset in DB at this point and the caller should not roll that
            back just because the confirmation email failed.
        """
        try:
            if not self.smtp_host:
                logger.error(
                    "Configuration SMTP manquante. Impossible d'envoyer "
                    "la confirmation de changement de mot de passe."
                )
                return False

            subject = "Votre mot de passe a été modifié"
            html_content = self._render_password_changed_template(user_name)
            plain_content = self._render_password_changed_plain_text(user_name)

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

            logger.info(
                "Email de confirmation de changement de mot de passe "
                "envoyé avec succès à %s",
                email,
            )
            return True

        except smtplib.SMTPAuthenticationError as e:
            logger.exception(
                "Authentification SMTP refusée lors de l'envoi de la "
                "confirmation à %s (code=%s). Vérifier SMTP_USER/"
                "SMTP_PASSWORD. Message serveur: %r",
                email,
                getattr(e, "smtp_code", "?"),
                getattr(e, "smtp_error", b""),
            )
            return False
        except smtplib.SMTPException as e:
            logger.exception(
                "Erreur SMTP lors de l'envoi de la confirmation à %s: %s",
                email,
                e,
            )
            return False
        except Exception:
            logger.exception(
                "Erreur inattendue lors de l'envoi de la confirmation à %s",
                email,
            )
            return False

    def _render_password_changed_template(
        self,
        user_name: Optional[str],
    ) -> str:
        """Render the confirmation HTML body."""
        template_path = (
            Path(__file__).parent.parent
            / "templates"
            / "password_changed_email.html"
        )
        display_name = user_name if user_name else "Utilisateur"

        try:
            with open(template_path, "r", encoding="utf-8") as f:
                template_content = f.read()

            html_content = apply_branding(template_content)
            html_content = html_content.replace(
                "{{ user_name }}", display_name
            )
            return html_content
        except FileNotFoundError:
            logger.error(
                "Template de confirmation introuvable: %s", template_path
            )
            return self._render_password_changed_fallback_html(display_name)
        except Exception as e:
            logger.error(
                "Erreur lors du rendu du template de confirmation: %s", e
            )
            return self._render_password_changed_fallback_html(display_name)

    def _render_password_changed_plain_text(
        self,
        user_name: Optional[str],
    ) -> str:
        """Render the confirmation plain-text body."""
        display_name = user_name if user_name else "Utilisateur"

        lines = [
            COMPANY_NAME,
            "=" * 50,
            "",
            f"Bonjour {display_name},",
            "",
            "Nous vous confirmons que le mot de passe de votre compte a",
            "bien été réinitialisé.",
            "",
            "Vous pouvez maintenant vous connecter avec votre nouveau",
            "mot de passe.",
            "",
            "⚠️  SI CE CHANGEMENT N'EST PAS DE VOTRE FAIT",
            "Contactez immédiatement votre administrateur système. Votre",
            "compte doit être sécurisé au plus vite.",
            "",
            "=" * 50,
            f"Cet email a été envoyé automatiquement par {COMPANY_NAME}.",
            "Merci de ne pas répondre à cet email.",
            "",
            f"© 2024 {COMPANY_NAME}. Tous droits réservés.",
        ]
        return "\n".join(lines)

    def _render_password_changed_fallback_html(
        self,
        display_name: str,
    ) -> str:
        """Fallback HTML if the main template cannot be read."""
        return f"""
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <title>Mot de passe modifié - {COMPANY_NAME}</title>
</head>
<body style="font-family: Arial, sans-serif; line-height: 1.6; color: #102624; background-color: #F5F7F7;">
    <div style="max-width: 600px; margin: 0 auto; padding: 24px; background:#ffffff; border-radius: 12px; border: 1px solid #D8DFDE;">
        <h2 style="color: {COLOR_PRIMARY}; margin: 0 0 16px 0;">{COMPANY_NAME}</h2>
        <p>Bonjour {display_name},</p>
        <p>Votre mot de passe a bien été réinitialisé.</p>
        <p>Si vous n'êtes pas à l'origine de cette modification, contactez immédiatement votre administrateur.</p>
    </div>
</body>
</html>
"""

    def _render_otp_template(self, otp: str, user_name: Optional[str]) -> str:
        """
        Génère le contenu HTML de l'email à partir du template

        Args:
            otp: Code OTP à 6 chiffres
            user_name: Nom de l'utilisateur (optionnel)

        Returns:
            str: Contenu HTML de l'email
        """
        # Chemin vers le template
        template_path = Path(__file__).parent.parent / "templates" / "otp_email.html"

        try:
            # Lire le template
            with open(template_path, "r", encoding="utf-8") as f:
                template_content = f.read()

            # Remplacer les variables
            # Si user_name n'est pas fourni, utiliser une salutation générique
            display_name = user_name if user_name else "Utilisateur"

            html_content = apply_branding(template_content)
            html_content = html_content.replace("{{ user_name }}", display_name)
            html_content = html_content.replace("{{ otp_code }}", otp)

            return html_content

        except FileNotFoundError:
            logger.error(f"Template d'email introuvable: {template_path}")
            # Fallback vers un template simple
            return self._render_fallback_html(otp, user_name)
        except Exception as e:
            logger.error(f"Erreur lors du rendu du template: {e}")
            return self._render_fallback_html(otp, user_name)

    def _render_plain_text(self, otp: str, user_name: Optional[str]) -> str:
        """
        Génèrela version texte brut de l'email

        Args:
            otp: Code OTP à 6 chiffres
            user_name: Nom de l'utilisateur (optionnel)

        Returns:
            str: Contenu texte brut de l'email
        """
        display_name = user_name if user_name else "Utilisateur"

        lines = [
            COMPANY_NAME,
            "=" * 50,
            "",
            f"Bonjour {display_name},",
            "",
            "Vous avez demandé la réinitialisation de votre mot de passe.",
            "Utilisez le code de vérification ci-dessous pour continuer :",
            "",
            f"    CODE DE VÉRIFICATION : {otp}",
            "",
            "⏱️  IMPORTANT : Ce code est valide pendant 15 minutes seulement.",
            "",
            "Entrez ce code dans l'application pour vérifier votre identité",
            "et procéder à la réinitialisation de votre mot de passe.",
            "",
            "🔒 AVERTISSEMENT DE SÉCURITÉ",
            "Si vous n'avez pas demandé cette réinitialisation, veuillez",
            "ignorer cet email et contacter immédiatement votre administrateur",
            "système. Ne partagez jamais ce code avec qui que ce soit.",
            "",
            "=" * 50,
            f"Cet email a été envoyé automatiquement par {COMPANY_NAME}.",
            "Merci de ne pas répondre à cet email.",
            "",
            f"© 2024 {COMPANY_NAME}. Tous droits réservés.",
        ]

        return "\n".join(lines)

    def _render_fallback_html(self, otp: str, user_name: Optional[str]) -> str:
        """
        Génère un template HTML simple en cas d'erreur de chargement du template

        Args:
            otp: Code OTP à 6 chiffres
            user_name: Nom de l'utilisateur (optionnel)

        Returns:
            str: Contenu HTML simple
        """
        display_name = user_name if user_name else "Utilisateur"

        return f"""
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Code de vérification - {COMPANY_NAME}</title>
</head>
<body style="font-family: Arial, sans-serif; line-height: 1.6; color: #102624; background-color: #F5F7F7;">
    <div style="max-width: 600px; margin: 0 auto; padding: 24px; background:#ffffff; border-radius: 12px; border: 1px solid #D8DFDE;">
        <h2 style="color: {COLOR_PRIMARY}; margin: 0 0 16px 0;">{COMPANY_NAME}</h2>
        <p>Bonjour {display_name},</p>
        <p>Vous avez demandé la réinitialisation de votre mot de passe.</p>
        <p>Votre code de vérification est :</p>
        <div style="background-color: #E8F2F0; padding: 20px; text-align: center; margin: 20px 0; border: 1px solid #D8DFDE; border-radius: 10px;">
            <h1 style="color: {COLOR_PRIMARY}; font-size: 36px; letter-spacing: 10px; margin: 0;">{otp}</h1>
        </div>
        <p><strong>Important :</strong> Ce code est valide pendant 15 minutes seulement.</p>
        <div style="background-color: #FEE2E2; padding: 14px 16px; border-left: 4px solid #B91C1C; border-radius: 6px; margin: 20px 0;">
            <p style="margin: 0; color: #7F1D1D;"><strong>Avertissement de sécurité</strong></p>
            <p style="margin: 8px 0 0 0; color: #7F1D1D; font-size: 13px;">Si vous n'avez pas demandé cette réinitialisation, ignorez cet email et contactez immédiatement votre administrateur système.</p>
        </div>
        <hr style="border: none; border-top: 1px solid #D8DFDE; margin: 30px 0;">
        <p style="font-size: 12px; color: #5A6968; text-align: center;">
            © 2024 {COMPANY_NAME}. Tous droits réservés.
        </p>
    </div>
</body>
</html>
"""

