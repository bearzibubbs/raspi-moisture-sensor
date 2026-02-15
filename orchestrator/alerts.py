import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from database import get_db
from models import Agent, AlertRule, ActiveAlert

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/alerts", tags=["alerts"])


# Request/Response models
class AlertRuleCreate(BaseModel):
    agent_id: str
    sensor_channel: int
    dry_threshold: float
    wet_threshold: float
    enabled: bool = True


class AlertResponse(BaseModel):
    id: int
    agent_id: str
    sensor_channel: int
    alert_type: str
    triggered_at: str
    resolved_at: Optional[str]
    acknowledged: bool
    moisture_percent: Optional[float]
    threshold: Optional[float]
    location: Optional[str]
    plant_type: Optional[str]
    sensor_name: Optional[str]


class AlertEngine:
    """Alert calculation engine"""

    def __init__(self, db: Session):
        self.db = db

    def check_reading(
        self,
        agent_id: str,
        sensor_channel: int,
        moisture_percent: float,
        location: str,
        plant_type: str,
        sensor_name: str,
        thresholds: Dict[str, float]
    ):
        """
        Check a reading against thresholds and create/resolve alerts.

        Args:
            agent_id: Agent identifier
            sensor_channel: Sensor channel number
            moisture_percent: Current moisture percentage
            location: Sensor location
            plant_type: Plant type
            sensor_name: Sensor name
            thresholds: Dict with dry_percent, wet_percent, hysteresis
        """
        dry_threshold = thresholds.get('dry_percent', 30)
        wet_threshold = thresholds.get('wet_percent', 85)
        hysteresis = thresholds.get('hysteresis', 5)

        # Check for active alerts for this sensor
        active_alert = self.db.query(ActiveAlert).filter(
            ActiveAlert.agent_id == agent_id,
            ActiveAlert.sensor_channel == sensor_channel,
            ActiveAlert.resolved_at.is_(None)
        ).first()

        # Determine if alert should be triggered
        trigger_dry = moisture_percent < dry_threshold
        trigger_wet = moisture_percent > wet_threshold

        # Determine if alert should be resolved (with hysteresis)
        resolve_dry = moisture_percent > (dry_threshold + hysteresis)
        resolve_wet = moisture_percent < (wet_threshold - hysteresis)

        if trigger_dry and not active_alert:
            # Create new dry alert
            self._create_alert(
                agent_id=agent_id,
                sensor_channel=sensor_channel,
                alert_type="too_dry",
                moisture_percent=moisture_percent,
                threshold=dry_threshold,
                location=location,
                plant_type=plant_type,
                sensor_name=sensor_name
            )

        elif trigger_wet and not active_alert:
            # Create new wet alert
            self._create_alert(
                agent_id=agent_id,
                sensor_channel=sensor_channel,
                alert_type="too_wet",
                moisture_percent=moisture_percent,
                threshold=wet_threshold,
                location=location,
                plant_type=plant_type,
                sensor_name=sensor_name
            )

        elif active_alert:
            # Check if alert should be resolved
            if active_alert.alert_type == "too_dry" and resolve_dry:
                self._resolve_alert(active_alert)
            elif active_alert.alert_type == "too_wet" and resolve_wet:
                self._resolve_alert(active_alert)

    def _create_alert(
        self,
        agent_id: str,
        sensor_channel: int,
        alert_type: str,
        moisture_percent: float,
        threshold: float,
        location: str,
        plant_type: str,
        sensor_name: str
    ):
        """Create a new alert"""
        alert = ActiveAlert(
            agent_id=agent_id,
            sensor_channel=sensor_channel,
            alert_type=alert_type,
            moisture_percent=moisture_percent,
            threshold=threshold,
            location=location,
            plant_type=plant_type,
            sensor_name=sensor_name
        )

        self.db.add(alert)
        self.db.commit()

        logger.warning(
            f"Alert triggered: {alert_type} for {agent_id}/channel-{sensor_channel} "
            f"({sensor_name}): {moisture_percent:.1f}% (threshold: {threshold}%)"
        )

    def _resolve_alert(self, alert: ActiveAlert):
        """Resolve an existing alert"""
        alert.resolved_at = datetime.now(timezone.utc)
        self.db.commit()

        logger.info(
            f"Alert resolved: {alert.alert_type} for {alert.agent_id}/channel-{alert.sensor_channel} "
            f"({alert.sensor_name})"
        )

    def check_agent_offline(self, timeout_minutes: int = 10):
        """Check for agents that haven't sent heartbeat recently"""
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=timeout_minutes)

        # Find agents with old heartbeats
        offline_agents = self.db.query(Agent).filter(
            Agent.status == 'active',
            Agent.last_heartbeat < cutoff
        ).all()

        for agent in offline_agents:
            # Check if alert already exists
            existing = self.db.query(ActiveAlert).filter(
                ActiveAlert.agent_id == agent.agent_id,
                ActiveAlert.alert_type == 'agent_offline',
                ActiveAlert.resolved_at.is_(None)
            ).first()

            if not existing:
                alert = ActiveAlert(
                    agent_id=agent.agent_id,
                    sensor_channel=-1,  # Not sensor-specific
                    alert_type='agent_offline',
                    location="N/A",
                    plant_type="N/A",
                    sensor_name="N/A"
                )
                self.db.add(alert)

                logger.warning(f"Agent offline alert: {agent.agent_id}")

        # Resolve agent_offline alerts for agents that are back online
        online_agents = self.db.query(Agent).filter(
            Agent.status == 'active',
            Agent.last_heartbeat >= cutoff
        ).all()

        for agent in online_agents:
            alerts = self.db.query(ActiveAlert).filter(
                ActiveAlert.agent_id == agent.agent_id,
                ActiveAlert.alert_type == 'agent_offline',
                ActiveAlert.resolved_at.is_(None)
            ).all()

            for alert in alerts:
                alert.resolved_at = datetime.now(timezone.utc)
                logger.info(f"Agent online alert resolved: {agent.agent_id}")

        self.db.commit()


# API Endpoints

@router.get("", response_model=List[AlertResponse])
async def get_active_alerts(
    db: Session = Depends(get_db)
):
    """Get all active (unresolved) alerts"""
    alerts = db.query(ActiveAlert).filter(
        ActiveAlert.resolved_at.is_(None)
    ).order_by(ActiveAlert.triggered_at.desc()).all()

    return [
        AlertResponse(
            id=a.id,
            agent_id=a.agent_id,
            sensor_channel=a.sensor_channel,
            alert_type=a.alert_type,
            triggered_at=a.triggered_at.isoformat() if a.triggered_at else None,
            resolved_at=a.resolved_at.isoformat() if a.resolved_at else None,
            acknowledged=a.acknowledged,
            moisture_percent=a.moisture_percent,
            threshold=a.threshold,
            location=a.location,
            plant_type=a.plant_type,
            sensor_name=a.sensor_name
        )
        for a in alerts
    ]


@router.get("/history", response_model=List[AlertResponse])
async def get_alert_history(
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """Get alert history (resolved alerts)"""
    alerts = db.query(ActiveAlert).filter(
        ActiveAlert.resolved_at.isnot(None)
    ).order_by(ActiveAlert.triggered_at.desc()).limit(limit).all()

    return [
        AlertResponse(
            id=a.id,
            agent_id=a.agent_id,
            sensor_channel=a.sensor_channel,
            alert_type=a.alert_type,
            triggered_at=a.triggered_at.isoformat() if a.triggered_at else None,
            resolved_at=a.resolved_at.isoformat() if a.resolved_at else None,
            acknowledged=a.acknowledged,
            moisture_percent=a.moisture_percent,
            threshold=a.threshold,
            location=a.location,
            plant_type=a.plant_type,
            sensor_name=a.sensor_name
        )
        for a in alerts
    ]


@router.post("/{alert_id}/acknowledge")
async def acknowledge_alert(
    alert_id: int,
    db: Session = Depends(get_db)
):
    """Acknowledge an alert"""
    alert = db.query(ActiveAlert).filter_by(id=alert_id).first()

    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    alert.acknowledged = True
    db.commit()

    logger.info(f"Alert acknowledged: {alert_id}")

    return {"status": "acknowledged"}


@router.get("/rules")
async def get_alert_rules(
    db: Session = Depends(get_db)
):
    """Get all alert rules"""
    rules = db.query(AlertRule).all()

    return {
        "rules": [
            {
                "id": r.id,
                "agent_id": r.agent_id,
                "sensor_channel": r.sensor_channel,
                "dry_threshold": r.dry_threshold,
                "wet_threshold": r.wet_threshold,
                "enabled": r.enabled
            }
            for r in rules
        ]
    }


@router.post("/rules")
async def create_alert_rule(
    request: AlertRuleCreate,
    db: Session = Depends(get_db)
):
    """Create a new alert rule"""
    rule = AlertRule(
        agent_id=request.agent_id,
        sensor_channel=request.sensor_channel,
        dry_threshold=request.dry_threshold,
        wet_threshold=request.wet_threshold,
        enabled=request.enabled
    )

    db.add(rule)
    db.commit()

    logger.info(f"Alert rule created for {request.agent_id}/channel-{request.sensor_channel}")

    return {"id": rule.id, "status": "created"}
