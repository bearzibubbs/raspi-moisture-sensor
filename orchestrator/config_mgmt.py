import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from database import get_db
from models import Agent, AgentConfig
from auth import verify_agent_token

logger = logging.getLogger(__name__)
router = APIRouter(tags=["config"])


# Request/Response models
class ConfigResponse(BaseModel):
    version: int
    config: Dict[str, Any]


class UpdateConfigRequest(BaseModel):
    config: Dict[str, Any]


@router.get("/agents/{agent_id}/config", response_model=ConfigResponse)
async def get_agent_config(
    agent_id: str,
    agent: Agent = Depends(verify_agent_token),
    db: Session = Depends(get_db)
):
    """Get configuration for agent (pull-based model)"""

    # Verify agent_id matches token
    if agent.agent_id != agent_id:
        raise HTTPException(status_code=403, detail="Agent ID mismatch")

    # Check if there's a config update available
    if agent.applied_config_version >= agent.desired_config_version:
        # No update needed
        raise HTTPException(status_code=304, detail="Config up to date")

    # Get latest config for this agent
    latest_config = db.query(AgentConfig).filter(
        AgentConfig.agent_id == agent_id,
        AgentConfig.version == agent.desired_config_version
    ).first()

    if not latest_config:
        # No config exists, return default
        logger.warning(f"No config found for {agent_id}, returning default")
        return ConfigResponse(
            version=1,
            config={}
        )

    logger.info(f"Config pulled by {agent_id}, version {latest_config.version}")

    return ConfigResponse(
        version=latest_config.version,
        config=latest_config.config_data
    )


@router.put("/agents/{agent_id}/config")
async def update_agent_config(
    agent_id: str,
    request: UpdateConfigRequest,
    db: Session = Depends(get_db)
):
    """Update agent configuration (admin only - no auth for now)"""

    # Get agent
    agent = db.query(Agent).filter_by(agent_id=agent_id).first()

    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    # Get current version
    current = db.query(AgentConfig).filter(
        AgentConfig.agent_id == agent_id
    ).order_by(AgentConfig.version.desc()).first()

    new_version = (current.version + 1) if current else 1

    # Create new config version
    new_config = AgentConfig(
        agent_id=agent_id,
        version=new_version,
        config_data=request.config
    )

    db.add(new_config)

    # Update agent desired version
    agent.desired_config_version = new_version

    db.commit()

    logger.info(f"Config updated for {agent_id}, new version: {new_version}")

    return {
        "version": new_version,
        "status": "updated"
    }


@router.post("/agents/{agent_id}/config/applied")
async def report_config_applied(
    agent_id: str,
    version: int,
    agent: Agent = Depends(verify_agent_token),
    db: Session = Depends(get_db)
):
    """Agent reports that it has applied a config version"""

    # Verify agent_id matches token
    if agent.agent_id != agent_id:
        raise HTTPException(status_code=403, detail="Agent ID mismatch")

    # Update applied version
    agent.applied_config_version = version

    # Update config record
    config = db.query(AgentConfig).filter(
        AgentConfig.agent_id == agent_id,
        AgentConfig.version == version
    ).first()

    if config:
        config.applied_at = datetime.now(timezone.utc)

    db.commit()

    logger.info(f"Config version {version} applied by {agent_id}")

    return {"status": "ok"}
