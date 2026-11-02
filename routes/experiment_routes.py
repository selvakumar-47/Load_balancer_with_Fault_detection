from flask import Blueprint, request, jsonify
from core.experiment_manager import ExperimentManager
from test_backends.manager import BackendClusterManager

def create_experiment_blueprint(load_balancer):
    bp = Blueprint("experiment", __name__, url_prefix="/api/experiment")
    exp_manager = ExperimentManager(load_balancer.db_path)
    cluster_manager = BackendClusterManager()

    @bp.route("/fault", methods=["POST"])
    def inject_fault():
        """Injects a controlled fault (DELAY, ERROR_500, CRASH, RECOVER) on a test backend."""
        data = request.get_json(silent=True) or {}
        server_id = data.get("server_id")
        fault_type = data.get("fault_type")
        param_val = data.get("param_val")

        if not server_id or not fault_type:
            return jsonify({"error": "server_id and fault_type are required."}), 400

        try:
            result = exp_manager.inject_fault(server_id, fault_type, param_val)
            return jsonify({"message": f"Fault '{fault_type}' injected successfully on {server_id}.", "result": result}), 200
        except ValueError as ve:
            return jsonify({"error": str(ve)}), 400
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @bp.route("/workload/start", methods=["POST"])
    def start_workload():
        """Starts synthetic traffic generation batch."""
        data = request.get_json(silent=True) or {}
        total_requests = int(data.get("total_requests", 50))
        concurrency = int(data.get("concurrency", 2))
        delay_ms = int(data.get("delay_ms", 50))

        # Base URL of this running load balancer instance
        lb_host = request.host_url.rstrip("/")
        algo = load_balancer.get_algorithm_name()

        try:
            res = exp_manager.start_workload(
                target_lb_url=lb_host,
                total_requests=total_requests,
                concurrency=concurrency,
                delay_ms=delay_ms,
                algorithm_name=algo
            )
            return jsonify(res), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 400

    @bp.route("/workload/stop", methods=["POST"])
    def stop_workload():
        """Aborts ongoing workload."""
        res = exp_manager.stop_workload()
        return jsonify(res), 200

    @bp.route("/workload/status", methods=["GET"])
    def workload_status():
        """Queries status and counts of ongoing workload."""
        status = exp_manager.get_workload_status()
        return jsonify({"workload": status}), 200

    @bp.route("/cluster/status", methods=["GET"])
    def cluster_status():
        """Returns running status of the 3 local test backends."""
        return jsonify({"cluster": cluster_manager.get_all_status()}), 200

    @bp.route("/cluster/start", methods=["POST"])
    def cluster_start():
        """Starts all 3 test backends."""
        cluster_manager.start_all()
        return jsonify({"message": "All 3 local test backends started.", "cluster": cluster_manager.get_all_status()}), 200

    @bp.route("/cluster/stop", methods=["POST"])
    def cluster_stop():
        """Stops all 3 test backends."""
        cluster_manager.stop_all()
        return jsonify({"message": "All 3 local test backends stopped.", "cluster": cluster_manager.get_all_status()}), 200

    @bp.route("/cluster/restart-server", methods=["POST"])
    def cluster_restart_server():
        """Restarts a specific local test backend."""
        data = request.get_json(silent=True) or {}
        server_id = data.get("server_id")
        if not server_id:
            return jsonify({"error": "server_id is required."}), 400
        ok = cluster_manager.restart_server(server_id)
        if ok:
            return jsonify({"message": f"Server {server_id} restarted.", "status": cluster_manager.get_server_status(server_id)}), 200
        return jsonify({"error": f"Server {server_id} not found in cluster manager."}), 404

    return bp
