import pytest
from fastapi.testclient import TestClient
from src.api.main import app

def test_sse_stream_endpoint_ready_stock():
    client = TestClient(app)
    
    # RELIANCE is already in database and ready
    response = client.get("/api/v1/stocks/RELIANCE/stream")
    assert response.status_code == 200
    assert "text/event-stream" in response.headers.get("content-type", "")
    
    body = response.text
    assert "event: status" in body
    assert "event: close" in body
    assert "RELIANCE" in body


def test_sse_stream_endpoint_unseeded_stock():
    client = TestClient(app)
    
    # UNKNOWN_SSE_TEST stock
    response = client.get("/api/v1/stocks/UNKNOWN_SSE_TEST/stream")
    assert response.status_code == 200
    assert "text/event-stream" in response.headers.get("content-type", "")
    
    body = response.text
    assert "event: status" in body
    assert "NOT_STARTED" in body
