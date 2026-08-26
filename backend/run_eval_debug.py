"""Debug script - run the evaluation function directly."""
import asyncio
import sys
import os
import logging

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

from app.db import async_session, engine, Base
from app.models import Dataset, TestCase, RAGConfig, EvalRun, EvalResult
from app.services.evaluation_engine import EvaluationEngine


async def main():
    print("=== Direct Evaluation Test ===\n")

    async with async_session() as db:
        from sqlalchemy import select

        # Check what's in the DB
        result = await db.execute(select(EvalRun).order_by(EvalRun.id.desc()))
        runs = result.scalars().all()
        print(f"Found {len(runs)} runs:")
        for run in runs:
            print(f"  Run #{run.id}: status={run.status}")

        # Get the latest run
        if runs:
            target_run = runs[0]
            print(f"\n=== Running Run #{target_run.id} ===")
            print(f"  Dataset: {target_run.dataset_id}")
            print(f"  Config: {target_run.config_id}")

            engine_inst = EvaluationEngine()
            print("EvaluationEngine created. Running...")
            await engine_inst.run_evaluation(
                run_id=target_run.id,
                dataset_id=target_run.dataset_id,
                config_id=target_run.config_id,
                db=db
            )
            print("=== Done ===")


if __name__ == "__main__":
    asyncio.run(main())
