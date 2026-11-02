import time
import pytest
from core.circuit_breaker import CircuitBreaker, CircuitState

def test_circuit_initial_closed_state():
    cb = CircuitBreaker(server_id="test-srv", failure_threshold=3, recovery_threshold=2, recovery_delay=0.5)
    assert cb.state == CircuitState.CLOSED
    assert cb.is_available_for_traffic() is True
    assert cb.consecutive_failures == 0

def test_circuit_trips_to_open_after_threshold():
    transitions = []
    def callback(s_id, from_s, to_s, reason, count):
        transitions.append((from_s, to_s, count))

    cb = CircuitBreaker(server_id="test-srv", failure_threshold=3, on_state_change=callback)

    # 1st failure: still CLOSED
    cb.record_failure("Error 1")
    assert cb.state == CircuitState.CLOSED
    assert cb.is_available_for_traffic() is True

    # 2nd failure: still CLOSED
    cb.record_failure("Error 2")
    assert cb.state == CircuitState.CLOSED

    # 3rd failure: trips to OPEN!
    cb.record_failure("Error 3")
    assert cb.state == CircuitState.OPEN
    assert cb.is_available_for_traffic() is False
    assert len(transitions) == 1
    assert transitions[0] == ("CLOSED", "OPEN", 3)

def test_circuit_half_open_recovery_and_reopen():
    # Fast recovery delay for test: 0.1s
    cb = CircuitBreaker(server_id="test-srv", failure_threshold=2, recovery_threshold=2, recovery_delay=0.1)

    # Trip to OPEN
    cb.record_failure("Err 1")
    cb.record_failure("Err 2")
    assert cb.state == CircuitState.OPEN

    # Wait for recovery delay
    time.sleep(0.15)

    # State property triggers check_half_open_transition
    assert cb.state == CircuitState.HALF_OPEN
    # Normal client traffic is not allowed in HALF-OPEN (probes only!)
    assert cb.is_available_for_traffic() is False

    # Probe failure in HALF-OPEN immediately trips back to OPEN
    cb.record_failure("Probe failed in HALF-OPEN", is_probe=True)
    assert cb.state == CircuitState.OPEN

def test_circuit_successful_recovery_to_closed():
    cb = CircuitBreaker(server_id="test-srv", failure_threshold=2, recovery_threshold=2, recovery_delay=0.1)

    cb.record_failure("Err 1")
    cb.record_failure("Err 2")
    assert cb.state == CircuitState.OPEN

    time.sleep(0.15)
    assert cb.state == CircuitState.HALF_OPEN

    # 1st successful probe
    cb.record_success(is_probe=True)
    assert cb.state == CircuitState.HALF_OPEN
    assert cb.consecutive_successes == 1

    # 2nd successful probe reaches threshold -> CLOSED!
    cb.record_success(is_probe=True)
    assert cb.state == CircuitState.CLOSED
    assert cb.is_available_for_traffic() is True
    assert cb.consecutive_failures == 0

def test_circuit_manual_trip_and_reset():
    cb = CircuitBreaker(server_id="test-srv")
    assert cb.state == CircuitState.CLOSED

    cb.manual_trip("Admin test trip")
    assert cb.state == CircuitState.OPEN
    assert cb.is_available_for_traffic() is False

    cb.manual_reset()
    assert cb.state == CircuitState.CLOSED
    assert cb.is_available_for_traffic() is True
