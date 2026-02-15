import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from database import get_db
from models import Agent, BootstrapToken
from auth import verify_bootstrap_token, verify_agent_token, generate_agent_token

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/agents", tags=["agents"])


# Request/Response models
class AgentRegistrationRequest(BaseModel):
    agent_id: str
    hostname: str
    hardware: str


class AgentRegistrationResponse(BaseModel):
    agent_token: str
    config: Dict[str, Any]


class HeartbeatRequest(BaseModel):
    pass  # Empty for now, could add metrics later


class HeartbeatResponse(BaseModel):
    status: str
    server_time: str


class CreateBootstrapTokenRequest(BaseModel):
    expires_in_hours: int = 24
    max_uses: int = None


class CreateBootstrapTokenResponse(BaseModel):
    token: str
    expires_at: str


@router.post("/register", response_model=AgentRegistrationResponse)
async def register_agent(
    request: AgentRegistrationRequest,
    bootstrap: BootstrapToken = Depends(verify_bootstrap_token),
    db: Session = Depends(get_db)
):
    """Register a new agent with bootstrap token"""

    # Check if agent already exists
    existing = db.query(Agent).filter_by(agent_id=request.agent_id).first()
    if existing:
        raise HTTPException(status_code=409, detail="Agent already registered")

    # Generate agent token
    agent_token = generate_agent_token()
    token_hash = Agent.hash_token(agent_token)

    # Create agent record
    agent = Agent(
        agent_id=request.agent_id,
        hostname=request.hostname,
        hardware=request.hardware,
        agent_token_hash=token_hash,
        status='active',
        desired_config_version=1,
        applied_config_version=0
    )

    db.add(agent)

    # Increment bootstrap token usage
    bootstrap.used_count += 1

    db.commit()

    logger.info(f"Agent registered: {request.agent_id}")

    # Return agent token and initial config
    return AgentRegistrationResponse(
        agent_token=agent_token,
        config={"version": 1}  # Placeholder config
    )


@router.post("/{agent_id}/heartbeat", response_model=HeartbeatResponse)
async def agent_heartbeat(
    agent_id: str,
    request: HeartbeatRequest,
    agent: Agent = Depends(verify_agent_token),
    db: Session = Depends(get_db)
):
    """Receive heartbeat from agent"""

    # Verify agent_id matches token
    if agent.agent_id != agent_id:
        raise HTTPException(status_code=403, detail="Agent ID mismatch")

    # Update last heartbeat
    agent.last_heartbeat = datetime.now(timezone.utc)
    db.commit()

    logger.debug(f"Heartbeat received from {agent_id}")

    return HeartbeatResponse(
        status="ok",
        server_time=datetime.now(timezone.utc).isoformat()
    )


@router.get("")
async def list_agents(
    db: Session = Depends(get_db)
):
    """List all registered agents"""
    agents = db.query(Agent).all()

    return {
        "agents": [
            {
                "agent_id": a.agent_id,
                "hostname": a.hostname,
                "hardware": a.hardware,
                "status": a.status,
                "registered_at": a.registered_at.isoformat() if a.registered_at else None,
                "last_heartbeat": a.last_heartbeat.isoformat() if a.last_heartbeat else None,
                "config_version": a.applied_config_version
            }
            for a in agents
        ]
    }


@router.get("/{agent_id}")
async def get_agent(
    agent_id: str,
    db: Session = Depends(get_db)
):
    """Get agent details"""
    agent = db.query(Agent).filter_by(agent_id=agent_id).first()

    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    return {
        "agent_id": agent.agent_id,
        "hostname": agent.hostname,
        "hardware": agent.hardware,
        "status": agent.status,
        "registered_at": agent.registered_at.isoformat() if agent.registered_at else None,
        "last_heartbeat": agent.last_heartbeat.isoformat() if agent.last_heartbeat else None,
        "last_sync_at": agent.last_sync_at.isoformat() if agent.last_sync_at else None,
        "desired_config_version": agent.desired_config_version,
        "applied_config_version": agent.applied_config_version,
        "metadata": agent.metadata
    }


@router.delete("/{agent_id}")
async def decommission_agent(
    agent_id: str,
    db: Session = Depends(get_db)
):
    """Decommission an agent"""
    agent = db.query(Agent).filter_by(agent_id=agent_id).first()

    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    agent.status = 'decommissioned'
    db.commit()

    logger.info(f"Agent decommissioned: {agent_id}")

    return {"status": "decommissioned"}


# Bootstrap token management
@router.post("/bootstrap-tokens", response_model=CreateBootstrapTokenResponse)
async def create_bootstrap_token(
    request: CreateBootstrapTokenRequest,
    db: Session = Depends(get_db)
):
    """Create a new bootstrap token (admin only - no auth for now)"""

    # Generate token
    token = BootstrapToken.generate_token()
    token_hash = Agent.hash_token(token)

    # Calculate expiration
    expires_at = datetime.now(timezone.utc) + timedelta(hours=request.expires_in_hours)

    # Create record
    bootstrap = BootstrapToken(
        token_hash=token_hash,
        expires_at=expires_at,
        max_uses=request.max_uses
    )

    db.add(bootstrap)
    db.commit()

    logger.info(f"Bootstrap token created, expires: {expires_at.isoformat()}")

    return CreateBootstrapTokenResponse(
        token=token,
        expires_at=expires_at.isoformat()
    )


@router.get("/bootstrap-tokens")
async def list_bootstrap_tokens(
    db: Session = Depends(get_db)
):
    """List all bootstrap tokens"""
    tokens = db.query(BootstrapToken).all()

    return {
        "tokens": [
            {
                "created_at": t.created_at.isoformat() if t.created_at else None,
                "expires_at": t.expires_at.isoformat() if t.expires_at else None,
                "used_count": t.used_count,
                "max_uses": t.max_uses,
                "is_valid": t.is_valid()
            }
            for t in tokens
        ]
    }
