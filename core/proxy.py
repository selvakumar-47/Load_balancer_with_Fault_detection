import time
import uuid
import requests
from flask import Request, Response, jsonify, make_response
from typing import Optional, Dict, Any
from core.server_registry import ServerRegistry
from database.db import execute_db
from config import Config

# Hop-by-hop headers as per RFC 7230 / RFC 2616
HOP_BY_HOP_HEADERS = {
    'connection',
    'keep-alive',
    'proxy-authenticate',
    'proxy-authorization',
    'te',
    'trailers',
    'transfer-encoding',
    'upgrade',
    'content-length'  # We let requests and Flask recompute this
}

class ReverseProxy:
    """
    Reverse HTTP Proxy forwarding client requests to selected backends.
    Handles hop-by-hop header removal, connection tracking, timeouts, and metrics logging.
    """
    def __init__(self, registry: ServerRegistry, db_path: Optional[str] = None):
        self.registry = registry
        self.db_path = db_path or Config.DATABASE_PATH
        self.timeout = Config.REQUEST_TIMEOUT_SECONDS

    def filter_headers(self, headers: Dict[str, str]) -> Dict[str, str]:
        """Strips hop-by-hop headers."""
        return {
            k: v for k, v in headers.items()
            if k.lower() not in HOP_BY_HOP_HEADERS and not k.lower().startswith('sec-')
        }

    def forward_request(
        self,
        flask_req: Request,
        subpath: str,
        selected_backend: Optional[Dict[str, Any]],
        algorithm_name: str,
        experiment_id: Optional[str] = None
    ) -> Response:
        """Forwards an incoming client request to the selected backend server."""
        req_id = f"req-{uuid.uuid4().hex[:10]}"
        client_ip = flask_req.headers.get("X-Forwarded-For", flask_req.remote_addr or "127.0.0.1")
        target_path = "/" + subpath.lstrip("/")

        if not selected_backend:
            # 503: No eligible backend available
            self._log_request(
                request_id=req_id,
                method=flask_req.method,
                path=target_path,
                backend_id=None,
                backend_url=None,
                algo=algorithm_name,
                status_code=503,
                latency_ms=0.0,
                is_success=False,
                error_msg="No eligible backend servers available (all down or open circuit)",
                client_ip=client_ip,
                experiment_id=experiment_id
            )
            return make_response(jsonify({
                "error": "Service Unavailable",
                "message": "All backend servers are currently offline, degraded, or circuit-broken.",
                "code": 503,
                "request_id": req_id
            }), 503)

        backend_id = selected_backend["id"]
        backend_base_url = selected_backend["url"].rstrip("/")
        destination_url = f"{backend_base_url}{target_path}"

        # Increment active connection for Least Connections algorithm
        self.registry.increment_active(backend_id)
        start_time = time.time()
        status_code = 502
        is_success = False
        error_msg = None
        backend_response = None

        try:
            # Prepare headers
            forward_headers = self.filter_headers(dict(flask_req.headers))
            forward_headers["X-Forwarded-For"] = client_ip
            forward_headers["X-Request-ID"] = req_id
            forward_headers["X-Forwarded-Host"] = flask_req.host

            # Forward request using requests
            resp = requests.request(
                method=flask_req.method,
                url=destination_url,
                headers=forward_headers,
                params=flask_req.args,
                data=flask_req.get_data(),
                timeout=self.timeout,
                allow_redirects=False
            )
            latency_ms = (time.time() - start_time) * 1000.0
            status_code = resp.status_code
            is_success = (status_code < 500)
            if not is_success:
                error_msg = f"Backend returned HTTP {status_code}"

            # Prepare client response
            resp_headers = self.filter_headers(dict(resp.headers))
            resp_headers["X-Handled-By"] = backend_id
            resp_headers["X-Load-Balancer-Algo"] = algorithm_name
            resp_headers["X-Response-Time-Ms"] = str(round(latency_ms, 2))

            backend_response = Response(
                response=resp.content,
                status=resp.status_code,
                headers=resp_headers
            )

        except requests.exceptions.Timeout:
            latency_ms = (time.time() - start_time) * 1000.0
            status_code = 504
            is_success = False
            error_msg = f"Gateway Timeout (> {self.timeout}s to {backend_id})"
            backend_response = make_response(jsonify({
                "error": "Gateway Timeout",
                "message": f"Backend server {backend_id} timed out after {self.timeout} seconds.",
                "code": 504,
                "request_id": req_id
            }), 504)

        except requests.exceptions.ConnectionError:
            latency_ms = (time.time() - start_time) * 1000.0
            status_code = 502
            is_success = False
            error_msg = f"Connection Refused to {backend_id}"
            backend_response = make_response(jsonify({
                "error": "Bad Gateway",
                "message": f"Could not connect to backend server {backend_id}.",
                "code": 502,
                "request_id": req_id
            }), 502)

        except Exception as ex:
            latency_ms = (time.time() - start_time) * 1000.0
            status_code = 500
            is_success = False
            error_msg = str(ex)
            backend_response = make_response(jsonify({
                "error": "Proxy Error",
                "message": f"Internal proxy error forwarding to {backend_id}: {str(ex)}",
                "code": 500,
                "request_id": req_id
            }), 500)

        finally:
            # Always decrement active connection
            self.registry.decrement_active(backend_id)
            # Record server outcome for registry & circuit breaker
            self.registry.record_request_outcome(backend_id, is_success, latency_ms)
            # Log to request_logs table
            self._log_request(
                request_id=req_id,
                method=flask_req.method,
                path=target_path,
                backend_id=backend_id,
                backend_url=backend_base_url,
                algo=algorithm_name,
                status_code=status_code,
                latency_ms=latency_ms,
                is_success=is_success,
                error_msg=error_msg,
                client_ip=client_ip,
                experiment_id=experiment_id
            )

        return backend_response

    def _log_request(
        self,
        request_id: str,
        method: str,
        path: str,
        backend_id: Optional[str],
        backend_url: Optional[str],
        algo: str,
        status_code: int,
        latency_ms: float,
        is_success: bool,
        error_msg: Optional[str],
        client_ip: str,
        experiment_id: Optional[str]
    ):
        """Persists request routing event into SQLite."""
        try:
            execute_db(
                """INSERT INTO request_logs
                   (request_id, method, path, selected_backend_id, selected_backend_url,
                    algorithm_used, status_code, response_time_ms, is_success, error_message, client_ip, experiment_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);""",
                (
                    request_id,
                    method,
                    path,
                    backend_id,
                    backend_url,
                    algo,
                    status_code,
                    round(latency_ms, 2),
                    1 if is_success else 0,
                    error_msg,
                    client_ip,
                    experiment_id
                ),
                db_path=self.db_path
            )
        except Exception as e:
            print(f"[Proxy Log Error] {e}")
