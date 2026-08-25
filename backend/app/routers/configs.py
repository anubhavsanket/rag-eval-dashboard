from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db import get_db
from app.models.rag_config import RAGConfig
from app.schemas import RAGConfigCreate, RAGConfigResponse

router = APIRouter(prefix="/api/v1/configs", tags=["configs"])


@router.get("", response_model=list[RAGConfigResponse])
async def list_configs(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(RAGConfig).order_by(RAGConfig.created_at.desc()))
    return [RAGConfigResponse.model_validate(c) for c in result.scalars().all()]


@router.post("", response_model=RAGConfigResponse, status_code=201)
async def create_config(data: RAGConfigCreate, db: AsyncSession = Depends(get_db)):
    config = RAGConfig(
        name=data.name,
        description=data.description,
        config=data.config,
    )
    db.add(config)
    await db.flush()
    await db.refresh(config)
    return RAGConfigResponse.model_validate(config)


@router.get("/{config_id}", response_model=RAGConfigResponse)
async def get_config(config_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(RAGConfig).where(RAGConfig.id == config_id))
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="Config not found")
    return RAGConfigResponse.model_validate(config)


@router.delete("/{config_id}", status_code=204)
async def delete_config(config_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(RAGConfig).where(RAGConfig.id == config_id))
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="Config not found")
    await db.delete(config)
