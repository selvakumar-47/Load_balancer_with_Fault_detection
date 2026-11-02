import os

class Config:
    # Server / App configuration
    SECRET_KEY = os.environ.get("SECRET_KEY", "lb-fault-detection-secret-2026")
    HOST = os.environ.get("LB_HOST", "127.0.0.1")
    PORT = int(os.environ.get("LB_PORT", 5000))
    DEBUG = os.environ.get("FLASK_DEBUG", "0") == "1"

    # SQLite Database
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    DATABASE_PATH = os.environ.get("DATABASE_PATH", os.path.join(BASE_DIR, "load_balancer.db"))

    # Load Balancer Defaults
    DEFAULT_ALGORITHM = "ROUND_ROBIN"  # ROUND_ROBIN, WEIGHTED_ROUND_ROBIN, LEAST_CONNECTIONS
    REQUEST_TIMEOUT_SECONDS = float(os.environ.get("REQUEST_TIMEOUT_SECONDS", 3.0))
    PROXY_MAX_BODY_SIZE = 16 * 1024 * 1024  # 16MB

    # Health Monitor Defaults
    HEALTH_CHECK_INTERVAL_SECONDS = float(os.environ.get("HEALTH_CHECK_INTERVAL", 3.0))
    HEALTH_CHECK_TIMEOUT_SECONDS = float(os.environ.get("HEALTH_CHECK_TIMEOUT", 1.5))
    FAILURE_THRESHOLD = int(os.environ.get("FAILURE_THRESHOLD", 3))  # Failures before OPEN
    RECOVERY_THRESHOLD = int(os.environ.get("RECOVERY_THRESHOLD", 2))  # Successes in HALF-OPEN before CLOSED
    RECOVERY_DELAY_SECONDS = float(os.environ.get("RECOVERY_DELAY", 5.0))  # Delay before entering HALF-OPEN

    # Allowed Proxy Destination Hosts (Security Allowlist)
    ALLOWED_HOSTS = ["127.0.0.1", "localhost"]
    ALLOWED_PORTS = [8001, 8002, 8003, 8004, 8005, 5001, 5002, 5003]
