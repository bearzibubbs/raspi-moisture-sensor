from sqlalchemy import Column, Integer, String, DateTime, Boolean, Float, Text, ForeignKey, JSON
from sqlalchemy.sql import func
from database import Base
from passlib.context import CryptContext
import secrets

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class Agent(Base):
    __tablename__ = "agents"

    agent_id = Column(String(255), primary_key=True)
    hostname = Column(String(255))
    hardware = Column(String(255))
    agent_token_hash = Column(String(255), nullable=False)
    registered_at = Column(DateTime(timezone=True), server_default=func.now())
    last_heartbeat = Column(DateTime(timezone=True))
    last_sync_at = Column(DateTime(timezone=True))
    status = Column(String(50), default='active')
    desired_config_version = Column(Integer, default=1)
    applied_config_version = Column(Integer, default=0)
    metadata = Column(JSON)

    @staticmethod
    def hash_token(token: str) -> str:
        """Hash a token using bcrypt"""
        return pwd_context.hash(token)

    @staticmethod
    def verify_token(plain_token: str, hashed_token: str) -> bool:
        """Verify a token against its hash"""
        return pwd_context.verify(plain_token, hashed_token)


class BootstrapToken(Base):
    __tablename__ = "bootstrap_tokens"

    token_hash = Column(String(255), primary_key=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used_count = Column(Integer, default=0)
    max_uses = Column(Integer, nullable=True)

    @staticmethod
    def generate_token() -> str:
        """Generate a new bootstrap token"""
        return f"bst_k8s_{secrets.token_urlsafe(32)}"

    def is_expired(self) -> bool:
        """Check if token is expired"""
        from datetime import datetime, timezone
        return datetime.now(timezone.utc) > self.expires_at

    def is_valid(self) -> bool:
        """Check if token is valid (not expired, not exhausted)"""
        if self.is_expired():
            return False
        if self.max_uses and self.used_count >= self.max_uses:
            return False
        return True


class AlertRule(Base):
    __tablename__ = "alert_rules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_id = Column(String(255), ForeignKey('agents.agent_id'))
    sensor_channel = Column(Integer)
    dry_threshold = Column(Float)
    wet_threshold = Column(Float)
    enabled = Column(Boolean, default=True)


class ActiveAlert(Base):
    __tablename__ = "active_alerts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_id = Column(String(255), ForeignKey('agents.agent_id'))
    sensor_channel = Column(Integer)
    alert_type = Column(String(50))  # 'too_dry', 'too_wet', 'sensor_offline', 'agent_offline'
    triggered_at = Column(DateTime(timezone=True), server_default=func.now())
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    acknowledged = Column(Boolean, default=False)
    moisture_percent = Column(Float, nullable=True)
    threshold = Column(Float, nullable=True)
    location = Column(String(255))
    plant_type = Column(String(255))
    sensor_name = Column(String(255))


class AgentConfig(Base):
    __tablename__ = "agent_configs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_id = Column(String(255), ForeignKey('agents.agent_id'))
    version = Column(Integer, nullable=False)
    config_data = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    applied_at = Column(DateTime(timezone=True), nullable=True)
