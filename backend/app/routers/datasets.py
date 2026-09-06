from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.db import get_db
from app.models.dataset import Dataset
from app.models.test_case import TestCase
from app.schemas import (
    DatasetCreate,
    DatasetResponse,
    DatasetDetailResponse,
    TestCaseCreate,
    TestCaseResponse,
)

router = APIRouter(prefix="/api/v1/datasets", tags=["datasets"])


@router.get("", response_model=list[DatasetResponse])
async def list_datasets(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(
            Dataset,
            func.count(TestCase.id).label("test_case_count"),
        )
        .outerjoin(TestCase)
        .group_by(Dataset.id)
        .order_by(Dataset.created_at.desc())
    )
    rows = result.all()
    datasets = []
    for dataset, count in rows:
        ds = DatasetResponse.model_validate(dataset)
        ds.test_case_count = count
        datasets.append(ds)
    return datasets


@router.post("", response_model=DatasetDetailResponse, status_code=201)
async def create_dataset(data: DatasetCreate, db: AsyncSession = Depends(get_db)):
    dataset = Dataset(
        name=data.name,
        description=data.description,
        tags=data.tags,
    )
    db.add(dataset)
    await db.flush()

    for tc in data.test_cases:
        test_case = TestCase(
            dataset_id=dataset.id,
            query=tc.query,
            expected_answer=tc.expected_answer,
            context_chunks=tc.context_chunks,
            extra_meta=tc.metadata,
        )
        db.add(test_case)

    await db.flush()
    await db.refresh(dataset)

    # Fetch with test cases
    result = await db.execute(
        select(Dataset).options(selectinload(Dataset.test_cases)).where(Dataset.id == dataset.id)
    )
    dataset = result.scalar_one()
    return DatasetDetailResponse(
        **DatasetResponse.model_validate(dataset).model_dump(),
        test_cases=[TestCaseResponse.from_orm_model(tc) for tc in dataset.test_cases],
    )


@router.get("/{dataset_id}", response_model=DatasetDetailResponse)
async def get_dataset(dataset_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Dataset).options(selectinload(Dataset.test_cases)).where(Dataset.id == dataset_id)
    )
    dataset = result.scalar_one_or_none()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    return DatasetDetailResponse(
        **DatasetResponse.model_validate(dataset).model_dump(),
        test_cases=[TestCaseResponse.from_orm_model(tc) for tc in dataset.test_cases],
    )


@router.delete("/{dataset_id}", status_code=204)
async def delete_dataset(dataset_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Dataset).where(Dataset.id == dataset_id))
    dataset = result.scalar_one_or_none()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    # Refuse to delete datasets that have evaluation history — runs reference
    # the dataset and its test cases via FKs, so deleting would corrupt history.
    from app.models.eval_run import EvalRun
    result = await db.execute(
        select(func.count()).select_from(EvalRun).where(EvalRun.dataset_id == dataset_id)
    )
    run_count = result.scalar_one()
    if run_count > 0:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot delete dataset: {run_count} evaluation run(s) reference it. Delete those runs first.",
        )

    await db.delete(dataset)


@router.post("/upload", response_model=DatasetDetailResponse, status_code=201)
async def upload_dataset_file(
    file: UploadFile = File(...),
    name: str = "",
    description: str = "",
    db: AsyncSession = Depends(get_db),
):
    import json

    content = await file.read()
    data = json.loads(content)

    # Support both wrapped and raw formats
    if "test_cases" in data:
        test_cases_data = data["test_cases"]
        name = data.get("name", name)
        description = data.get("description", description)
        tags = data.get("tags", [])
    else:
        test_cases_data = data
        tags = []

    dataset = Dataset(name=name, description=description, tags=tags)
    db.add(dataset)
    await db.flush()

    for tc in test_cases_data:
        test_case = TestCase(
            dataset_id=dataset.id,
            query=tc["query"],
            expected_answer=tc["expected_answer"],
            context_chunks=tc.get("context_chunks", []),
            extra_meta=tc.get("metadata", {}),
        )
        db.add(test_case)

    await db.flush()
    await db.refresh(dataset)

    result = await db.execute(
        select(Dataset).options(selectinload(Dataset.test_cases)).where(Dataset.id == dataset.id)
    )
    dataset = result.scalar_one()
    return DatasetDetailResponse(
        **DatasetResponse.model_validate(dataset).model_dump(),
        test_cases=[TestCaseResponse.from_orm_model(tc) for tc in dataset.test_cases],
    )
