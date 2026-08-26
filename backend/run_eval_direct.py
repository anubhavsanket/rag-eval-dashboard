"""Direct evaluation runner that bypasses HTTP."""
import asyncio
import json
import os
import sys

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.db import async_session
from app.services.evaluation_engine import EvaluationEngine


async def main():
    async with async_session() as db:
        engine = EvaluationEngine()
        print("Running evaluation directly...")
        await engine.run_evaluation(
            run_id=1,
            dataset_id=1,
            config_id=1,
            db=db
        )
        print("Evaluation complete!")


if __name__ == "__main__":
    asyncio.run(main())
