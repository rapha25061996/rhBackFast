"""FastAPI routes for paie_app"""
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.permissions import require_permission
from app.core.config import settings
from app.core.query_utils import apply_expansion, parse_expand_param
from app.user_app.models import User
from app.paie_app import schemas
from app.paie_app.models import (
    Alert, RetenueEmploye, PeriodePaie, EntreePaie
)
from app.paie_app.services import (
    SalaryCalculatorService,
    PeriodProcessorService,
    DeductionManagerService,
    PayslipGeneratorService,
    ExportService,
    StatisticsService,
    NotificationService
)
from app.audit_app.constants import AuditAction, AuditResourceType
from app.audit_app.services import AuditService


# Alert Routes
alert_router = APIRouter(prefix="/alerts", tags=["Alerts"])


@alert_router.get("/", response_model=List[schemas.AlertResponse])
async def list_alerts(
    skip: int = 0,
    limit: int = 100,
    expand: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("alert", "view"))
):
    """List all alerts (optional ?expand=employe)"""
    query = select(Alert)
    if expand:
        query = apply_expansion(query, Alert, parse_expand_param(expand))
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


@alert_router.post("/", response_model=schemas.AlertResponse)
async def create_alert(
    alert: schemas.AlertCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("alert", "create"))
):
    """Create a new alert"""
    db_alert = Alert(**alert.model_dump())
    db.add(db_alert)
    await db.commit()
    await db.refresh(db_alert)

    await AuditService.log_action(
        db=db,
        user=current_user,
        action=AuditAction.CREATE.value,
        resource_type=AuditResourceType.ALERT.value,
        resource_id=str(db_alert.id),
        new_values=alert.model_dump(),
        request=request
    )

    # Send notification if enabled
    if hasattr(settings, 'NOTIFICATIONS_ENABLED') and settings.NOTIFICATIONS_ENABLED:
        notification_service = NotificationService(db)
        await notification_service.send_alert_notification(db_alert.id)

    return db_alert


@alert_router.get("/{alert_id}", response_model=schemas.AlertResponse)
async def get_alert(
    alert_id: int,
    expand: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("alert", "view"))
):
    """Get alert by ID (optional ?expand=employe)"""
    query = select(Alert).where(Alert.id == alert_id)
    if expand:
        query = apply_expansion(query, Alert, parse_expand_param(expand))
    result = await db.execute(query)
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert


@alert_router.post("/{alert_id}/send-notification")
async def send_alert_notification(
    alert_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("alert", "update"))
):
    """Manually send notification for an alert"""
    notification_service = NotificationService(db)
    try:
        success = await notification_service.send_alert_notification(alert_id)

        await AuditService.log_action(
            db=db,
            user=current_user,
            action=AuditAction.UPDATE.value,
            resource_type=AuditResourceType.ALERT.value,
            resource_id=str(alert_id),
            new_values={"action": "send_notification", "success": success},
            request=request
        )

        if success:
            return {"message": "Notification sent successfully"}
        else:
            raise HTTPException(
                status_code=500,
                detail="Failed to send notification"
            )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error sending notification: {str(e)}"
        ) from e


# Retenue Routes
retenue_router = APIRouter(prefix="/retenues", tags=["Retenues"])


@retenue_router.get("/")
async def list_retenues(
    skip: int = 0,
    limit: int = 100,
    employe_id: int = Query(None),
    expand: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("retenue", "view"))
):
    """List all employee deductions (optional ?expand=employe)"""
    query = select(RetenueEmploye)
    if employe_id:
        query = query.where(RetenueEmploye.employe_id == employe_id)
    if expand:
        query = apply_expansion(query, RetenueEmploye, parse_expand_param(expand))
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


@retenue_router.post("/")
async def create_retenue(
    retenue: schemas.RetenueEmployeCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("retenue", "create"))
):
    """Create a new employee deduction"""
    deduction_service = DeductionManagerService(db)
    try:
        db_retenue = await deduction_service.create_deduction(
            retenue.model_dump()
        )
        await AuditService.log_action(
            db=db,
            user=current_user,
            action=AuditAction.CREATE.value,
            resource_type=AuditResourceType.RETENUE.value,
            resource_id=str(db_retenue.id),
            new_values=retenue.model_dump(),
            request=request
        )

        # Send notification if enabled
        if hasattr(settings, 'NOTIFICATIONS_ENABLED') and settings.NOTIFICATIONS_ENABLED:
            notification_service = NotificationService(db)
            await notification_service.notify_deduction_created(db_retenue.id)

        return db_retenue
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


# Periode Routes
periode_router = APIRouter(prefix="/periodes", tags=["Periodes"])


@periode_router.get("/")
async def list_periodes(
    skip: int = 0,
    limit: int = 100,
    annee: int = Query(None),
    mois: int = Query(None),
    expand: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("periode", "view"))
):
    """List all payroll periods (optional ?expand=entries,etape_courante,statut_global,responsable)"""
    query = select(PeriodePaie)
    if annee:
        query = query.where(PeriodePaie.annee == annee)
    if mois:
        query = query.where(PeriodePaie.mois == mois)
    if expand:
        query = apply_expansion(query, PeriodePaie, parse_expand_param(expand))
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


@periode_router.post("/")
async def create_periode(
    periode: schemas.PeriodePaieCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("periode", "create"))
):
    """Create a new payroll period"""
    processor = PeriodProcessorService(db)
    try:
        db_periode = await processor.create_period(
            annee=periode.annee,
            mois=periode.mois,
            user_id=current_user.id
        )
        await AuditService.log_action(
            db=db,
            user=current_user,
            action=AuditAction.CREATE.value,
            resource_type=AuditResourceType.PERIODE_PAIE.value,
            resource_id=str(db_periode.id),
            new_values={"annee": periode.annee, "mois": periode.mois},
            request=request
        )
        return db_periode
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@periode_router.post("/{periode_id}/process")
async def process_periode(
    periode_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("periode", "update"))
):
    """Process a payroll period"""
    processor = PeriodProcessorService(db)
    try:
        results = await processor.process_period(periode_id)
        await AuditService.log_action(
            db=db,
            user=current_user,
            action=AuditAction.UPDATE.value,
            resource_type=AuditResourceType.PERIODE_PAIE.value,
            resource_id=str(periode_id),
            new_values={"action": "process", "results": results},
            request=request
        )

        # Send notification if enabled
        if hasattr(settings, 'NOTIFICATIONS_ENABLED') and settings.NOTIFICATIONS_ENABLED:
            notification_service = NotificationService(db)
            await notification_service.notify_period_processed(periode_id)

        return results
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@periode_router.post("/{periode_id}/finalize")
async def finalize_periode(
    periode_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("periode", "update"))
):
    """Finalize a payroll period"""
    processor = PeriodProcessorService(db)
    try:
        await processor.finalize_period(periode_id)
        await AuditService.log_action(
            db=db,
            user=current_user,
            action=AuditAction.UPDATE.value,
            resource_type=AuditResourceType.PERIODE_PAIE.value,
            resource_id=str(periode_id),
            new_values={"action": "finalize"},
            request=request
        )
        return {"message": "Period finalized successfully"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@periode_router.post("/{periode_id}/approve")
async def approve_periode(
    periode_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("periode", "update"))
):
    """Approve a payroll period"""
    processor = PeriodProcessorService(db)
    try:
        await processor.approve_period(periode_id, current_user.id)
        await AuditService.log_action(
            db=db,
            user=current_user,
            action=AuditAction.UPDATE.value,
            resource_type=AuditResourceType.PERIODE_PAIE.value,
            resource_id=str(periode_id),
            new_values={"action": "approve"},
            request=request
        )

        # Send notification if enabled
        if hasattr(settings, 'NOTIFICATIONS_ENABLED') and settings.NOTIFICATIONS_ENABLED:
            notification_service = NotificationService(db)
            await notification_service.notify_period_approved(periode_id)

        return {"message": "Period approved successfully"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


# Entree Routes
entree_router = APIRouter(prefix="/entrees", tags=["Entrees"])


@entree_router.get("/")
async def list_entrees(
    skip: int = 0,
    limit: int = 100,
    periode_id: int = Query(None),
    expand: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("entree", "view"))
):
    """List all payroll entries (optional ?expand=employe,periode_paie)"""
    query = select(EntreePaie)
    if periode_id:
        query = query.where(EntreePaie.periode_paie_id == periode_id)
    if expand:
        query = apply_expansion(query, EntreePaie, parse_expand_param(expand))
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


@entree_router.post("/{entree_id}/calculate")
async def calculate_entree(
    entree_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("entree", "update")),
    request: Request = None,  # type: ignore[assignment]
):
    """Recalculate a payroll entry"""
    result = await db.execute(
        select(EntreePaie).where(EntreePaie.id == entree_id)
    )
    db_entree = result.scalar_one_or_none()
    if not db_entree:
        raise HTTPException(status_code=404, detail="Entree not found")

    calculator = SalaryCalculatorService(db)
    try:
        salary_data = await calculator.calculate_salary(
            db_entree.employe_id,
            db_entree.periode_paie_id
        )
        db_entree.salaire_base = salary_data['salaire_base']
        db_entree.salaire_brut = salary_data['salaire_brut']
        db_entree.salaire_net = salary_data['salaire_net']
        await db.commit()
        await db.refresh(db_entree)

        await AuditService.log_action(
            db=db,
            user=current_user,
            action=AuditAction.UPDATE.value,
            resource_type=AuditResourceType.ENTREE_PAIE.value,
            resource_id=str(entree_id),
            new_values={"action": "calculate"},
            request=request
        )
        return db_entree
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


# Export Routes
payroll_router = APIRouter(prefix="/payroll", tags=["Payroll"])


@payroll_router.get("/export/periode/{periode_id}")
async def export_periode(
    periode_id: int,
    export_format: str = Query("excel", pattern="^(excel|csv)$"),
    request: Request = None,  # type: ignore[assignment]
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("payroll", "view"))
):
    """Export a specific payroll period to Excel or CSV"""
    export_service = ExportService(db)

    try:
        if export_format == "excel":
            file_path = await export_service.export_periode_to_excel(periode_id)
        else:  # csv
            file_path = await export_service.export_periode_to_csv(periode_id)

        await AuditService.log_export(
            db=db,
            user=current_user,
            resource_type=AuditResourceType.PERIODE_PAIE.value,
            format_type=export_format,
            count=1,
            request=request
        )

        return FileResponse(
            path=file_path,
            media_type=(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                if export_format == "excel" else "text/csv"
            ),
            filename=Path(file_path).name
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error exporting period: {str(e)}"
        ) from e


@payroll_router.get("/export/all-periodes")
async def export_all_periodes(
    annee: Optional[int] = Query(None),
    request: Request = None,  # type: ignore[assignment]
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("payroll", "view"))
):
    """Export all payroll periods to Excel"""
    export_service = ExportService(db)

    try:
        file_path = await export_service.export_all_periodes_to_excel(annee)

        await AuditService.log_export(
            db=db,
            user=current_user,
            resource_type=AuditResourceType.ALL_PERIODES.value,
            format_type="excel",
            count=1,
            request=request
        )

        return FileResponse(
            path=file_path,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename=Path(file_path).name
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error exporting periods: {str(e)}"
        ) from e


@payroll_router.get("/export/retenues")
async def export_retenues(
    employe_id: Optional[int] = Query(None),
    request: Request = None,  # type: ignore[assignment]
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("payroll", "view"))
):
    """Export employee deductions to CSV"""
    export_service = ExportService(db)

    try:
        file_path = await export_service.export_retenues_to_csv(employe_id)

        await AuditService.log_export(
            db=db,
            user=current_user,
            resource_type=AuditResourceType.RETENUES.value,
            format_type="csv",
            count=1,
            request=request
        )

        return FileResponse(
            path=file_path,
            media_type="text/csv",
            filename=Path(file_path).name
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error exporting deductions: {str(e)}"
        ) from e


@payroll_router.get("/export")
async def export_payroll(
    export_format: str = Query("excel", pattern="^(excel|csv|json)$"),
    request: Request = None,  # type: ignore[assignment]
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("payroll", "view"))
):
    """Export payroll data (deprecated - use specific endpoints)"""
    result = await db.execute(select(PeriodePaie))
    periodes = result.scalars().all()

    await AuditService.log_export(
        db=db,
        user=current_user,
        resource_type=AuditResourceType.PAYROLL.value,
        format_type=export_format,
        count=len(periodes),
        request=request
    )

    return {
        "message": f"Payroll export {export_format} requested",
        "count": len(periodes),
        "format": export_format,
        "note": "This endpoint is deprecated. Use /export/periode/{id} or /export/all-periodes"
    }


@payroll_router.post("/entrees/{entree_id}/generate-payslip")
async def generate_payslip(
    entree_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("entree", "view"))
):
    """Generate PDF payslip for a specific payroll entry"""
    generator = PayslipGeneratorService(db)
    try:
        file_path = await generator.generate_payslip(entree_id)

        await AuditService.log_action(
            db=db,
            user=current_user,
            action=AuditAction.CREATE.value,
            resource_type=AuditResourceType.PAYSLIP.value,
            resource_id=str(entree_id),
            new_values={"file_path": file_path},
            request=request
        )

        # Send notification if enabled
        if hasattr(settings, 'NOTIFICATIONS_ENABLED') and settings.NOTIFICATIONS_ENABLED:
            notification_service = NotificationService(db)
            await notification_service.notify_payslip_generated(entree_id)

        return {
            "message": "Payslip generated successfully",
            "file_path": file_path,
            "entree_id": entree_id
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error generating payslip: {str(e)}"
        ) from e


@payroll_router.get("/entrees/{entree_id}/download-payslip")
async def download_payslip(
    entree_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("entree", "view"))
):
    """Download PDF payslip for a specific payroll entry"""
    result = await db.execute(
        select(EntreePaie).where(EntreePaie.id == entree_id)
    )
    entree = result.scalar_one_or_none()

    if not entree:
        raise HTTPException(status_code=404, detail="Payroll entry not found")

    if not entree.payslip_generated or not entree.payslip_file:
        raise HTTPException(
            status_code=404,
            detail="Payslip not generated yet. Please generate it first."
        )

    # Check if file exists
    file_path = Path(entree.payslip_file)
    if not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail="Payslip file not found on disk"
        )

    return FileResponse(
        path=str(file_path),
        media_type="application/pdf",
        filename=file_path.name
    )


@payroll_router.post("/periodes/{periode_id}/generate-all-payslips")
async def generate_all_payslips(
    periode_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("periode", "view"))
):
    """Generate PDF payslips for all entries in a payroll period"""
    generator = PayslipGeneratorService(db)
    try:
        file_paths = await generator.generate_bulk_payslips(periode_id)

        await AuditService.log_action(
            db=db,
            user=current_user,
            action=AuditAction.CREATE.value,
            resource_type=AuditResourceType.PAYSLIP_BULK.value,
            resource_id=str(periode_id),
            new_values={
                "count": len(file_paths),
                "file_paths": file_paths
            },
            request=request
        )

        return {
            "message": f"Generated {len(file_paths)} payslips successfully",
            "count": len(file_paths),
            "file_paths": file_paths,
            "periode_id": periode_id
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error generating payslips: {str(e)}"
        ) from e


# Statistics Routes
statistics_router = APIRouter(prefix="/statistics", tags=["Statistics"])


@statistics_router.get("/periode/{periode_id}/summary")
async def get_period_summary(
    periode_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("payroll", "view"))
):
    """Get comprehensive summary for a specific payroll period"""
    stats_service = StatisticsService(db)
    try:
        return await stats_service.get_period_summary(periode_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@statistics_router.get("/annual/{annee}/summary")
async def get_annual_summary(
    annee: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("payroll", "view"))
):
    """Get annual payroll summary"""
    stats_service = StatisticsService(db)
    try:
        return await stats_service.get_annual_summary(annee)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@statistics_router.get("/employee/{employe_id}/history")
async def get_employee_history(
    employe_id: int,
    annee: Optional[int] = Query(None),
    limit: int = Query(12, ge=1, le=24),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("payroll", "view"))
):
    """Get payroll history for a specific employee"""
    stats_service = StatisticsService(db)
    try:
        return await stats_service.get_employee_payroll_history(
            employe_id, annee, limit
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@statistics_router.get("/deductions/summary")
async def get_deductions_summary(
    employe_id: Optional[int] = Query(None),
    type_retenue: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("retenue", "view"))
):
    """Get summary of employee deductions"""
    stats_service = StatisticsService(db)
    return await stats_service.get_deductions_summary(
        employe_id, type_retenue
    )


@statistics_router.get("/alerts/summary")
async def get_alerts_summary(
    periode_id: Optional[int] = Query(None),
    severity: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("alert", "view"))
):
    """Get summary of payroll alerts"""
    stats_service = StatisticsService(db)
    return await stats_service.get_alerts_summary(
        periode_id, severity, status
    )


@statistics_router.get("/comparative/{annee}/{mois}")
async def get_comparative_analysis(
    annee: int,
    mois: int,
    compare_to_previous: bool = Query(
        True,
        description="True for previous month, False for same month last year"
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("payroll", "view"))
):
    """Compare current period with previous period or same month last year"""
    stats_service = StatisticsService(db)
    try:
        return await stats_service.get_comparative_analysis(
            annee, mois, compare_to_previous
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@statistics_router.get("/top-earners")
async def get_top_earners(
    periode_id: Optional[int] = Query(None),
    annee: Optional[int] = Query(None),
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("payroll", "view"))
):
    """Get top earners for a period or year"""
    if not periode_id and not annee:
        raise HTTPException(
            status_code=400,
            detail="Either periode_id or annee must be provided"
        )

    stats_service = StatisticsService(db)
    try:
        return await stats_service.get_top_earners(
            periode_id, annee, limit
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@statistics_router.get("/dashboard")
async def get_dashboard_summary(
    annee: Optional[int] = Query(None),
    mois: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("payroll", "view"))
):
    """Get comprehensive dashboard summary"""
    stats_service = StatisticsService(db)
    return await stats_service.get_dashboard_summary(annee, mois)


# Modification History Routes
history_router = APIRouter(prefix="/history", tags=["Modification History"])


@history_router.get(
    "/entrees/{entree_id}",
    response_model=schemas.ModificationHistoryResponse
)
async def get_entree_modification_history(
    entree_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("entree", "view"))
):
    """Get modification history for a payroll entry"""
    from app.paie_app.services import ModificationHistoryService

    # Verify entree exists
    result = await db.execute(
        select(EntreePaie).where(EntreePaie.id == entree_id)
    )
    entree = result.scalar_one_or_none()
    if not entree:
        raise HTTPException(status_code=404, detail="Entree not found")

    # Get history
    history = await ModificationHistoryService.get_entree_history(
        db, entree_id
    )

    return {
        "resource_type": "entree_paie",
        "resource_id": entree_id,
        "history": history,
        "total_modifications": len(history)
    }


@history_router.get(
    "/retenues/{retenue_id}",
    response_model=schemas.ModificationHistoryResponse
)
async def get_retenue_modification_history(
    retenue_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("retenue", "view"))
):
    """Get modification history for an employee deduction"""
    from app.paie_app.services import ModificationHistoryService

    # Verify retenue exists
    result = await db.execute(
        select(RetenueEmploye).where(RetenueEmploye.id == retenue_id)
    )
    retenue = result.scalar_one_or_none()
    if not retenue:
        raise HTTPException(status_code=404, detail="Retenue not found")

    # Get history
    history = await ModificationHistoryService.get_retenue_history(
        db, retenue_id
    )

    return {
        "resource_type": "retenue_employe",
        "resource_id": retenue_id,
        "history": history,
        "total_modifications": len(history)
    }


# Main Router
def get_paie_app_router():
    """Get the main paie_app router"""
    from app.paie_app.workflow_routes import workflow_router

    main_router = APIRouter()
    main_router.include_router(alert_router)
    main_router.include_router(retenue_router)
    main_router.include_router(periode_router)
    main_router.include_router(entree_router)
    main_router.include_router(payroll_router)
    main_router.include_router(statistics_router)
    main_router.include_router(history_router)
    main_router.include_router(workflow_router)
    return main_router
