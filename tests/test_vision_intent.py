from pathlib import Path

import pytest

from pi_edge_assistant.services.vision_intent import VisionIntentError, VisionIntentService


@pytest.mark.asyncio
async def test_classifier_reports_missing_artifacts(tmp_path: Path) -> None:
    service = VisionIntentService(tmp_path)
    with pytest.raises(VisionIntentError, match="model.onnx, tokenizer.json, vision_intent_head.npz"):
        await service.classify("我手里拿的是什么？")
