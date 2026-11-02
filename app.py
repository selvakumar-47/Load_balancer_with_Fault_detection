import os
import atexit
from flask import Flask, render_template, send_from_directory
from waitress import serve
from config import Config
from database.db import init_db
from core.load_balancer import LoadBalancer
from test_backends.manager import BackendClusterManager

# Import route blueprints
from routes.proxy_routes import create_proxy_blueprint
from routes.server_routes import create_server_blueprint
from routes.dashboard_routes import create_dashboard_blueprint
from routes.metrics_routes import create_metrics_blueprint
from routes.experiment_routes import create_experiment_blueprint
from routes.settings_routes import create_settings_blueprint

def create_app(test_config=None):
    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)

    # Initialize Database Schema & Seed Data
    db_path = app.config.get("DATABASE_PATH", Config.DATABASE_PATH)
    init_db(db_path)

    # Initialize Central Load Balancer
    lb = LoadBalancer(db_path=db_path)
    app.load_balancer = lb

    # Register Blueprints
    app.register_blueprint(create_proxy_blueprint(lb))
    app.register_blueprint(create_server_blueprint(lb))
    app.register_blueprint(create_dashboard_blueprint(lb))
    app.register_blueprint(create_metrics_blueprint(lb))
    app.register_blueprint(create_experiment_blueprint(lb))
    app.register_blueprint(create_settings_blueprint(lb))

    # Main UI Single-Page Application route
    @app.route("/")
    def index():
        return render_template("index.html")

    return app, lb

if __name__ == "__main__":
    print("=" * 70)
    print(" LOAD BALANCER WITH FAULT DETECTION AND AUTOMATIC RECOVERY")
    print(" Enterprise Operational Console & Academic Demo Platform")
    print("=" * 70)

    # 1. Start the 3 local test backends automatically in background threads
    cluster = BackendClusterManager()
    print("[Cluster] Starting 3 local test backends (Alpha:8001, Beta:8002, Gamma:8003)...")
    cluster.start_all()

    # 2. Create the Flask app and Load Balancer
    app, lb = create_app()

    # 3. Start Health Monitor prober
    lb.start()

    # Register clean shutdown
    def cleanup():
        print("\n[Shutdown] Stopping Health Monitor...")
        lb.stop()
        print("[Shutdown] Stopping Test Backends Cluster...")
        cluster.stop_all()
        print("[Shutdown] Clean exit complete.")

    atexit.register(cleanup)

    print(f"[LoadBalancer] Dashboard UI running at: http://{Config.HOST}:{Config.PORT}")
    print(f"[LoadBalancer] HTTP Reverse Proxy path: http://{Config.HOST}:{Config.PORT}/proxy/")
    print(f"[LoadBalancer] Self-Health endpoint:   http://{Config.HOST}:{Config.PORT}/health")
    print("=" * 70)

    # Run the production WSGI server
    serve(app, host=Config.HOST, port=Config.PORT, threads=8)
