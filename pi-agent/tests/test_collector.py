import pytest
from collector import calculate_moisture_percent


def test_calculate_moisture_capacitive():
    # Capacitive: lower raw = wetter (inverted)
    assert calculate_moisture_percent(0, 300, 800, "capacitive") == 100.0
    assert calculate_moisture_percent(800, 300, 800, "capacitive") == 0.0


def test_calculate_moisture_resistive():
    # Resistive: higher raw = wetter (normal)
    assert calculate_moisture_percent(0, 0, 950, "resistive") == 0.0
    assert calculate_moisture_percent(950, 0, 950, "resistive") == 100.0


def test_calculate_moisture_resistive_inverted():
    # Resistive inverted: dry-in-air raw > wet raw, so lower raw = wetter
    assert calculate_moisture_percent(0, 0, 950, sensor_type="resistive_inverted") == 100.0
    assert calculate_moisture_percent(950, 0, 950, sensor_type="resistive_inverted") == 0.0
