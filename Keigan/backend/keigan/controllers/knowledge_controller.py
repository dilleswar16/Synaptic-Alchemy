"""Knowledge endpoints: capture prompt, documents, topology and runbooks."""

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile, status

from keigan.config.database_config import provide
from keigan.dtos.common_dtos import JobAcceptedResponse
from keigan.dtos.knowledge_dtos import (
    CapturePromptResponse,
    DocumentUploadResponse,
    KnowledgeDocumentDetailResponse,
    KnowledgeDocumentResponse,
    RunbookCreateRequest,
    RunbookHealthResponse,
    RunbookResponse,
    RunbookUpdateRequest,
    TopologyResponse,
    TopologyReviewRequest,
    TopologyReviewResponse,
)
from keigan.security.current_user import CurrentUser, require_application_admin, require_application_reader
from keigan.security.security_middleware import rate_limiter
from keigan.services.knowledge_service import KnowledgeService
from keigan.services.runbook_health_service import RunbookHealthService
from keigan.services.runbook_service import RunbookService
from keigan.services.topology_service import TopologyService

router = APIRouter(prefix="/api", tags=["Knowledge"])
APPLICATION_PATH = "/applications/{application_id}"
UPLOADS_PER_MINUTE = 20

ReaderDependency = Depends(require_application_reader)
AdminDependency = Depends(require_application_admin)
KnowledgeDependency = Depends(provide(KnowledgeService))
TopologyDependency = Depends(provide(TopologyService))
RunbookDependency = Depends(provide(RunbookService))


# ── Capture prompt and documents ───────────────────────────────────────────────
@router.get(f"{APPLICATION_PATH}/knowledge/capture-prompt", response_model=CapturePromptResponse)
async def get_capture_prompt(
    application_id: str, service_id: str | None = Query(default=None, alias="serviceId"), _user: CurrentUser = ReaderDependency, knowledge_service: KnowledgeService = KnowledgeDependency
) -> CapturePromptResponse:
    return await knowledge_service.get_capture_prompt(application_id, service_id)


@router.get(f"{APPLICATION_PATH}/knowledge/documents", response_model=list[KnowledgeDocumentResponse])
async def list_documents(application_id: str, _user: CurrentUser = ReaderDependency, knowledge_service: KnowledgeService = KnowledgeDependency) -> list[KnowledgeDocumentResponse]:
    return await knowledge_service.list_documents(application_id)


@router.post(f"{APPLICATION_PATH}/knowledge/documents", response_model=DocumentUploadResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_document(
    application_id: str,
    file: UploadFile = File(...),
    document_category: str = Form(alias="documentCategory"),
    service_id: str | None = Form(default=None, alias="serviceId"),
    document_title: str | None = Form(default=None, alias="documentTitle"),
    current_user: CurrentUser = AdminDependency,
    knowledge_service: KnowledgeService = KnowledgeDependency,
) -> DocumentUploadResponse:
    rate_limiter.check(f"knowledge-upload:{current_user.user_principal_name}", UPLOADS_PER_MINUTE)
    return await knowledge_service.upload_document(current_user, application_id, file, service_id or None, document_category, document_title)


@router.get(f"{APPLICATION_PATH}/knowledge/documents/{{document_id}}", response_model=KnowledgeDocumentDetailResponse)
async def get_document(
    application_id: str, document_id: str, _user: CurrentUser = ReaderDependency, knowledge_service: KnowledgeService = KnowledgeDependency
) -> KnowledgeDocumentDetailResponse:
    return await knowledge_service.get_document(application_id, document_id)


@router.delete(f"{APPLICATION_PATH}/knowledge/documents/{{document_id}}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    application_id: str, document_id: str, current_user: CurrentUser = AdminDependency, knowledge_service: KnowledgeService = KnowledgeDependency
) -> Response:
    await knowledge_service.delete_document(current_user, application_id, document_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(f"{APPLICATION_PATH}/knowledge/documents/{{document_id}}/content")
async def download_document(
    application_id: str, document_id: str, _user: CurrentUser = ReaderDependency, knowledge_service: KnowledgeService = KnowledgeDependency
) -> Response:
    file_bytes, content_type, file_name = await knowledge_service.read_document_content(application_id, document_id)
    return Response(
        content=file_bytes,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{file_name}"', "X-Content-Type-Options": "nosniff"},
    )


# ── Topology ───────────────────────────────────────────────────────────────────
@router.post(f"{APPLICATION_PATH}/topology/build", response_model=JobAcceptedResponse, status_code=status.HTTP_202_ACCEPTED)
async def build_topology(application_id: str, current_user: CurrentUser = AdminDependency, topology_service: TopologyService = TopologyDependency) -> JobAcceptedResponse:
    return await topology_service.start_build(current_user, application_id)


@router.get(f"{APPLICATION_PATH}/topology", response_model=TopologyResponse)
async def get_topology(application_id: str, _user: CurrentUser = ReaderDependency, topology_service: TopologyService = TopologyDependency) -> TopologyResponse:
    return await topology_service.get_topology(application_id)


@router.post(f"{APPLICATION_PATH}/topology/{{topology_id}}/reviews", response_model=TopologyReviewResponse, status_code=status.HTTP_201_CREATED)
async def add_topology_review(
    application_id: str, topology_id: str, request: TopologyReviewRequest, current_user: CurrentUser = AdminDependency, topology_service: TopologyService = TopologyDependency
) -> TopologyReviewResponse:
    return await topology_service.add_review(current_user, application_id, topology_id, request)


# ── Runbooks ───────────────────────────────────────────────────────────────────
@router.get(f"{APPLICATION_PATH}/runbooks", response_model=list[RunbookResponse])
async def list_runbooks(application_id: str, _user: CurrentUser = ReaderDependency, runbook_service: RunbookService = RunbookDependency) -> list[RunbookResponse]:
    return await runbook_service.list_runbooks(application_id)


@router.post(f"{APPLICATION_PATH}/runbooks", response_model=RunbookResponse, status_code=status.HTTP_201_CREATED)
async def create_runbook(
    application_id: str, request: RunbookCreateRequest, current_user: CurrentUser = AdminDependency, runbook_service: RunbookService = RunbookDependency
) -> RunbookResponse:
    return await runbook_service.create_runbook(current_user, application_id, request)


@router.get(f"{APPLICATION_PATH}/runbook-health", response_model=RunbookHealthResponse)
async def get_runbook_health(application_id: str, _user: CurrentUser = ReaderDependency, runbook_health_service: RunbookHealthService = Depends(provide(RunbookHealthService))) -> RunbookHealthResponse:
    """Which runbooks need attention and why: never used, not updated, often rated incorrect, no symptoms, no steps. Computed on read from stored rows; nothing is edited."""
    return await runbook_health_service.report(application_id)


@router.get(f"{APPLICATION_PATH}/runbooks/{{runbook_id}}", response_model=RunbookResponse)
async def get_runbook(application_id: str, runbook_id: str, _user: CurrentUser = ReaderDependency, runbook_service: RunbookService = RunbookDependency) -> RunbookResponse:
    return await runbook_service.get_runbook(application_id, runbook_id)


@router.patch(f"{APPLICATION_PATH}/runbooks/{{runbook_id}}", response_model=RunbookResponse)
async def update_runbook(
    application_id: str, runbook_id: str, request: RunbookUpdateRequest, current_user: CurrentUser = AdminDependency, runbook_service: RunbookService = RunbookDependency
) -> RunbookResponse:
    return await runbook_service.update_runbook(current_user, application_id, runbook_id, request)


@router.delete(f"{APPLICATION_PATH}/runbooks/{{runbook_id}}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_runbook(application_id: str, runbook_id: str, current_user: CurrentUser = AdminDependency, runbook_service: RunbookService = RunbookDependency) -> Response:
    await runbook_service.delete_runbook(current_user, application_id, runbook_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
