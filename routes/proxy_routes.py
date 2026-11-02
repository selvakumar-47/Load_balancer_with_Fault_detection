from flask import Blueprint, request, jsonify

def create_proxy_blueprint(load_balancer):
    bp = Blueprint("proxy", __name__)

    @bp.route("/health", methods=["GET"])
    def lb_health():
        """Load balancer self-health check."""
        return jsonify({
            "status": "UP",
            "service": "Load Balancer with Fault Detection & Auto-Recovery",
            "active_algorithm": load_balancer.get_algorithm_name(),
            "timestamp": load_balancer.health_monitor.get_status().get("last_run_time")
        }), 200

    @bp.route("/proxy", defaults={"subpath": ""}, methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"], strict_slashes=False)
    @bp.route("/proxy/", defaults={"subpath": ""}, methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"], strict_slashes=False)
    @bp.route("/proxy/<path:subpath>", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"], strict_slashes=False)
    def proxy_endpoint(subpath=""):
        """HTTP Reverse Proxy entrypoint."""
        exp_id = request.headers.get("X-Experiment-ID")
        return load_balancer.route_request(request, subpath, experiment_id=exp_id)

    return bp
