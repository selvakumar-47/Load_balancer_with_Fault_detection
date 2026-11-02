import time
import pytest
from unittest.mock import patch, MagicMock
from core.server_registry import ServerRegistry
from core.health_monitor import HealthMonitor
from core.load_balancer import LoadBalancer
from database.db import init_db, query_db
import tempfile
import os

@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    init_db(path)
    # Configure shorter recovery delay for fast testing
    from database.db import execute_db
    execute_db("UPDATE system_config SET value = '0.2' WHERE key = 'recovery_delay';", db_path=path)
    execute_db("UPDATE system_config SET value = '2' WHERE key = 'failure_threshold';", db_path=path)
    execute_db("UPDATE system_config SET value = '2' WHERE key = 'recovery_threshold';", db_path=path)
    yield path
    try:
        os.remove(path)
    except Exception:
        pass

def test_full_fault_isolation_and_automatic_recovery(temp_db):
    lb = LoadBalancer(db_path=temp_db)
    registry = lb.registry
    monitor = lb.health_monitor

    # 1. Initial state: All 3 backends eligible
    eligible = registry.get_eligible_servers()
    assert len(eligible) == 3

    # 2. Simulate Backend Alpha failing repeatedly (returns 500 error)
    srv_a = registry.get_server("srv-backend-a")
    fail_mock = MagicMock()
    fail_mock.status_code = 500

    with patch("requests.get", return_value=fail_mock):
        monitor.probe_server(srv_a)
        monitor.probe_server(srv_a)

    # Circuit should now be OPEN for Alpha
    srv_a_updated = registry.get_server("srv-backend-a")
    assert srv_a_updated["circuit_state"] == "OPEN"

    # 3. Failover Verification: Routing excludes Alpha and routes ONLY to Beta and Gamma
    eligible = registry.get_eligible_servers()
    eligible_ids = {s["id"] for s in eligible}
    assert "srv-backend-a" not in eligible_ids
    assert eligible_ids == {"srv-backend-b", "srv-backend-c"}

    # 4. Wait for recovery delay (0.2s)
    time.sleep(0.3)
    cb_a = registry.get_circuit_breaker("srv-backend-a")
    assert cb_a.state == "HALF-OPEN"

    # In HALF-OPEN, Alpha is STILL NOT eligible for normal client traffic
    assert "srv-backend-a" not in {s["id"] for s in registry.get_eligible_servers()}

    # 5. Recovery probes succeed (Backend Alpha has recovered)
    success_mock = MagicMock()
    success_mock.status_code = 200

    with patch("requests.get", return_value=success_mock):
        # 1st probe
        monitor.probe_server(srv_a)
        assert cb_a.state == "HALF-OPEN"
        # 2nd probe reaches recovery threshold -> restores to CLOSED!
        monitor.probe_server(srv_a)
        assert cb_a.state == "CLOSED"

    # 6. Backend Alpha is now automatically restored to eligible routing pool!
    eligible_after = registry.get_eligible_servers()
    eligible_after_ids = {s["id"] for s in eligible_after}
    assert "srv-backend-a" in eligible_after_ids
    assert len(eligible_after) == 3

    # 7. Verify transition history was recorded in SQLite
    transitions = query_db("SELECT * FROM circuit_transitions WHERE server_id = 'srv-backend-a';", db_path=temp_db)
    assert len(transitions) >= 2
    # Verify transitions to OPEN and CLOSED exist
    to_states = [t["to_state"] for t in transitions]
    assert "OPEN" in to_states
    assert "CLOSED" in to_states
