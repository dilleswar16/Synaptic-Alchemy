"""Predictive signals, intelligence reports and the health-score trend."""

from fastapi import APIRouter, Depends, Query, status

from keigan.config.database_config import provide
from keigan.dtos.common_dtos import JobAcceptedResponse
from keigan.dtos.intelligence_dtos import (
    GenerateReportRequest, HealthScoreTrendResponse, IntelligenceReportResponse, IntelligenceReportSummary, PredictiveSignalResponse, PredictiveSignalStatusRequest, SignalInvestigationResponse,
)
from keigan.security.current_user import CurrentUser, get_current_user
from keigan.services.intelligence_service import IntelligenceService

router = APIRouter(prefix="/api", tags=["Intelligence"])


def _split(value: str | None) -> list[str] | None:
    return [item for item in value.split(",") if item] if value else None


@router.get("/predictive-signals", response_model=list[PredictiveSignalResponse])
async def list_predictive_signals(
    application_ids: str | None = Query(None, alias="applicationIds"), detectors: str | None = Query(None), severities: str | None = Query(None), statuses: str | None = Query(None), limit: int = Query(100, ge=1, le=300),
    current_user: CurrentUser = Depends(get_current_user), service: IntelligenceService = Depends(provide(IntelligenceService)),
) -> list[PredictiveSignalResponse]:
    return await service.list_signals(current_user, _split(application_ids), _split(detectors), _split(severities), _split(statuses), limit)


@router.patch("/predictive-signals/{signal_id}", response_model=PredictiveSignalResponse)
async def update_predictive_signal(signal_id: str, request: PredictiveSignalStatusRequest, current_user: CurrentUser = Depends(get_current_user), service: IntelligenceService = Depends(provide(IntelligenceService))) -> PredictiveSignalResponse:
    return await service.update_signal_status(current_user, signal_id, request)


@router.post("/predictive-signals/{signal_id}/investigate", response_model=SignalInvestigationResponse, status_code=status.HTTP_202_ACCEPTED)
async def investigate_predictive_signal(signal_id: str, current_user: CurrentUser = Depends(get_current_user), service: IntelligenceService = Depends(provide(IntelligenceService))) -> SignalInvestigationResponse:
    return await service.investigate_signal(current_user, signal_id)


@router.get("/intelligence-reports", response_model=list[IntelligenceReportSummary])
async def list_intelligence_reports(application_id: str | None = Query(None, alias="applicationId"), current_user: CurrentUser = Depends(get_current_user), service: IntelligenceService = Depends(provide(IntelligenceService))) -> list[IntelligenceReportSummary]:
    return await service.list_reports(current_user, application_id)


@router.get("/intelligence-reports/{report_id}", response_model=IntelligenceReportResponse)
async def get_intelligence_report(report_id: str, current_user: CurrentUser = Depends(get_current_user), service: IntelligenceService = Depends(provide(IntelligenceService))) -> IntelligenceReportResponse:
    return await service.get_report(current_user, report_id)


@router.post("/applications/{application_id}/intelligence-reports/generate", response_model=JobAcceptedResponse, status_code=status.HTTP_202_ACCEPTED)
async def generate_intelligence_report(application_id: str, request: GenerateReportRequest, current_user: CurrentUser = Depends(get_current_user), service: IntelligenceService = Depends(provide(IntelligenceService))) -> JobAcceptedResponse:
    return JobAcceptedResponse(job_id=await service.request_report(current_user, application_id, request.report_type, request.send_to_stakeholders))


@router.get("/applications/{application_id}/health-score-trend", response_model=HealthScoreTrendResponse)
async def get_health_score_trend(application_id: str, days: int = Query(30, ge=7, le=90), current_user: CurrentUser = Depends(get_current_user), service: IntelligenceService = Depends(provide(IntelligenceService))) -> HealthScoreTrendResponse:
    return await service.get_health_score_trend(current_user, application_id, days)
