import pytest
from core.metrics import MetricsEngine
from core.server_registry import ServerRegistry
from database.db import init_db, execute_db
import tempfile
import os

@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    init_db(path)
    yield path
    try:
        os.remove(path)
    except Exception:
        pass

def test_metrics_overview_and_p95(temp_db):
    engine = MetricsEngine(db_path=temp_db)

    # Insert sample request logs with known latencies
    latencies = [10.0, 15.0, 20.0, 25.0, 30.0, 35.0, 40.0, 45.0, 50.0, 100.0]
    for i, lat in enumerate(latencies):
        execute_db(
            """INSERT INTO request_logs 
               (request_id, method, path, selected_backend_id, selected_backend_url,
                algorithm_used, status_code, response_time_ms, is_success)
               VALUES (?, 'GET', '/test', 'srv-backend-a', 'http://127.0.0.1:8001', 'ROUND_ROBIN', 200, ?, 1);""",
            (f"req-{i}", lat),
            db_path=temp_db
        )

    data = engine.get_dashboard_metrics()
    assert len(data["trend"]) == 10
    # p95 should capture the 95th percentile (here 100.0)
    assert data["p95_latency_ms"] == 100.0
    assert len(data["distribution"]) == 1
    assert data["distribution"][0]["count"] == 10

def test_recovery_intelligence_calculations(temp_db):
    engine = MetricsEngine(db_path=temp_db)

    # Insert sample fault event with precise detection and recovery duration
    execute_db(
        """INSERT INTO fault_events 
           (event_id, server_id, fault_type, injected_at, detected_at, detection_latency_ms, recovered_at, recovery_duration_ms, status)
           VALUES ('fault-1', 'srv-backend-a', 'DELAY', '2026-10-19 12:00:00', '2026-10-19 12:00:03', 3050.0, '2026-10-19 12:00:10', 7100.0, 'RESOLVED');""",
        db_path=temp_db
    )

    intel = engine.get_recovery_intelligence_metrics()
    assert intel["avg_detection_latency_ms"] == 3050.0
    assert intel["avg_recovery_duration_ms"] == 7100.0
    assert intel["total_faults_tracked"] == 1
    assert intel["recovered_faults_count"] == 1

def test_csv_export(temp_db):
    engine = MetricsEngine(db_path=temp_db)

    execute_db(
        """INSERT INTO request_logs 
           (request_id, method, path, selected_backend_id, selected_backend_url,
            algorithm_used, status_code, response_time_ms, is_success)
           VALUES ('req-csv', 'GET', '/api/data', 'srv-backend-b', 'http://127.0.0.1:8002', 'WEIGHTED_ROUND_ROBIN', 200, 14.5, 1);""",
        db_path=temp_db
    )

    csv_out = engine.export_csv("requests")
    assert "req-csv" in csv_out
    assert "srv-backend-b" in csv_out
    assert "WEIGHTED_ROUND_ROBIN" in csv_out
