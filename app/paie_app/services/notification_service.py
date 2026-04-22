"""Notification service for payroll system"""
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.paie_app.constants import SEVERITY_COLORS
from app.paie_app.models import Alert, PeriodePaie, EntreePaie, RetenueEmploye
from app.user_app.models import User, Employe
from app.core.config import settings


logger = logging.getLogger(__name__)


class NotificationService:
    """Service for sending notifications via email"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def send_email(
        self,
        to_email: str,
        subject: str,
        body: str,
        html_body: Optional[str] = None
    ) -> bool:
        """Send an email notification"""
        try:
            if not hasattr(settings, 'SMTP_HOST') or not settings.SMTP_HOST:
                logger.warning('Email not configured. Skipping email notification.')
                return False

            msg = MIMEMultipart('alternative')
            msg['From'] = settings.SMTP_FROM_EMAIL
            msg['To'] = to_email
            msg['Subject'] = subject
            msg.attach(MIMEText(body, 'plain'))
            if html_body:
                msg.attach(MIMEText(html_body, 'html'))

            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
                if settings.SMTP_TLS:
                    server.starttls()
                if settings.SMTP_USER and settings.SMTP_PASSWORD:
                    server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                server.send_message(msg)

            logger.info(f'Email sent successfully to {to_email}')
            return True
        except Exception as e:
            logger.error(f'Failed to send email to {to_email}: {str(e)}')
            return False

    async def send_alert_notification(self, alert_id: int) -> bool:
        """Send email notification for an alert"""
        try:
            result = await self.db.execute(select(Alert).where(Alert.id == alert_id))
            alert = result.scalar_one_or_none()
            if not alert:
                logger.error(f'Alert {alert_id} not found')
                return False
            if alert.email_sent:
                logger.info(f'Alert {alert_id} email already sent')
                return True

            recipients = await self._get_alert_recipients(alert)
            if not recipients:
                logger.warning(f'No recipients found for alert {alert_id}')
                return False

            subject = f'[{alert.severity}] {alert.title}'
            body = self._format_alert_email(alert)
            html_body = self._format_alert_email_html(alert)

            success = True
            for recipient in recipients:
                sent = await self.send_email(recipient, subject, body, html_body)
                if not sent:
                    success = False

            if success:
                alert.email_sent = True
                alert.email_sent_at = datetime.utcnow()
                await self.db.commit()

            return success
        except Exception as e:
            logger.error(f'Failed to send alert notification {alert_id}: {str(e)}')
            return False

    async def _get_alert_recipients(self, alert: Alert) -> List[str]:
        """Get email recipients for an alert"""
        recipients: List[str] = []
        result = await self.db.execute(select(User).where(User.is_active.is_(True)))
        users = result.scalars().all()
        for user in users:
            if await self._user_has_payroll_permission(user):
                recipients.append(user.email)

        return list(set(recipients))

    async def _user_has_payroll_permission(self, user: User) -> bool:
        """Check if user has payroll management permissions"""
        return user.is_superuser or user.is_staff

    def _format_alert_email(self, alert: Alert) -> str:
        """Format alert as plain text email"""
        lines = [
            f'Alert: {alert.title}',
            f'Severity: {alert.severity}',
            f'Type: {alert.alert_type}',
            f'Status: {alert.status}',
            '',
            'Message:',
            alert.message,
            ''
        ]
        if alert.details:
            lines.append('Details:')
            for key, value in alert.details.items():
                lines.append(f'  {key}: {value}')
            lines.append('')
        lines.append(f'Created: {alert.created_at}')
        lines.append('')
        lines.append('---')
        lines.append('RH Management System')
        return '\n'.join(lines)

    def _format_alert_email_html(self, alert: Alert) -> str:
        """Format alert as HTML email"""
        color = SEVERITY_COLORS.get(alert.severity, '#6c757d')

        html_parts = [
            '<html><body style="font-family: Arial, sans-serif;">',
            f'<div style="border-left: 4px solid {color}; padding: 15px; background-color: #f8f9fa; margin: 20px 0;">',
            f'<div style="font-size: 18px; font-weight: bold; color: {color}; margin-bottom: 10px;">{alert.title}</div>',
            '<div style="font-size: 12px; color: #6c757d; margin-bottom: 15px;">',
            f'<strong>Severity:</strong> {alert.severity} | ',
            f'<strong>Type:</strong> {alert.alert_type} | ',
            f'<strong>Status:</strong> {alert.status}</div>',
            f'<div style="font-size: 14px; line-height: 1.6; margin-bottom: 15px;">{alert.message}</div>'
        ]

        if alert.details:
            html_parts.append('<div style="background-color: #ffffff; padding: 10px; border-radius: 4px; font-size: 13px;">')
            html_parts.append('<strong>Details:</strong><br>')
            for key, value in alert.details.items():
                html_parts.append(f'<div>{key}: {value}</div>')
            html_parts.append('</div>')

        html_parts.extend([
            '</div>',
            '<div style="margin-top: 30px; padding-top: 20px; border-top: 1px solid #dee2e6; font-size: 12px; color: #6c757d;">',
            f'<p>Created: {alert.created_at}</p>',
            '<p>RH Management System - Payroll Notifications</p>',
            '</div></body></html>'
        ])

        return ''.join(html_parts)

    async def notify_period_processed(self, periode_id: int) -> bool:
        """Send notification when a payroll period is processed"""
        try:
            result = await self.db.execute(select(PeriodePaie).where(PeriodePaie.id == periode_id))
            periode = result.scalar_one_or_none()
            if not periode:
                return False

            recipients = await self._get_hr_managers()
            if not recipients:
                return False

            subject = f'Payroll Period Processed: {periode.mois}/{periode.annee}'
            body_lines = [
                'Payroll period has been processed successfully.',
                '',
                f'Period: {periode.mois}/{periode.annee}',
                f'Status: {periode.statut}',
                f'Employees: {periode.nombre_employes}',
                f'Total Net Payable: {periode.total_net_a_payer} FC',
                '',
                'The period is now ready for review and approval.',
                '',
                '---',
                'RH Management System'
            ]
            body = '\n'.join(body_lines)

            html_body = (
                '<html><body style="font-family: Arial, sans-serif;">'
                '<h2>Payroll Period Processed</h2>'
                '<p>The payroll period has been processed successfully.</p>'
                '<table style="border-collapse: collapse; margin: 20px 0;">'
                '<tr><td style="padding: 8px; font-weight: bold;">Period:</td>'
                f'<td style="padding: 8px;">{periode.mois}/{periode.annee}</td></tr>'
                '<tr><td style="padding: 8px; font-weight: bold;">Status:</td>'
                f'<td style="padding: 8px;">{periode.statut}</td></tr>'
                '<tr><td style="padding: 8px; font-weight: bold;">Employees:</td>'
                f'<td style="padding: 8px;">{periode.nombre_employes}</td></tr>'
                '<tr><td style="padding: 8px; font-weight: bold;">Total Net Payable:</td>'
                f'<td style="padding: 8px;">{periode.total_net_a_payer} FC</td></tr>'
                '</table>'
                '<p>The period is now ready for review and approval.</p>'
                '<hr><p style="font-size: 12px; color: #6c757d;">RH Management System</p>'
                '</body></html>'
            )

            success = True
            for recipient in recipients:
                sent = await self.send_email(recipient, subject, body, html_body)
                if not sent:
                    success = False
            return success
        except Exception as e:
            logger.error(f'Failed to send period processed notification: {str(e)}')
            return False

    async def notify_period_approved(self, periode_id: int) -> bool:
        """Send notification when a payroll period is approved"""
        try:
            result = await self.db.execute(select(PeriodePaie).where(PeriodePaie.id == periode_id))
            periode = result.scalar_one_or_none()
            if not periode:
                return False

            recipients = await self._get_hr_managers()
            if not recipients:
                return False

            subject = f'Payroll Period Approved: {periode.mois}/{periode.annee}'
            body_lines = [
                'Payroll period has been approved and is ready for payment.',
                '',
                f'Period: {periode.mois}/{periode.annee}',
                f'Status: {periode.statut}',
                f'Employees: {periode.nombre_employes}',
                f'Total Net Payable: {periode.total_net_a_payer} FC',
                f'Approved: {periode.date_approbation}',
                '',
                'Please proceed with payment processing.',
                '',
                '---',
                'RH Management System'
            ]
            body = '\n'.join(body_lines)

            html_body = (
                '<html><body style="font-family: Arial, sans-serif;">'
                '<h2 style="color: #28a745;">Payroll Period Approved</h2>'
                '<p>The payroll period has been approved and is ready for payment.</p>'
                '<table style="border-collapse: collapse; margin: 20px 0;">'
                '<tr><td style="padding: 8px; font-weight: bold;">Period:</td>'
                f'<td style="padding: 8px;">{periode.mois}/{periode.annee}</td></tr>'
                '<tr><td style="padding: 8px; font-weight: bold;">Status:</td>'
                f'<td style="padding: 8px;">{periode.statut}</td></tr>'
                '<tr><td style="padding: 8px; font-weight: bold;">Employees:</td>'
                f'<td style="padding: 8px;">{periode.nombre_employes}</td></tr>'
                '<tr><td style="padding: 8px; font-weight: bold;">Total Net Payable:</td>'
                f'<td style="padding: 8px;">{periode.total_net_a_payer} FC</td></tr>'
                '<tr><td style="padding: 8px; font-weight: bold;">Approved:</td>'
                f'<td style="padding: 8px;">{periode.date_approbation}</td></tr>'
                '</table>'
                '<p>Please proceed with payment processing.</p>'
                '<hr><p style="font-size: 12px; color: #6c757d;">RH Management System</p>'
                '</body></html>'
            )

            success = True
            for recipient in recipients:
                sent = await self.send_email(recipient, subject, body, html_body)
                if not sent:
                    success = False
            return success
        except Exception as e:
            logger.error(f'Failed to send period approved notification: {str(e)}')
            return False

    async def notify_payslip_generated(self, entree_id: int) -> bool:
        """Send notification to employee when payslip is generated"""
        try:
            result = await self.db.execute(select(EntreePaie).where(EntreePaie.id == entree_id))
            entree = result.scalar_one_or_none()
            if not entree:
                return False

            result = await self.db.execute(select(Employe).where(Employe.id == entree.employe_id))
            employe = result.scalar_one_or_none()
            if not employe:
                return False

            email = employe.email_professionnel or employe.email_personnel
            if not email:
                logger.warning(f'No email found for employee {employe.id}')
                return False

            result = await self.db.execute(select(PeriodePaie).where(PeriodePaie.id == entree.periode_paie_id))
            periode = result.scalar_one_or_none()
            if not periode:
                logger.warning(f'Period {entree.periode_paie_id} not found for payslip notification')
                return False

            subject = f'Your Payslip - {periode.mois}/{periode.annee}'
            body_lines = [
                f'Dear {employe.prenom} {employe.nom},',
                '',
                f'Your payslip for {periode.mois}/{periode.annee} is now available.',
                '',
                'Salary Details:',
                f'- Gross Salary: {entree.salaire_brut} FC',
                f'- Net Salary: {entree.salaire_net} FC',
                '',
                'Please log in to the system to download your payslip.',
                '',
                '---',
                'RH Management System'
            ]
            body = '\n'.join(body_lines)

            html_body = (
                '<html><body style="font-family: Arial, sans-serif;">'
                '<h2>Your Payslip is Ready</h2>'
                f'<p>Dear {employe.prenom} {employe.nom},</p>'
                f'<p>Your payslip for {periode.mois}/{periode.annee} is now available.</p>'
                '<table style="border-collapse: collapse; margin: 20px 0;">'
                '<tr><td style="padding: 8px; font-weight: bold;">Gross Salary:</td>'
                f'<td style="padding: 8px;">{entree.salaire_brut} FC</td></tr>'
                '<tr><td style="padding: 8px; font-weight: bold;">Net Salary:</td>'
                f'<td style="padding: 8px;">{entree.salaire_net} FC</td></tr>'
                '</table>'
                '<p>Please log in to the system to download your payslip.</p>'
                '<hr><p style="font-size: 12px; color: #6c757d;">RH Management System</p>'
                '</body></html>'
            )

            return await self.send_email(email, subject, body, html_body)
        except Exception as e:
            logger.error(f'Failed to send payslip notification: {str(e)}')
            return False

    async def _get_hr_managers(self) -> List[str]:
        """Get email addresses of HR managers"""
        result = await self.db.execute(select(User).where(User.is_active.is_(True)))
        users = result.scalars().all()
        emails = []
        for user in users:
            if user.is_superuser or user.is_staff:
                emails.append(user.email)
        return emails

    async def notify_deduction_created(self, retenue_id: int) -> bool:
        """Send notification when a deduction is created"""
        try:
            result = await self.db.execute(select(RetenueEmploye).where(RetenueEmploye.id == retenue_id))
            retenue = result.scalar_one_or_none()
            if not retenue:
                return False

            result = await self.db.execute(select(Employe).where(Employe.id == retenue.employe_id))
            employe = result.scalar_one_or_none()
            if not employe:
                return False

            email = employe.email_professionnel or employe.email_personnel
            if not email:
                return False

            subject = 'New Salary Deduction'
            body_lines = [
                f'Dear {employe.prenom} {employe.nom},',
                '',
                'A new salary deduction has been added to your account.',
                '',
                'Deduction Details:',
                f'- Type: {retenue.type_retenue}',
                f'- Description: {retenue.description}',
                f'- Monthly Amount: {retenue.montant_mensuel} FC',
                f'- Total Amount: {retenue.montant_total} FC',
                f'- Start Date: {retenue.date_debut}',
                f'- End Date: {retenue.date_fin or "Ongoing"}',
                '',
                'If you have any questions, please contact HR.',
                '',
                '---',
                'RH Management System'
            ]
            body = '\n'.join(body_lines)

            html_body = (
                '<html><body style="font-family: Arial, sans-serif;">'
                '<h2>New Salary Deduction</h2>'
                f'<p>Dear {employe.prenom} {employe.nom},</p>'
                '<p>A new salary deduction has been added to your account.</p>'
                '<table style="border-collapse: collapse; margin: 20px 0;">'
                '<tr><td style="padding: 8px; font-weight: bold;">Type:</td>'
                f'<td style="padding: 8px;">{retenue.type_retenue}</td></tr>'
                '<tr><td style="padding: 8px; font-weight: bold;">Description:</td>'
                f'<td style="padding: 8px;">{retenue.description}</td></tr>'
                '<tr><td style="padding: 8px; font-weight: bold;">Monthly Amount:</td>'
                f'<td style="padding: 8px;">{retenue.montant_mensuel} FC</td></tr>'
                '<tr><td style="padding: 8px; font-weight: bold;">Total Amount:</td>'
                f'<td style="padding: 8px;">{retenue.montant_total} FC</td></tr>'
                '<tr><td style="padding: 8px; font-weight: bold;">Start Date:</td>'
                f'<td style="padding: 8px;">{retenue.date_debut}</td></tr>'
                '<tr><td style="padding: 8px; font-weight: bold;">End Date:</td>'
                f'<td style="padding: 8px;">{retenue.date_fin or "Ongoing"}</td></tr>'
                '</table>'
                '<p>If you have any questions, please contact HR.</p>'
                '<hr><p style="font-size: 12px; color: #6c757d;">RH Management System</p>'
                '</body></html>'
            )

            return await self.send_email(email, subject, body, html_body)
        except Exception as e:
            logger.error(f'Failed to send deduction notification: {str(e)}')
            return False
