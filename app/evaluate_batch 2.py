from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from app.services.evaluator import EvaluationSample, rag_evaluator
from app.services.logging_service import app_logger


async def main(path: str) -> None:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    samples = [
        EvaluationSample(
            query=item.get("query", ""),
            retrieved_docs=item.get("retrieved_docs", []),
            answer=item.get("answer", item.get("expected", "")),
            reference_answer=item.get("expected", ""),
            reference_docs=item.get("reference_docs", []),
        )
        for item in data.get("samples", [])
    ]
    result = await rag_evaluator.evaluate_batch(samples)
    app_logger.log("evaluation_script", path=path, summary=result.get("summary", {}))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1]))
