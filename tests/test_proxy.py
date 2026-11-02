import pytest
from unittest.mock import MagicMock, patch
from flask import Flask, Request
from core.proxy import ReverseProxy
from core.server_registry import ServerRegistry
from database.db import init_db
import tempfile
import os

@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    init_db(path)
    yield path
    try:
        os.remove(path)
    except Exception:
        pass

def test_url_validation_security(temp_db):
    registry = ServerRegistry(db_path=temp_db)

    # Allowed local destinations
    assert registry.validate_url("http://127.0.0.1:8001") is True
    assert registry.validate_url("http://localhost:8002") is True
    assert registry.validate_url("http://127.0.0.1:5001") is True

    # Disallowed external or dangerous destinations (SSRF protection)
    assert registry.validate_url("http://google.com") is False
    assert registry.validate_url("http://169.254.169.254/latest/meta-data") is False
    assert registry.validate_url("file:///etc/passwd") is False
    assert registry.validate_url("ftp://127.0.0.1:21") is False

def test_proxy_hop_by_hop_header_filtering(temp_db):
    registry = ServerRegistry(db_path=temp_db)
    proxy = ReverseProxy(registry, db_path=temp_db)

    headers = {
        "Host": "127.0.0.1:5000",
        "User-Agent": "TestClient/1.0",
        "Connection": "keep-alive",
        "Keep-Alive": "timeout=5",
        "Proxy-Authenticate": "Basic",
        "Upgrade": "websocket",
        "Accept": "application/json"
    }

    filtered = proxy.filter_headers(headers)
    assert "Host" in filtered
    assert "User-Agent" in filtered
    assert "Accept" in filtered
    assert "Connection" not in filtered
    assert "Keep-Alive" not in filtered
    assert "Proxy-Authenticate" not in filtered
    assert "Upgrade" not in filtered

def test_proxy_503_when_no_backend_available(temp_db):
    registry = ServerRegistry(db_path=temp_db)
    proxy = ReverseProxy(registry, db_path=temp_db)

    app = Flask(__name__)
    with app.test_request_context("/proxy/test", method="GET"):
        from flask import request
        # Passing None as selected backend
        resp = proxy.forward_request(
            flask_req=request,
            subpath="test",
            selected_backend=None,
            algorithm_name="ROUND_ROBIN"
        )
        assert resp.status_code == 503
        data = resp.get_json()
        assert data["error"] == "Service Unavailable"
        assert "All backend servers are currently offline" in data["message"]
