from fastapi import APIRouter

from app.api.routers import case


api_router = APIRouter()

api_router.include_router(case.router)
