import time
import threading
from enum import Enum
from typing import Optional, Callable
from datetime import datetime

class CircuitState(str, Enum):
    CLOSED = "CLOSED"         # Normal operation: traffic allowed
    OPEN = "OPEN"             # Isolated: no normal traffic
    HALF_OPEN = "HALF-OPEN"   # Probing: test if service has recovered

class CircuitBreaker:
    """
    Per-backend Circuit Breaker managing states: CLOSED, OPEN, HALF-OPEN.
    Thread-safe and supports transition callbacks for SQLite logging.
    """
    def __init__(
        self,
        server_id: str,
        failure_threshold: int = 3,
        recovery_threshold: int = 2,
        recovery_delay: float = 5.0,
        on_state_change: Optional[Callable[[str, str, str, str, int], None]] = None
    ):
        self.server_id = server_id
        self.failure_threshold = failure_threshold
        self.recovery_threshold = recovery_threshold
        self.recovery_delay = recovery_delay
        self.on_state_change = on_state_change

        self._state = CircuitState.CLOSED
        self._consecutive_failures = 0
        self._consecutive_successes = 0
        self._last_state_change = time.time()
        self._opened_at: Optional[float] = None
        self._lock = threading.Lock()

    @property
    def state(self) -> CircuitState:
        with self._lock:
            self._check_half_open_transition()
            return self._state

    @property
    def consecutive_failures(self) -> int:
        with self._lock:
            return self._consecutive_failures

    @property
    def consecutive_successes(self) -> int:
        with self._lock:
            return self._consecutive_successes

    def is_available_for_traffic(self) -> bool:
        """Determines if the backend can receive normal client proxy traffic."""
        with self._lock:
            self._check_half_open_transition()
            # Only CLOSED state receives normal user traffic.
            # HALF-OPEN is reserved for health check probes to avoid flooding recovering servers.
            return self._state == CircuitState.CLOSED

    def record_success(self, is_probe: bool = False):
        """Records a successful response (from probe or request)."""
        with self._lock:
            self._check_half_open_transition()
            self._consecutive_failures = 0

            if self._state == CircuitState.HALF_OPEN:
                self._consecutive_successes += 1
                if self._consecutive_successes >= self.recovery_threshold:
                    self._transition_to(
                        CircuitState.CLOSED,
                        f"Recovered: {self._consecutive_successes} consecutive successful probes in HALF-OPEN"
                    )
            elif self._state == CircuitState.CLOSED:
                self._consecutive_successes += 1

    def record_failure(self, reason: str = "Failure detected", is_probe: bool = False):
        """Records a failure (connection refused, timeout, or 5xx)."""
        with self._lock:
            self._check_half_open_transition()
            self._consecutive_failures += 1
            self._consecutive_successes = 0

            if self._state == CircuitState.CLOSED:
                if self._consecutive_failures >= self.failure_threshold:
                    self._transition_to(
                        CircuitState.OPEN,
                        f"Failure threshold reached: {self._consecutive_failures}/{self.failure_threshold} failures ({reason})"
                    )
            elif self._state == CircuitState.HALF_OPEN:
                # Any failure during HALF-OPEN immediately re-opens the circuit
                self._transition_to(
                    CircuitState.OPEN,
                    f"Probe failed in HALF-OPEN state: {reason}"
                )

    def manual_reset(self):
        """Manually forces the circuit breaker back to CLOSED."""
        with self._lock:
            self._transition_to(CircuitState.CLOSED, "Manual administrator reset")
            self._consecutive_failures = 0
            self._consecutive_successes = 0

    def manual_trip(self, reason: str = "Manual trip"):
        """Manually trips the circuit breaker to OPEN."""
        with self._lock:
            self._transition_to(CircuitState.OPEN, reason)

    def _check_half_open_transition(self):
        """If OPEN and recovery delay has elapsed, transition to HALF-OPEN."""
        if self._state == CircuitState.OPEN and self._opened_at is not None:
            elapsed = time.time() - self._opened_at
            if elapsed >= self.recovery_delay:
                self._transition_to(
                    CircuitState.HALF_OPEN,
                    f"Recovery delay of {self.recovery_delay:.1f}s elapsed, testing recovery with probes"
                )

    def _transition_to(self, new_state: CircuitState, reason: str):
        old_state = self._state
        if old_state == new_state:
            return

        self._state = new_state
        self._last_state_change = time.time()

        if new_state == CircuitState.OPEN:
            self._opened_at = time.time()
            self._consecutive_successes = 0
        elif new_state == CircuitState.HALF_OPEN:
            self._consecutive_successes = 0
        elif new_state == CircuitState.CLOSED:
            self._opened_at = None
            self._consecutive_failures = 0

        # Trigger notification callback outside internal state logic
        if self.on_state_change:
            try:
                self.on_state_change(
                    self.server_id,
                    old_state.value,
                    new_state.value,
                    reason,
                    self._consecutive_failures
                )
            except Exception as e:
                print(f"[CircuitBreaker Callback Error] {e}")

    def get_status_dict(self) -> dict:
        with self._lock:
            self._check_half_open_transition()
            time_in_state = time.time() - self._last_state_change
            time_until_probe = 0.0
            if self._state == CircuitState.OPEN and self._opened_at is not None:
                time_until_probe = max(0.0, self.recovery_delay - (time.time() - self._opened_at))

            return {
                "server_id": self.server_id,
                "state": self._state.value,
                "consecutive_failures": self._consecutive_failures,
                "consecutive_successes": self._consecutive_successes,
                "failure_threshold": self.failure_threshold,
                "recovery_threshold": self.recovery_threshold,
                "recovery_delay": self.recovery_delay,
                "time_in_state_seconds": round(time_in_state, 1),
                "time_until_probe_seconds": round(time_until_probe, 1),
                "is_available_for_traffic": self._state == CircuitState.CLOSED
            }
