"""Export service for payroll data"""
import csv
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
import xlsxwriter

from app.paie_app.models import PeriodePaie, RetenueEmploye
from app.user_app.models import Employe


class ExportService:
    """Service for exporting payroll data to various formats"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def export_periode_to_excel(
        self,
        periode_id: int,
        output_path: Optional[str] = None
    ) -> str:
        """
        Export a payroll period to Excel format

        Args:
            periode_id: ID of the payroll period
            output_path: Optional custom output path

        Returns:
            Path to the generated Excel file
        """
        # Fetch period with entries
        result = await self.db.execute(
            select(PeriodePaie)
            .where(PeriodePaie.id == periode_id)
            .options(selectinload(PeriodePaie.entries))
        )
        periode = result.scalar_one_or_none()

        if not periode:
            raise ValueError(f"Period {periode_id} not found")

        # Generate filename
        if not output_path:
            export_dir = Path("media/exports/payroll")
            export_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"paie_{periode.annee}_{periode.mois:02d}_{timestamp}.xlsx"
            output_path = str(export_dir / filename)

        # Create workbook
        workbook = xlsxwriter.Workbook(output_path)

        # Add formats
        header_format = workbook.add_format({
            'bold': True,
            'bg_color': '#4472C4',
            'font_color': 'white',
            'border': 1
        })
        currency_format = workbook.add_format({'num_format': '#,##0.00'})
        date_format = workbook.add_format({'num_format': 'dd/mm/yyyy'})

        # Create summary sheet
        await self._create_summary_sheet(workbook, periode, header_format, currency_format)

        # Create detailed entries sheet
        await self._create_entries_sheet(
            workbook, periode, header_format, currency_format
        )

        # Create deductions sheet
        await self._create_deductions_sheet(
            workbook, periode, header_format, currency_format, date_format
        )

        workbook.close()
        return output_path

    async def _create_summary_sheet(
        self,
        workbook: xlsxwriter.Workbook,
        periode: PeriodePaie,
        header_format: Any,
        currency_format: Any
    ):
        """Create summary worksheet"""
        worksheet = workbook.add_worksheet("Résumé")
        worksheet.set_column(0, 0, 30)
        worksheet.set_column(1, 1, 20)

        # Period information
        worksheet.write(0, 0, 'Période de Paie', header_format)
        worksheet.write(0, 1, f"{periode.mois:02d}/{periode.annee}", header_format)

        row = 2
        summary_data = [
            ('Statut', periode.statut),
            ('Date début', periode.date_debut.strftime('%d/%m/%Y')),
            ('Date fin', periode.date_fin.strftime('%d/%m/%Y')),
            ('Nombre d\'employés', str(periode.nombre_employes)),
            ('', ''),
            ('Masse salariale brute', float(periode.masse_salariale_brute)),
            ('Total cotisations patronales', float(periode.total_cotisations_patronales)),
            ('Total cotisations salariales', float(periode.total_cotisations_salariales)),
            ('Total net à payer', float(periode.total_net_a_payer)),
        ]

        for label, value in summary_data:
            worksheet.write(row, 0, label)
            if isinstance(value, float):
                worksheet.write(row, 1, value, currency_format)
            else:
                worksheet.write(row, 1, value)
            row += 1

    async def _create_entries_sheet(
        self,
        workbook: xlsxwriter.Workbook,
        periode: PeriodePaie,
        header_format: Any,
        currency_format: Any
    ):
        """Create detailed entries worksheet"""
        worksheet = workbook.add_worksheet("Détails Paie")

        # Headers
        headers = [
            'ID', 'Employé', 'Matricule', 'Salaire Base', 'Ind. Logement',
            'Ind. Déplacement', 'Ind. Fonction', 'Allocation Familiale',
            'Autres Avantages', 'Salaire Brut', 'Cotisations Salariales',
            'Base Imposable', 'IRE', 'Retenues Diverses', 'Salaire Net'
        ]

        for col, header in enumerate(headers):
            worksheet.write(0, col, header, header_format)

        # Fetch employee data for entries
        row = 1
        for entry in periode.entries:
            # Get employee info
            result = await self.db.execute(
                select(Employe).where(Employe.id == entry.employe_id)
            )
            employe = result.scalar_one_or_none()

            if not employe:
                continue

            # Extract cotisations and retenues
            cotisations_salariales = entry.cotisations_salariales or {}
            retenues_diverses = entry.retenues_diverses or {}

            total_cotisations = sum(
                float(v) for v in cotisations_salariales.values() if isinstance(v, (int, float, Decimal))
            )
            total_retenues = sum(
                float(v) for v in retenues_diverses.values() if isinstance(v, (int, float, Decimal))
            )

            # Calculate IRE from retenues
            ire = float(retenues_diverses.get('ire', 0))

            data = [
                entry.id,
                f"{employe.nom} {employe.prenom}",
                employe.matricule or '',
                float(entry.salaire_base),
                float(entry.indemnite_logement),
                float(entry.indemnite_deplacement),
                float(entry.indemnite_fonction),
                float(entry.allocation_familiale),
                float(entry.autres_avantages),
                float(entry.salaire_brut),
                total_cotisations,
                float(entry.base_imposable),
                ire,
                total_retenues - ire,  # Other deductions
                float(entry.salaire_net)
            ]

            for col, value in enumerate(data):
                if isinstance(value, float) and col >= 3:  # Currency columns
                    worksheet.write(row, col, value, currency_format)
                else:
                    worksheet.write(row, col, value)
            row += 1

        # Auto-fit columns
        worksheet.set_column(0, 0, 8)
        worksheet.set_column(1, 1, 25)
        worksheet.set_column(2, 2, 15)
        worksheet.set_column(3, 14, 15)

    async def _create_deductions_sheet(
        self,
        workbook: xlsxwriter.Workbook,
        periode: PeriodePaie,
        header_format: Any,
        currency_format: Any,
        date_format: Any
    ):
        """Create deductions worksheet"""
        worksheet = workbook.add_worksheet("Retenues")

        # Headers
        headers = [
            'ID', 'Employé', 'Type', 'Description', 'Montant Mensuel',
            'Montant Total', 'Déjà Déduit', 'Solde', 'Date Début',
            'Date Fin', 'Active', 'Récurrente'
        ]

        for col, header in enumerate(headers):
            worksheet.write(0, col, header, header_format)

        # Fetch active deductions for employees in this period
        employe_ids = [entry.employe_id for entry in periode.entries]

        result = await self.db.execute(
            select(RetenueEmploye)
            .where(RetenueEmploye.employe_id.in_(employe_ids))
            .where(RetenueEmploye.est_active.is_(True))
        )
        retenues = result.scalars().all()

        row = 1
        for retenue in retenues:
            # Get employee info
            result = await self.db.execute(
                select(Employe).where(Employe.id == retenue.employe_id)
            )
            employe = result.scalar_one_or_none()

            if not employe:
                continue

            solde = float(retenue.montant_total or 0) - float(retenue.montant_deja_deduit)

            data = [
                retenue.id,
                f"{employe.nom} {employe.prenom}",
                retenue.type_retenue,
                retenue.description,
                float(retenue.montant_mensuel),
                float(retenue.montant_total) if retenue.montant_total else 0,
                float(retenue.montant_deja_deduit),
                solde,
                retenue.date_debut,
                retenue.date_fin,
                'Oui' if retenue.est_active else 'Non',
                'Oui' if retenue.est_recurrente else 'Non'
            ]

            for col, value in enumerate(data):
                if isinstance(value, float) and 4 <= col <= 7:  # Currency columns
                    worksheet.write(row, col, value, currency_format)
                elif col in [8, 9] and value:  # Date columns
                    worksheet.write(row, col, value, date_format)
                else:
                    worksheet.write(row, col, value)
            row += 1

        # Auto-fit columns
        worksheet.set_column(0, 0, 8)
        worksheet.set_column(1, 1, 25)
        worksheet.set_column(2, 2, 15)
        worksheet.set_column(3, 3, 30)
        worksheet.set_column(4, 7, 15)
        worksheet.set_column(8, 9, 12)
        worksheet.set_column(10, 11, 10)

    async def export_periode_to_csv(
        self,
        periode_id: int,
        output_path: Optional[str] = None
    ) -> str:
        """
        Export a payroll period to CSV format

        Args:
            periode_id: ID of the payroll period
            output_path: Optional custom output path

        Returns:
            Path to the generated CSV file
        """
        # Fetch period with entries
        result = await self.db.execute(
            select(PeriodePaie)
            .where(PeriodePaie.id == periode_id)
            .options(selectinload(PeriodePaie.entries))
        )
        periode = result.scalar_one_or_none()

        if not periode:
            raise ValueError(f"Period {periode_id} not found")

        # Generate filename
        if not output_path:
            export_dir = Path("media/exports/payroll")
            export_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"paie_{periode.annee}_{periode.mois:02d}_{timestamp}.csv"
            output_path = str(export_dir / filename)

        # Write CSV
        with open(output_path, 'w', newline='', encoding='utf-8-sig') as csvfile:
            writer = csv.writer(csvfile)

            # Headers
            writer.writerow([
                'ID', 'Employé', 'Matricule', 'Salaire Base', 'Ind. Logement',
                'Ind. Déplacement', 'Ind. Fonction', 'Allocation Familiale',
                'Autres Avantages', 'Salaire Brut', 'Cotisations Patronales',
                'Cotisations Salariales', 'Base Imposable', 'IRE',
                'Retenues Diverses', 'Salaire Net'
            ])

            # Data rows
            for entry in periode.entries:
                # Get employee info
                result = await self.db.execute(
                    select(Employe).where(Employe.id == entry.employe_id)
                )
                employe = result.scalar_one_or_none()

                if not employe:
                    continue

                # Extract cotisations and retenues
                cotisations_patronales = entry.cotisations_patronales or {}
                cotisations_salariales = entry.cotisations_salariales or {}
                retenues_diverses = entry.retenues_diverses or {}

                total_cotisations_patronales = sum(
                    float(v) for v in cotisations_patronales.values()
                    if isinstance(v, (int, float, Decimal))
                )
                total_cotisations_salariales = sum(
                    float(v) for v in cotisations_salariales.values()
                    if isinstance(v, (int, float, Decimal))
                )
                total_retenues = sum(
                    float(v) for v in retenues_diverses.values()
                    if isinstance(v, (int, float, Decimal))
                )

                # Calculate IRE from retenues
                ire = float(retenues_diverses.get('ire', 0))

                writer.writerow([
                    entry.id,
                    f"{employe.nom} {employe.prenom}",
                    employe.matricule or '',
                    float(entry.salaire_base),
                    float(entry.indemnite_logement),
                    float(entry.indemnite_deplacement),
                    float(entry.indemnite_fonction),
                    float(entry.allocation_familiale),
                    float(entry.autres_avantages),
                    float(entry.salaire_brut),
                    total_cotisations_patronales,
                    total_cotisations_salariales,
                    float(entry.base_imposable),
                    ire,
                    total_retenues - ire,
                    float(entry.salaire_net)
                ])

        return output_path

    async def export_all_periodes_to_excel(
        self,
        annee: Optional[int] = None,
        output_path: Optional[str] = None
    ) -> str:
        """
        Export all payroll periods to Excel format

        Args:
            annee: Optional year filter
            output_path: Optional custom output path

        Returns:
            Path to the generated Excel file
        """
        # Fetch periods
        query = select(PeriodePaie)
        if annee:
            query = query.where(PeriodePaie.annee == annee)

        result = await self.db.execute(query)
        periodes = result.scalars().all()

        if not periodes:
            raise ValueError("No periods found")

        # Generate filename
        if not output_path:
            export_dir = Path("media/exports/payroll")
            export_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            year_suffix = f"_{annee}" if annee else ""
            filename = f"paie_all{year_suffix}_{timestamp}.xlsx"
            output_path = str(export_dir / filename)

        # Create workbook
        workbook = xlsxwriter.Workbook(output_path)

        # Add formats
        header_format = workbook.add_format({
            'bold': True,
            'bg_color': '#4472C4',
            'font_color': 'white',
            'border': 1
        })
        currency_format = workbook.add_format({'num_format': '#,##0.00'})

        # Create summary sheet
        worksheet = workbook.add_worksheet("Toutes les Périodes")

        # Headers
        headers = [
            'ID', 'Année', 'Mois', 'Statut', 'Nb Employés',
            'Masse Salariale Brute', 'Cotisations Patronales',
            'Cotisations Salariales', 'Net à Payer'
        ]

        for col, header in enumerate(headers):
            worksheet.write(0, col, header, header_format)

        # Data rows
        row = 1
        for periode in periodes:
            data = [
                periode.id,
                periode.annee,
                periode.mois,
                periode.statut,
                periode.nombre_employes,
                float(periode.masse_salariale_brute),
                float(periode.total_cotisations_patronales),
                float(periode.total_cotisations_salariales),
                float(periode.total_net_a_payer)
            ]

            for col, value in enumerate(data):
                if isinstance(value, float) and col >= 5:  # Currency columns
                    worksheet.write(row, col, value, currency_format)
                else:
                    worksheet.write(row, col, value)
            row += 1

        # Auto-fit columns
        worksheet.set_column(0, 0, 8)
        worksheet.set_column(1, 2, 10)
        worksheet.set_column(3, 3, 12)
        worksheet.set_column(4, 4, 15)
        worksheet.set_column(5, 8, 20)

        workbook.close()
        return output_path

    async def export_retenues_to_csv(
        self,
        employe_id: Optional[int] = None,
        output_path: Optional[str] = None
    ) -> str:
        """
        Export employee deductions to CSV format

        Args:
            employe_id: Optional employee ID filter
            output_path: Optional custom output path

        Returns:
            Path to the generated CSV file
        """
        # Fetch deductions
        query = select(RetenueEmploye)
        if employe_id:
            query = query.where(RetenueEmploye.employe_id == employe_id)

        result = await self.db.execute(query)
        retenues = result.scalars().all()

        if not retenues:
            raise ValueError("No deductions found")

        # Generate filename
        if not output_path:
            export_dir = Path("media/exports/payroll")
            export_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            emp_suffix = f"_emp{employe_id}" if employe_id else ""
            filename = f"retenues{emp_suffix}_{timestamp}.csv"
            output_path = str(export_dir / filename)

        # Write CSV
        with open(output_path, 'w', newline='', encoding='utf-8-sig') as csvfile:
            writer = csv.writer(csvfile)

            # Headers
            writer.writerow([
                'ID', 'Employé ID', 'Employé', 'Type', 'Description',
                'Montant Mensuel', 'Montant Total', 'Déjà Déduit', 'Solde',
                'Date Début', 'Date Fin', 'Active', 'Récurrente'
            ])

            # Data rows
            for retenue in retenues:
                # Get employee info
                result = await self.db.execute(
                    select(Employe).where(Employe.id == retenue.employe_id)
                )
                employe = result.scalar_one_or_none()

                if not employe:
                    continue

                solde = float(retenue.montant_total or 0) - float(retenue.montant_deja_deduit)

                writer.writerow([
                    retenue.id,
                    retenue.employe_id,
                    f"{employe.nom} {employe.prenom}",
                    retenue.type_retenue,
                    retenue.description,
                    float(retenue.montant_mensuel),
                    float(retenue.montant_total) if retenue.montant_total else 0,
                    float(retenue.montant_deja_deduit),
                    solde,
                    retenue.date_debut.strftime('%Y-%m-%d'),
                    retenue.date_fin.strftime('%Y-%m-%d') if retenue.date_fin else '',
                    'Oui' if retenue.est_active else 'Non',
                    'Oui' if retenue.est_recurrente else 'Non'
                ])

        return output_path
