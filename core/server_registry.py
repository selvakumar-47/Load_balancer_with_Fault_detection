import threading
import time
from typing import Dict, List, Optional, Any
from urllib.parse import urlparse
from core.circuit_breaker import CircuitBreaker, CircuitState
from database.db import query_db, execute_db
from config import Config

class ServerRegistry:
    """
    In-memory, thread-safe server registry backed by SQLite.
    Maintains per-backend circuit breakers, active connections, and health state.
    """
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or Config.DATABASE_PATH
        self._lock = threading.RLock()
        self._servers: Dict[str, Dict[str, Any]] = {}
        self._circuit_breakers: Dict[str, CircuitBreaker] = {}
        self._active_connections: Dict[str, int] = {}
        self.reload_from_db()

    def reload_from_db(self):
        """Loads all servers and configuration from SQLite into memory."""
        with self._lock:
            # Fetch config for circuit breaker thresholds
            cfg_rows = query_db("SELECT key, value FROM system_config;", db_path=self.db_path)
            configs = {r["key"]: r["value"] for r in cfg_rows}
            failure_threshold = int(configs.get("failure_threshold", Config.FAILURE_THRESHOLD))
            recovery_threshold = int(configs.get("recovery_threshold", Config.RECOVERY_THRESHOLD))
            recovery_delay = float(configs.get("recovery_delay", Config.RECOVERY_DELAY_SECONDS))

            rows = query_db("SELECT * FROM servers;", db_path=self.db_path)
            for row in rows:
                s_id = row["id"]
                self._servers[s_id] = dict(row)
                if s_id not in self._active_connections:
                    self._active_connections[s_id] = 0

                # Initialize or update circuit breaker
                if s_id not in self._circuit_breakers:
                    cb = CircuitBreaker(
                        server_id=s_id,
                        failure_threshold=failure_threshold,
                        recovery_threshold=recovery_threshold,
                        recovery_delay=recovery_delay,
                        on_state_change=self._on_circuit_state_change
                    )
                    # Sync persisted state if it was OPEN or HALF-OPEN
                    if row["circuit_state"] == "OPEN":
                        cb.manual_trip("Restored from persisted state")
                    self._circuit_breakers[s_id] = cb
                else:
                    # Update parameters in case settings changed
                    cb = self._circuit_breakers[s_id]
                    cb.failure_threshold = failure_threshold
                    cb.recovery_threshold = recovery_threshold
                    cb.recovery_delay = recovery_delay

    def _on_circuit_state_change(self, server_id: str, from_state: str, to_state: str, reason: str, failure_count: int):
        """Callback fired when a circuit breaker changes state. Persists transition to SQLite."""
        try:
            # 1. Update servers table
            execute_db(
                """UPDATE servers
                   SET circuit_state = ?,
                       last_state_change = datetime('now', 'localtime')
                   WHERE id = ?;""",
                (to_state, server_id),
                db_path=self.db_path
            )

            # 2. Insert into circuit_transitions
            execute_db(
                """INSERT INTO circuit_transitions (server_id, from_state, to_state, reason, failure_count)
                   VALUES (?, ?, ?, ?, ?);""",
                (server_id, from_state, to_state, reason, failure_count),
                db_path=self.db_path
            )

            # 3. If transitioning to OPEN, update or record fault detection in fault_events if an active fault was injected
            if to_state == "OPEN":
                # Check if there is an active fault event waiting for detection
                now_str = time.strftime('%Y-%m-%d %H:%M:%S')
                active_fault = query_db(
                    """SELECT * FROM fault_events
                       WHERE server_id = ? AND status = 'ACTIVE'
                       ORDER BY id DESC LIMIT 1;""",
                    (server_id,),
                    one=True,
                    db_path=self.db_path
                )
                if active_fault:
                    # Calculate detection latency
                    injected_time = time.mktime(time.strptime(active_fault["injected_at"], '%Y-%m-%d %H:%M:%S'))
                    det_latency = max(0.0, (time.time() - injected_time) * 1000.0)
                    execute_db(
                        """UPDATE fault_events
                           SET detected_at = datetime('now', 'localtime'),
                               detection_latency_ms = ?,
                               status = 'DETECTED'
                           WHERE id = ?;""",
                        (round(det_latency, 2), active_fault["id"]),
                        db_path=self.db_path
                    )

            # 4. If transitioning to CLOSED, record recovery completion in fault_events
            elif to_state == "CLOSED":
                now_str = time.strftime('%Y-%m-%d %H:%M:%S')
                detected_fault = query_db(
                    """SELECT * FROM fault_events
                       WHERE server_id = ? AND status IN ('DETECTED', 'RECOVERING')
                       ORDER BY id DESC LIMIT 1;""",
                    (server_id,),
                    one=True,
                    db_path=self.db_path
                )
                if detected_fault:
                    injected_time = time.mktime(time.strptime(detected_fault["injected_at"], '%Y-%m-%d %H:%M:%S'))
                    rec_duration = max(0.0, (time.time() - injected_time) * 1000.0)
                    execute_db(
                        """UPDATE fault_events
                           SET recovered_at = datetime('now', 'localtime'),
                               recovery_duration_ms = ?,
                               status = 'RESOLVED'
                           WHERE id = ?;""",
                        (round(rec_duration, 2), detected_fault["id"]),
                        db_path=self.db_path
                    )
        except Exception as e:
            print(f"[ServerRegistry SQLite Error on Circuit Transition] {e}")

    def validate_url(self, url: str) -> bool:
        """Security validation: ensure URL belongs to allowed hosts/ports and has valid scheme."""
        try:
            parsed = urlparse(url)
            if parsed.scheme not in ("http", "https"):
                return False
            host = parsed.hostname
            if host not in Config.ALLOWED_HOSTS:
                return False
            port = parsed.port or (80 if parsed.scheme == "http" else 443)
            # Allow common dev ports and configured allowed ports
            if port not in Config.ALLOWED_PORTS and not (8000 <= port <= 8010 or 5000 <= port <= 5010):
                return False
            return True
        except Exception:
            return False

    def register_server(self, server_id: str, name: str, url: str, weight: int = 1) -> Dict[str, Any]:
        """Registers a new backend server."""
        if not self.validate_url(url):
            raise ValueError(f"Unsafe or invalid destination URL: {url}. Allowed hosts: {Config.ALLOWED_HOSTS}")

        with self._lock:
            # Check duplicate
            existing = query_db("SELECT id FROM servers WHERE id = ? OR url = ?;", (server_id, url), one=True, db_path=self.db_path)
            if existing:
                raise ValueError(f"Server with id '{server_id}' or url '{url}' already registered.")

            execute_db(
                """INSERT INTO servers (id, name, url, weight, is_enabled, status, circuit_state)
                   VALUES (?, ?, ?, ?, 1, 'HEALTHY', 'CLOSED');""",
                (server_id, name, url, weight),
                db_path=self.db_path
            )
            self.reload_from_db()
            return self.get_server(server_id)

    def update_server(self, server_id: str, name: Optional[str] = None, url: Optional[str] = None,
                      weight: Optional[int] = None, is_enabled: Optional[bool] = None) -> Dict[str, Any]:
        """Updates backend server configuration."""
        with self._lock:
            srv = self.get_server(server_id)
            if not srv:
                raise ValueError(f"Server {server_id} not found.")

            new_name = name if name is not None else srv["name"]
            new_url = url if url is not None else srv["url"]
            new_weight = weight if weight is not None else srv["weight"]
            new_enabled = int(is_enabled) if is_enabled is not None else srv["is_enabled"]

            if url and not self.validate_url(url):
                raise ValueError(f"Unsafe destination URL: {url}")

            execute_db(
                """UPDATE servers
                   SET name = ?, url = ?, weight = ?, is_enabled = ?
                   WHERE id = ?;""",
                (new_name, new_url, new_weight, new_enabled, server_id),
                db_path=self.db_path
            )
            self.reload_from_db()
            return self.get_server(server_id)

    def delete_server(self, server_id: str):
        """Removes a backend server from the registry and database."""
        with self._lock:
            execute_db("DELETE FROM servers WHERE id = ?;", (server_id,), db_path=self.db_path)
            self._servers.pop(server_id, None)
            self._circuit_breakers.pop(server_id, None)
            self._active_connections.pop(server_id, None)

    def get_server(self, server_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            srv = self._servers.get(server_id)
            if not srv:
                return None
            cb = self._circuit_breakers.get(server_id)
            result = dict(srv)
            result["active_connections"] = self._active_connections.get(server_id, 0)
            if cb:
                result["circuit_state"] = cb.state.value
                result["consecutive_failures"] = cb.consecutive_failures
                result["consecutive_successes"] = cb.consecutive_successes
                result["circuit_info"] = cb.get_status_dict()
            return result

    def get_all_servers(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [self.get_server(s_id) for s_id in self._servers.keys()]

    def get_eligible_servers(self) -> List[Dict[str, Any]]:
        """
        Returns backends that are:
        1. Enabled (is_enabled == 1)
        2. Circuit Breaker CLOSED (is_available_for_traffic == True)
        """
        with self._lock:
            eligible = []
            for s_id in self._servers.keys():
                srv = self.get_server(s_id)
                if not srv or not srv.get("is_enabled"):
                    continue
                cb = self._circuit_breakers.get(s_id)
                if not cb or not cb.is_available_for_traffic():
                    continue
                eligible.append(srv)
            return eligible

    def get_circuit_breaker(self, server_id: str) -> Optional[CircuitBreaker]:
        with self._lock:
            return self._circuit_breakers.get(server_id)

    def increment_active(self, server_id: str):
        with self._lock:
            self._active_connections[server_id] = self._active_connections.get(server_id, 0) + 1

    def decrement_active(self, server_id: str):
        with self._lock:
            current = self._active_connections.get(server_id, 0)
            self._active_connections[server_id] = max(0, current - 1)

    def record_request_outcome(self, server_id: str, is_success: bool, latency_ms: float):
        """Updates in-memory and database stats after a proxied request."""
        with self._lock:
            srv = self._servers.get(server_id)
            if not srv:
                return

            cb = self._circuit_breakers.get(server_id)
            if cb:
                if is_success:
                    cb.record_success(is_probe=False)
                else:
                    cb.record_failure("Proxy request failure/timeout", is_probe=False)

            # Update database metrics
            execute_db(
                """UPDATE servers
                   SET total_requests = total_requests + 1,
                       successful_requests = successful_requests + ?,
                       failed_requests = failed_requests + ?,
                       last_response_time_ms = ?
                   WHERE id = ?;""",
                (1 if is_success else 0, 0 if is_success else 1, round(latency_ms, 2), server_id),
                db_path=self.db_path
            )
            # Update cache
            srv["total_requests"] = srv.get("total_requests", 0) + 1
            if is_success:
                srv["successful_requests"] = srv.get("successful_requests", 0) + 1
            else:
                srv["failed_requests"] = srv.get("failed_requests", 0) + 1
            srv["last_response_time_ms"] = round(latency_ms, 2)

    def record_health_check(self, server_id: str, is_healthy: bool, response_time_ms: float,
                            status_code: Optional[int], error_msg: Optional[str] = None):
        """Records a periodic background health probe."""
        with self._lock:
            srv = self._servers.get(server_id)
            if not srv:
                return

            cb = self._circuit_breakers.get(server_id)
            if cb:
                if is_healthy:
                    cb.record_success(is_probe=True)
                else:
                    reason = error_msg or f"Health check returned HTTP {status_code}"
                    cb.record_failure(reason, is_probe=True)

            # Health status classification based on health & circuit breaker state
            if cb:
                if cb.state == CircuitState.OPEN:
                    status_str = "UNHEALTHY"
                elif cb.state == CircuitState.HALF_OPEN or cb.consecutive_failures > 0:
                    status_str = "DEGRADED"
                else:
                    status_str = "HEALTHY"
            else:
                status_str = "HEALTHY" if is_healthy else "UNHEALTHY"

            # Persist to health_history
            execute_db(
                """INSERT INTO health_history (server_id, status, status_code, response_time_ms, error_message)
                   VALUES (?, ?, ?, ?, ?);""",
                (server_id, "UP" if is_healthy else "DOWN", status_code, round(response_time_ms, 2), error_msg),
                db_path=self.db_path
            )

            # Update servers table
            execute_db(
                """UPDATE servers
                   SET status = ?,
                       last_health_check = datetime('now', 'localtime'),
                       consecutive_failures = ?,
                       consecutive_successes = ?,
                       last_response_time_ms = CASE WHEN ? > 0 THEN ? ELSE last_response_time_ms END
                   WHERE id = ?;""",
                (
                    status_str,
                    cb.consecutive_failures if cb else 0,
                    cb.consecutive_successes if cb else 0,
                    response_time_ms,
                    round(response_time_ms, 2),
                    server_id
                ),
                db_path=self.db_path
            )

            srv["status"] = status_str
            srv["last_health_check"] = time.strftime('%Y-%m-%d %H:%M:%S')
