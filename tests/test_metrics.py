from pi_edge_assistant.services.metrics import MetricsService


def test_metrics_degrade_when_platform_metric_is_unavailable(monkeypatch) -> None:
    def unavailable():
        raise OSError("not available")

    monkeypatch.setattr("pi_edge_assistant.services.metrics.psutil.swap_memory", unavailable)
    snapshot = MetricsService().snapshot()
    assert snapshot["swap_used_mb"] is None
    assert "memory_used_mb" in snapshot
