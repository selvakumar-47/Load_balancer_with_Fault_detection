import time
import os
import sys
import threading
from datetime import datetime
from flask import Flask, request, jsonify

def create_backend_app(name: str, port: int) -> Flask:
    app = Flask(name)

    state = {
        "name": name,
        "port": port,
        "requests_served": 0,
        "status": "UP",           # "UP", "DOWN", "ERROR", "SLOW"
        "delay_ms": 0,
        "error_code": 0,
        "started_at": datetime.now().isoformat()
    }
    state_lock = threading.Lock()

    @app.before_request
    def handle_injected_faults():
        # Do not apply faults to the fault management endpoints themselves!
        if request.path.startswith("/fault"):
            return None

        with state_lock:
            delay = state["delay_ms"]
            error = state["error_code"]
            status = state["status"]

        if delay > 0:
            time.sleep(delay / 1000.0)

        if status == "DOWN":
            return jsonify({
                "error": "Service Unavailable (Simulated Crash)",
                "backend": name,
                "status": "DOWN"
            }), 503

        if error and error >= 400:
            return jsonify({
                "error": f"Simulated HTTP {error} Failure",
                "backend": name,
                "code": error
            }), error

        return None

    @app.route("/", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
    def index():
        with state_lock:
            state["requests_served"] += 1
            current_count = state["requests_served"]
            curr_status = state["status"]
            curr_delay = state["delay_ms"]

        return jsonify({
            "message": f"Response from {name}",
            "backend": name,
            "port": port,
            "requests_served": current_count,
            "status": curr_status,
            "delay_ms": curr_delay,
            "method": request.method,
            "headers_received": {k: v for k, v in request.headers.items() if not k.startswith("X-Internal")},
            "timestamp": datetime.now().isoformat()
        }), 200

    @app.route("/api/echo", methods=["GET", "POST"])
    def echo():
        with state_lock:
            state["requests_served"] += 1
            current_count = state["requests_served"]

        data = request.get_json(silent=True) or request.form.to_dict() or request.data.decode('utf-8', errors='ignore')
        return jsonify({
            "backend": name,
            "port": port,
            "requests_served": current_count,
            "echo_data": data,
            "query_params": request.args.to_dict(),
            "timestamp": datetime.now().isoformat()
        }), 200

    @app.route("/health", methods=["GET"])
    def health():
        with state_lock:
            status = state["status"]
            delay = state["delay_ms"]
            error = state["error_code"]
            count = state["requests_served"]

        # Health endpoint responds according to injected faults
        if delay > 0:
            time.sleep(delay / 1000.0)

        if status == "DOWN":
            return jsonify({
                "status": "DOWN",
                "backend": name,
                "message": "Backend simulated as crashed or down"
            }), 503

        if error and error >= 400:
            return jsonify({
                "status": "ERROR",
                "backend": name,
                "code": error,
                "message": f"Backend simulated failure {error}"
            }), error

        return jsonify({
            "status": "UP",
            "backend": name,
            "port": port,
            "healthy": True,
            "requests_served": count,
            "timestamp": datetime.now().isoformat()
        }), 200

    # Fault Injection Control APIs
    @app.route("/fault/status", methods=["GET"])
    def fault_status():
        with state_lock:
            return jsonify(dict(state)), 200

    @app.route("/fault/delay", methods=["POST"])
    def inject_delay():
        data = request.get_json(silent=True) or {}
        ms = int(data.get("ms", request.args.get("ms", 3000)))
        with state_lock:
            state["delay_ms"] = ms
            state["status"] = "SLOW" if ms > 0 else "UP"
        return jsonify({
            "message": f"Injected response delay of {ms}ms on {name}",
            "state": dict(state)
        }), 200

    @app.route("/fault/error", methods=["POST"])
    def inject_error():
        data = request.get_json(silent=True) or {}
        code = int(data.get("code", request.args.get("code", 500)))
        with state_lock:
            state["error_code"] = code
            state["status"] = "ERROR"
        return jsonify({
            "message": f"Injected HTTP {code} error on {name}",
            "state": dict(state)
        }), 200

    @app.route("/fault/crash", methods=["POST"])
    def inject_crash():
        with state_lock:
            state["status"] = "DOWN"
            state["error_code"] = 503
        return jsonify({
            "message": f"Backend {name} marked as crashed (DOWN)",
            "state": dict(state)
        }), 200

    @app.route("/fault/recover", methods=["POST"])
    def recover():
        with state_lock:
            state["status"] = "UP"
            state["delay_ms"] = 0
            state["error_code"] = 0
        return jsonify({
            "message": f"Backend {name} recovered to healthy normal operation",
            "state": dict(state)
        }), 200

    return app
