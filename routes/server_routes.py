from flask import Blueprint, request, jsonify

def create_server_blueprint(load_balancer):
    bp = Blueprint("servers", __name__, url_prefix="/api/servers")
    registry = load_balancer.registry

    @bp.route("", methods=["GET"])
    def list_servers():
        """Lists all registered backend servers with live metrics and circuit state."""
        servers = registry.get_all_servers()
        return jsonify({"servers": servers, "count": len(servers)}), 200

    @bp.route("", methods=["POST"])
    def add_server():
        """Registers a new backend server."""
        data = request.get_json(silent=True) or {}
        server_id = data.get("id", "").strip()
        name = data.get("name", "").strip()
        url = data.get("url", "").strip()
        weight = int(data.get("weight", 1))

        if not server_id or not name or not url:
            return jsonify({"error": "Missing required fields: id, name, and url are required."}), 400

        try:
            srv = registry.register_server(server_id, name, url, weight)
            return jsonify({"message": f"Server {server_id} registered successfully.", "server": srv}), 201
        except ValueError as ve:
            return jsonify({"error": str(ve)}), 400
        except Exception as e:
            return jsonify({"error": f"Internal error registering server: {str(e)}"}), 500

    @bp.route("/<server_id>", methods=["GET"])
    def get_server(server_id):
        """Retrieves details of a specific backend server."""
        srv = registry.get_server(server_id)
        if not srv:
            return jsonify({"error": f"Server {server_id} not found."}), 404
        return jsonify({"server": srv}), 200

    @bp.route("/<server_id>", methods=["PUT"])
    def update_server(server_id):
        """Updates backend server configuration."""
        data = request.get_json(silent=True) or {}
        name = data.get("name")
        url = data.get("url")
        weight = data.get("weight")
        is_enabled = data.get("is_enabled")

        try:
            srv = registry.update_server(
                server_id=server_id,
                name=name,
                url=url,
                weight=int(weight) if weight is not None else None,
                is_enabled=bool(is_enabled) if is_enabled is not None else None
            )
            return jsonify({"message": f"Server {server_id} updated.", "server": srv}), 200
        except ValueError as ve:
            return jsonify({"error": str(ve)}), 400
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @bp.route("/<server_id>", methods=["DELETE"])
    def delete_server(server_id):
        """Deletes a backend server."""
        try:
            registry.delete_server(server_id)
            return jsonify({"message": f"Server {server_id} removed successfully."}), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @bp.route("/<server_id>/toggle", methods=["POST"])
    def toggle_server(server_id):
        """Toggles a server between enabled and disabled."""
        srv = registry.get_server(server_id)
        if not srv:
            return jsonify({"error": f"Server {server_id} not found."}), 404
        new_status = not bool(srv.get("is_enabled"))
        updated = registry.update_server(server_id=server_id, is_enabled=new_status)
        return jsonify({
            "message": f"Server {server_id} is now {'enabled' if new_status else 'disabled'}.",
            "server": updated
        }), 200

    @bp.route("/<server_id>/circuit/reset", methods=["POST"])
    def reset_circuit(server_id):
        """Manually resets the circuit breaker for a server to CLOSED."""
        cb = registry.get_circuit_breaker(server_id)
        if not cb:
            return jsonify({"error": f"Circuit breaker for {server_id} not found."}), 404
        cb.manual_reset()
        return jsonify({"message": f"Circuit breaker for {server_id} manually reset to CLOSED."}), 200

    @bp.route("/<server_id>/circuit/trip", methods=["POST"])
    def trip_circuit(server_id):
        """Manually trips the circuit breaker for a server to OPEN."""
        cb = registry.get_circuit_breaker(server_id)
        if not cb:
            return jsonify({"error": f"Circuit breaker for {server_id} not found."}), 404
        cb.manual_trip("Manual operator trip via API")
        return jsonify({"message": f"Circuit breaker for {server_id} manually tripped to OPEN."}), 200

    return bp
