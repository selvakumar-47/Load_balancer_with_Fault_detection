from flask import Blueprint, request, jsonify
from database.db import query_db, execute_db
from core.algorithms import AlgorithmFactory

def create_settings_blueprint(load_balancer):
    bp = Blueprint("settings", __name__, url_prefix="/api")

    @bp.route("/settings", methods=["GET"])
    def get_settings():
        """Returns all configuration settings."""
        rows = query_db("SELECT key, value, description, updated_at FROM system_config;", db_path=load_balancer.db_path)
        configs = {r["key"]: r["value"] for r in rows}
        return jsonify({
            "settings": configs,
            "descriptions": {r["key"]: r["description"] for r in rows},
            "available_algorithms": AlgorithmFactory.list_available()
        }), 200

    @bp.route("/settings", methods=["POST"])
    def update_settings():
        """Updates system configuration settings."""
        data = request.get_json(silent=True) or {}
        allowed_keys = {
            "health_check_interval",
            "health_check_timeout",
            "request_timeout",
            "failure_threshold",
            "recovery_threshold",
            "recovery_delay",
            "active_algorithm"
        }

        updated = []
        for key, val in data.items():
            if key in allowed_keys:
                execute_db(
                    """UPDATE system_config 
                       SET value = ?, updated_at = datetime('now', 'localtime') 
                       WHERE key = ?;""",
                    (str(val), key),
                    db_path=load_balancer.db_path
                )
                updated.append(key)

        # Apply settings live to memory components
        if "active_algorithm" in data:
            load_balancer.set_algorithm(str(data["active_algorithm"]))

        if "health_check_interval" in data:
            load_balancer.health_monitor.interval = float(data["health_check_interval"])

        if "health_check_timeout" in data:
            load_balancer.health_monitor.timeout = float(data["health_check_timeout"])

        if "request_timeout" in data:
            load_balancer.proxy.timeout = float(data["request_timeout"])

        # Reload registry circuit breaker thresholds
        load_balancer.registry.reload_from_db()

        return jsonify({"message": f"Updated settings: {', '.join(updated)}", "updated_keys": updated}), 200

    @bp.route("/algorithm", methods=["POST"])
    def set_algorithm():
        """Switches the active load balancing algorithm."""
        data = request.get_json(silent=True) or {}
        algo = data.get("algorithm")
        if not algo:
            return jsonify({"error": "algorithm field is required."}), 400

        try:
            active_algo = load_balancer.set_algorithm(algo)
            return jsonify({"message": f"Active algorithm changed to {active_algo}.", "algorithm": active_algo}), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 400

    @bp.route("/algorithms", methods=["GET"])
    def list_algorithms():
        """Lists available load balancing algorithms."""
        return jsonify({
            "active": load_balancer.get_algorithm_name(),
            "available": AlgorithmFactory.list_available()
        }), 200

    return bp
