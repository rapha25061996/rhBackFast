"""Payslip PDF generation service"""
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Optional
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
)
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.branding import (
    COLOR_ACCENT,
    COLOR_BORDER,
    COLOR_ON_PRIMARY,
    COLOR_PRIMARY,
    COLOR_PRIMARY_600,
    COLOR_PRIMARY_DARK,
    COLOR_PRIMARY_SURFACE,
    COLOR_SUCCESS,
    COLOR_TEXT_BODY,
    COLOR_TEXT_MUTED,
    COMPANY_NAME,
)
from app.paie_app.models import EntreePaie, PeriodePaie
from app.user_app.models import Employe


# Centralised ReportLab colour aliases so every section of the payslip
# pulls from the same branding tokens. Changing the palette in
# :mod:`app.core.branding` flows to the PDF with no code change here.
_PDF_PRIMARY = colors.HexColor(COLOR_PRIMARY)
_PDF_PRIMARY_DARK = colors.HexColor(COLOR_PRIMARY_DARK)
_PDF_PRIMARY_600 = colors.HexColor(COLOR_PRIMARY_600)
_PDF_PRIMARY_SURFACE = colors.HexColor(COLOR_PRIMARY_SURFACE)
_PDF_ACCENT = colors.HexColor(COLOR_ACCENT)
_PDF_SUCCESS = colors.HexColor(COLOR_SUCCESS)
_PDF_TEXT_BODY = colors.HexColor(COLOR_TEXT_BODY)
_PDF_TEXT_MUTED = colors.HexColor(COLOR_TEXT_MUTED)
_PDF_BORDER = colors.HexColor(COLOR_BORDER)
_PDF_ON_PRIMARY = colors.HexColor(COLOR_ON_PRIMARY)


class PayslipGeneratorService:
    """Service for generating PDF payslips"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()

    def _setup_custom_styles(self):
        """Setup custom paragraph styles"""
        self.styles.add(ParagraphStyle(
            name='CompanyTitle',
            parent=self.styles['Heading1'],
            fontSize=18,
            textColor=_PDF_PRIMARY,
            spaceAfter=6,
            alignment=TA_CENTER,
            fontName='Helvetica-Bold'
        ))

        self.styles.add(ParagraphStyle(
            name='SectionTitle',
            parent=self.styles['Heading2'],
            fontSize=12,
            textColor=_PDF_PRIMARY,
            spaceAfter=12,
            spaceBefore=12,
            fontName='Helvetica-Bold'
        ))

        self.styles.add(ParagraphStyle(
            name='RightAlign',
            parent=self.styles['Normal'],
            alignment=TA_RIGHT
        ))

    async def generate_payslip(
        self,
        entree_id: int,
        output_path: Optional[str] = None
    ) -> str:
        """
        Generate a PDF payslip for a payroll entry

        Args:
            entree_id: ID of the payroll entry
            output_path: Optional custom output path

        Returns:
            Path to the generated PDF file

        Raises:
            ValueError: If entry not found or data is invalid
        """
        # Fetch the payroll entry with related data
        result = await self.db.execute(
            select(EntreePaie).where(EntreePaie.id == entree_id)
        )
        entree = result.scalar_one_or_none()

        if not entree:
            raise ValueError(f"Payroll entry {entree_id} not found")

        # Fetch employee data
        result = await self.db.execute(
            select(Employe).where(Employe.id == entree.employe_id)
        )
        employe = result.scalar_one_or_none()

        if not employe:
            raise ValueError(f"Employee {entree.employe_id} not found")

        # Fetch period data
        result = await self.db.execute(
            select(PeriodePaie).where(PeriodePaie.id == entree.periode_paie_id)
        )
        periode = result.scalar_one_or_none()

        if not periode:
            raise ValueError(f"Period {entree.periode_paie_id} not found")

        # Generate output path if not provided
        if not output_path:
            media_dir = Path("media/payslips")
            media_dir.mkdir(parents=True, exist_ok=True)
            filename = f"payslip_{employe.id}_{periode.annee}_{periode.mois:02d}.pdf"
            output_path = str(media_dir / filename)

        # Create PDF
        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=2*cm,
            leftMargin=2*cm,
            topMargin=2*cm,
            bottomMargin=2*cm
        )

        # Build document content
        story = []
        story.extend(self._build_header(employe, periode))
        story.append(Spacer(1, 0.5*cm))
        story.extend(self._build_employee_info(employe))
        story.append(Spacer(1, 0.5*cm))
        story.extend(self._build_salary_details(entree))
        story.append(Spacer(1, 0.5*cm))
        story.extend(self._build_deductions(entree))
        story.append(Spacer(1, 0.5*cm))
        story.extend(self._build_summary(entree))
        story.append(Spacer(1, 1*cm))
        story.extend(self._build_footer())

        # Build PDF
        doc.build(story)

        # Save to file
        with open(output_path, 'wb') as f:
            f.write(buffer.getvalue())

        # Update entry record
        entree.payslip_generated = True
        entree.payslip_file = output_path
        entree.payslip_generated_at = datetime.utcnow()
        await self.db.commit()

        return output_path

    def _build_header(self, employe: Employe, periode: PeriodePaie) -> list:
        """Build the header section"""
        elements = []

        # Company name pulled from :mod:`app.core.branding` (which in turn
        # reads ``settings.APP_NAME``).
        company_name = Paragraph(
            COMPANY_NAME.upper(),
            self.styles['CompanyTitle']
        )
        elements.append(company_name)

        # Payslip title
        month_names = [
            "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
            "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"
        ]
        month_name = month_names[periode.mois - 1]
        title = Paragraph(
            f"<b>BULLETIN DE PAIE</b><br/>{month_name} {periode.annee}",
            self.styles['CompanyTitle']
        )
        elements.append(title)

        return elements

    def _build_employee_info(self, employe: Employe) -> list:
        """Build employee information section"""
        elements = []

        title = Paragraph("INFORMATIONS EMPLOYÉ", self.styles['SectionTitle'])
        elements.append(title)

        data = [
            ['Nom complet:', employe.full_name],
            ['Matricule:', employe.matricule or 'N/A'],
            ['Numéro INSS:', employe.numero_inss],
            ['Banque:', employe.banque],
            ['Compte:', employe.numero_compte],
        ]

        table = Table(data, colWidths=[5*cm, 11*cm])
        table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('TEXTCOLOR', (0, 0), (0, -1), _PDF_TEXT_BODY),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))

        elements.append(table)
        return elements

    def _build_salary_details(self, entree: EntreePaie) -> list:
        """Build salary details section"""
        elements = []

        title = Paragraph("DÉTAILS DU SALAIRE", self.styles['SectionTitle'])
        elements.append(title)

        data = [
            ['Description', 'Montant (USD)'],
            ['Salaire de base', self._format_amount(entree.salaire_base)],
        ]

        # Add allowances if they exist
        if entree.indemnite_logement > 0:
            data.append([
                'Indemnité de logement',
                self._format_amount(entree.indemnite_logement)
            ])

        if entree.indemnite_deplacement > 0:
            data.append([
                'Indemnité de déplacement',
                self._format_amount(entree.indemnite_deplacement)
            ])

        if entree.indemnite_fonction > 0:
            data.append([
                'Indemnité de fonction',
                self._format_amount(entree.indemnite_fonction)
            ])

        if entree.allocation_familiale > 0:
            data.append([
                'Allocation familiale',
                self._format_amount(entree.allocation_familiale)
            ])

        if entree.autres_avantages > 0:
            data.append([
                'Autres avantages',
                self._format_amount(entree.autres_avantages)
            ])

        # Gross salary
        data.append(['', ''])
        data.append([
            'SALAIRE BRUT',
            self._format_amount(entree.salaire_brut)
        ])

        table = Table(data, colWidths=[11*cm, 5*cm])
        table.setStyle(TableStyle([
            # Header row
            ('BACKGROUND', (0, 0), (-1, 0), _PDF_PRIMARY),
            ('TEXTCOLOR', (0, 0), (-1, 0), _PDF_ON_PRIMARY),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            # Data rows
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('TEXTCOLOR', (0, 1), (-1, -1), _PDF_TEXT_BODY),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            # Gross salary row (bold)
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, -1), (-1, -1), 10),
            ('LINEABOVE', (0, -1), (-1, -1), 1, _PDF_PRIMARY),
            # Grid
            ('GRID', (0, 0), (-1, -1), 0.5, _PDF_BORDER),
        ]))

        elements.append(table)
        return elements

    def _build_deductions(self, entree: EntreePaie) -> list:
        """Build deductions section"""
        elements = []

        title = Paragraph("RETENUES ET COTISATIONS", self.styles['SectionTitle'])
        elements.append(title)

        data = [
            ['Description', 'Montant (USD)'],
        ]

        # Employee contributions
        cotisations_salariales = entree.cotisations_salariales or {}
        if cotisations_salariales:
            if 'inss' in cotisations_salariales:
                data.append([
                    'INSS Employé',
                    self._format_amount(cotisations_salariales['inss'])
                ])
            if 'assurance' in cotisations_salariales:
                data.append([
                    'Assurance Employé',
                    self._format_amount(cotisations_salariales['assurance'])
                ])
            if 'fpc' in cotisations_salariales:
                data.append([
                    'FPC Employé',
                    self._format_amount(cotisations_salariales['fpc'])
                ])

        # IRE (Income tax)
        if 'ire' in cotisations_salariales:
            data.append([
                'IRE (Impôt sur le Revenu)',
                self._format_amount(cotisations_salariales['ire'])
            ])

        # Other deductions
        retenues_diverses = entree.retenues_diverses or {}
        if retenues_diverses:
            for key, value in retenues_diverses.items():
                if isinstance(value, (int, float, Decimal)) and value > 0:
                    data.append([
                        f'Retenue: {key}',
                        self._format_amount(value)
                    ])

        # Total deductions
        total_deductions = entree.total_charge_salariale
        data.append(['', ''])
        data.append([
            'TOTAL RETENUES',
            self._format_amount(total_deductions)
        ])

        table = Table(data, colWidths=[11*cm, 5*cm])
        table.setStyle(TableStyle([
            # Header row
            ('BACKGROUND', (0, 0), (-1, 0), _PDF_PRIMARY_600),
            ('TEXTCOLOR', (0, 0), (-1, 0), _PDF_ON_PRIMARY),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            # Data rows
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('TEXTCOLOR', (0, 1), (-1, -1), _PDF_TEXT_BODY),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            # Total row (bold)
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, -1), (-1, -1), 10),
            ('LINEABOVE', (0, -1), (-1, -1), 1, _PDF_PRIMARY),
            # Grid
            ('GRID', (0, 0), (-1, -1), 0.5, _PDF_BORDER),
        ]))

        elements.append(table)
        return elements

    def _build_summary(self, entree: EntreePaie) -> list:
        """Build summary section"""
        elements = []

        title = Paragraph("RÉCAPITULATIF", self.styles['SectionTitle'])
        elements.append(title)

        data = [
            ['Salaire Brut', self._format_amount(entree.salaire_brut)],
            ['Total Retenues', self._format_amount(entree.total_charge_salariale)],
            ['', ''],
            ['SALAIRE NET À PAYER', self._format_amount(entree.salaire_net)],
        ]

        table = Table(data, colWidths=[11*cm, 5*cm])
        table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (0, -2), 'Helvetica-Bold'),
            ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -2), 10),
            ('TEXTCOLOR', (0, 0), (-1, -2), _PDF_TEXT_BODY),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            # Net salary row — highlighted in the brand colour.
            ('BACKGROUND', (0, -1), (-1, -1), _PDF_PRIMARY),
            ('TEXTCOLOR', (0, -1), (-1, -1), _PDF_ON_PRIMARY),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, -1), (-1, -1), 12),
            ('LINEABOVE', (0, -1), (-1, -1), 2, _PDF_ACCENT),
        ]))

        elements.append(table)
        return elements

    def _build_footer(self) -> list:
        """Build footer section"""
        elements = []

        footer_text = Paragraph(
            f"<i>Document généré le {datetime.now().strftime('%d/%m/%Y à %H:%M')}</i>",
            self.styles['Normal']
        )
        elements.append(footer_text)

        disclaimer = Paragraph(
            "<i>Ce bulletin de paie est confidentiel et destiné uniquement "
            "à l'employé mentionné ci-dessus.</i>",
            self.styles['Normal']
        )
        elements.append(disclaimer)

        return elements

    def _format_amount(self, amount) -> str:
        """Format monetary amount"""
        if amount is None:
            return "0.00"
        if isinstance(amount, (int, float)):
            amount = Decimal(str(amount))
        return f"{amount:,.2f}".replace(",", " ")

    async def generate_bulk_payslips(
        self,
        periode_id: int,
        output_dir: Optional[str] = None
    ) -> list[str]:
        """
        Generate payslips for all entries in a period

        Args:
            periode_id: ID of the payroll period
            output_dir: Optional custom output directory

        Returns:
            List of paths to generated PDF files

        Raises:
            ValueError: If period not found
        """
        # Fetch all entries for the period
        result = await self.db.execute(
            select(EntreePaie).where(EntreePaie.periode_paie_id == periode_id)
        )
        entries = result.scalars().all()

        if not entries:
            raise ValueError(f"No entries found for period {periode_id}")

        # Generate payslips for each entry
        generated_files = []
        for entree in entries:
            try:
                file_path = await self.generate_payslip(
                    entree.id,
                    output_path=None  # Let it auto-generate path
                )
                generated_files.append(file_path)
            except Exception as e:
                # Log error but continue with other entries
                print(f"Error generating payslip for entry {entree.id}: {e}")
                continue

        return generated_files
