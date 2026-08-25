from pi_edge_assistant.orchestrator import requests_vision
from pi_edge_assistant.services.tts import split_by_language


def test_explicit_visual_triggers_are_bilingual() -> None:
    assert requests_vision("请看看摄像头里有什么")
    assert requests_vision("拍张照片并用中文描述")
    assert requests_vision("What do you see in the camera?")
    assert requests_vision("take a photo and describe it in Chinese")
    assert not requests_vision("请解释什么是边缘计算")


def test_tts_segments_chinese_and_english_sentences() -> None:
    assert split_by_language("你好。Hello there! 再见。") == [
        ("zh", "你好。"),
        ("en", "Hello there!"),
        ("zh", "再见。"),
    ]
    assert split_by_language("请检查 Raspberry Pi 5 的状态。") == [
        ("zh", "请检查"),
        ("en", "Raspberry Pi 5"),
        ("zh", "的状态。"),
    ]
