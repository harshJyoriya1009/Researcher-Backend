from fastapi import APIRouter

from app.api.v1 import auth, documents, models, research

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(research.router)
api_router.include_router(documents.router)
api_router.include_router(models.router)
