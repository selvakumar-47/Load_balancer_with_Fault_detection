import pytest
import time
from unittest.mock import patch, MagicMock
from core.server_registry import ServerRegistry
from core.health_monitor import HealthMonitor
from database.db import init_db
import tempfile
import os
import requests

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

def test_health_monitor_healthy_probe(temp_db):
    registry = ServerRegistry(db_path=temp_db)
    monitor = HealthMonitor(registry, interval=1.0, timeout=1.0)

    server = registry.get_server("srv-backend-a")
    assert server is not None

    mock_resp = MagicMock()
    mock_resp.status_code = 200

    with patch("requests.get", return_value=mock_resp):
        monitor.probe_server(server)

    updated = registry.get_server("srv-backend-a")
    assert updated["status"] == "HEALTHY"
    assert updated["circuit_state"] == "CLOSED"
    assert updated["consecutive_failures"] == 0

def test_health_monitor_detects_timeout_and_trips_circuit(temp_db):
    registry = ServerRegistry(db_path=temp_db)
    monitor = HealthMonitor(registry, interval=1.0, timeout=1.0)

    server = registry.get_server("srv-backend-a")

    with patch("requests.get", side_effect=requests.exceptions.Timeout("Connection timed out")):
        # 1st probe timeout
        monitor.probe_server(server)
        assert registry.get_server("srv-backend-a")["consecutive_failures"] == 1
        assert registry.get_server("srv-backend-a")["circuit_state"] == "CLOSED"

        # 2nd probe timeout
        monitor.probe_server(server)
        assert registry.get_server("srv-backend-a")["consecutive_failures"] == 2
        assert registry.get_server("srv-backend-a")["circuit_state"] == "CLOSED"

        # 3rd probe timeout -> reaches failure threshold of 3 -> trips circuit to OPEN!
        monitor.probe_server(server)
        s = registry.get_server("srv-backend-a")
        assert s["consecutive_failures"] == 3
        assert s["circuit_state"] == "OPEN"

    # Eligible servers should now EXCLUDE srv-backend-a!
    eligible = registry.get_eligible_servers()
    eligible_ids = [srv["id"] for srv in eligible]
    assert "srv-backend-a" not in eligible_ids
    assert "srv-backend-b" in eligible_ids
    assert "srv-backend-c" in eligible_ids
