"""Satellite HTTP client: URL/param building, JPEG guard, error bookkeeping."""
import pytest
import requests

from app.satellite import SatelliteClient, SatelliteError


class FakeResponse:
    def __init__(self, content=b"", payload=None, status=200):
        self.content = content
        self._payload = payload
        self.status_code = status

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


class FakeSession:
    def __init__(self, responses=None, error=None):
        self.calls = []
        self.responses = list(responses or [])
        self.error = error

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params, timeout))
        if self.error:
            raise self.error
        return self.responses.pop(0) if self.responses else FakeResponse(payload={})


def test_unconfigured_client_is_disabled_and_raises():
    client = SatelliteClient("", session=FakeSession())
    assert client.enabled is False
    with pytest.raises(SatelliteError):
        client.status()


def test_set_led_clamps_and_names_params():
    session = FakeSession([FakeResponse(payload={"r": 255})])
    client = SatelliteClient("10.0.0.9", timeout_s=1.5, session=session, clock=lambda: 42.0)
    client.set_led(300, -5, 128.7, effect="pulse", period_ms=50, brightness=999)
    url, params, timeout = session.calls[0]
    assert url == "http://10.0.0.9/led"
    assert params == {"r": 255, "g": 0, "b": 128, "effect": "pulse",
                      "periodMs": 100, "brightness": 255}
    assert timeout == 1.5
    assert client.last_ok_at == 42.0 and client.last_error is None


def test_set_led_rejects_unknown_effect():
    client = SatelliteClient("10.0.0.9", session=FakeSession())
    with pytest.raises(ValueError):
        client.set_led(1, 2, 3, effect="rainbow")


def test_snapshot_requires_a_jpeg():
    session = FakeSession([FakeResponse(content=b"<html>nope"),
                           FakeResponse(content=b"\xff\xd8\xff\xe0data")])
    client = SatelliteClient("10.0.0.9", session=session)
    with pytest.raises(SatelliteError):
        client.snapshot()
    assert client.snapshot().startswith(b"\xff\xd8")


def test_transport_errors_are_recorded_not_leaked():
    session = FakeSession(error=requests.ConnectionError("refused"))
    client = SatelliteClient("10.0.0.9", session=session)
    with pytest.raises(SatelliteError):
        client.status()
    assert "refused" in client.last_error
    assert client.info()["lastError"] == client.last_error
