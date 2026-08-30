import os

os.environ.setdefault("INFLUXDB_TOKEN", "test-token")

from influx_client import InfluxQueryClient

MALICIOUS_AGENT_ID = 'x" ) // or true ("'


def _client():
    return InfluxQueryClient()


def test_get_sensor_timeseries_does_not_interpolate_agent_id(monkeypatch):
    """Regression test for #3: a malicious agent_id must never end up
    inlined into the Flux query text (it must travel as a bind
    parameter instead), otherwise it could break out of the quoted
    string literal and inject arbitrary Flux."""
    client = _client()

    captured = {}

    def fake_query(query, params=None):
        captured["query"] = query
        captured["params"] = params
        return []

    monkeypatch.setattr(client.query_api, "query", fake_query)

    client.get_sensor_timeseries(MALICIOUS_AGENT_ID, 0, hours=24)

    assert MALICIOUS_AGENT_ID not in captured["query"]
    assert "params.agent_id" in captured["query"]
    assert captured["params"]["agent_id"] == MALICIOUS_AGENT_ID


def test_get_sensor_summary_does_not_interpolate_agent_id(monkeypatch):
    client = _client()

    captured = {}

    def fake_query(query, params=None):
        captured["query"] = query
        captured["params"] = params
        return []

    monkeypatch.setattr(client.query_api, "query", fake_query)

    client.get_sensor_summary(MALICIOUS_AGENT_ID, 0, hours=24)

    assert MALICIOUS_AGENT_ID not in captured["query"]
    assert "params.agent_id" in captured["query"]
    assert captured["params"]["agent_id"] == MALICIOUS_AGENT_ID
