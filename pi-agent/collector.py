import time
import logging
from typing import Optional
from config import SensorConfig
from storage import Reading


logger = logging.getLogger(__name__)


def calculate_moisture_percent(
    raw_value: int,
    sensor_min: int,
    sensor_max: int,
    sensor_type: str
) -> float:
    """
    Calculate moisture percentage from raw ADC value.

    Capacitive sensors: Lower value = wetter (inverted)
    Resistive sensors: Higher value = wetter (normal)
    """
    if sensor_type == "capacitive":
        # Inverted: higher raw value = drier
        percentage = ((sensor_max - raw_value) / (sensor_max - sensor_min)) * 100
    else:  # resistive
        # Normal: higher raw value = wetter
        percentage = ((raw_value - sensor_min) / (sensor_max - sensor_min)) * 100

    # Clamp to 0-100
    return max(0.0, min(100.0, percentage))


class SensorCollector:
    def __init__(self, adc, sensor_config: SensorConfig):
        """
        Initialize sensor collector.

        Args:
            adc: ADC instance from grove.py (grove.adc.ADC)
            sensor_config: Sensor configuration
        """
        self.adc = adc
        self.config = sensor_config
        self.max_retries = 3
        self.retry_delay = 1  # seconds

    def read(self) -> Optional[Reading]:
        """
        Read sensor and return Reading object, or None if failed.

        Implements retry logic for transient failures.
        """
        raw_value = None

        # Retry logic
        for attempt in range(self.max_retries):
            try:
                raw_value = self.adc.read(self.config.channel)

                if raw_value is not None:
                    break

                logger.warning(
                    f"Sensor read attempt {attempt + 1} returned None "
                    f"(channel {self.config.channel})"
                )

            except Exception as e:
                logger.warning(
                    f"Sensor read attempt {attempt + 1} failed "
                    f"(channel {self.config.channel}): {e}"
                )

            if attempt < self.max_retries - 1:
                time.sleep(self.retry_delay)

        # All retries failed
        if raw_value is None:
            logger.error(
                f"Sensor {self.config.channel} offline or not responding "
                f"after {self.max_retries} attempts"
            )
            return None

        # Calculate moisture percentage
        moisture_percent = calculate_moisture_percent(
            raw_value,
            self.config.calibration.min,
            self.config.calibration.max,
            self.config.type
        )

        # Create reading
        reading = Reading(
            timestamp=int(time.time()),
            sensor_channel=self.config.channel,
            sensor_type=self.config.type,
            raw_value=raw_value,
            moisture_percent=moisture_percent,
            location=self.config.labels.location,
            plant_type=self.config.labels.plant_type,
            sensor_name=self.config.labels.sensor_name,
            synced=False
        )

        return reading
