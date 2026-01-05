from fastapi import APIRouter
from app.core.logging import get_logger
from app.core.db import SessionDep
from app.models.case import CasePublic, CaseCreate, CaseUpdate

logger = get_logger(__name__)

router = APIRouter(prefix="/case", tags=["case"])


@router.get("/", response_model=list[CasePublic])
def get_cases(session: SessionDep):
    pass


@router.post("/", response_model=CasePublic)
def create_case(case: CaseCreate, session: SessionDep):
    pass


@router.put("/{case_id}", response_model=CasePublic)
def update_case(case_id: int, case: CaseUpdate, session: SessionDep):
    pass


@router.delete("/{case_id}", response_model=CasePublic)
def delete_case(case_id: int, session: SessionDep):
    pass


@router.get("/{case_id}", response_model=CasePublic)
def get_case(case_id: int, session: SessionDep):
    pass
