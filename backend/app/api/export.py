from fastapi import APIRouter, Depends
from app.core.auth_dependencies import require_admin

router = APIRouter(tags=["Export"], dependencies=[Depends(require_admin)])
