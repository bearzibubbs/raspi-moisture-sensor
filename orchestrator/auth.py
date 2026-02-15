from fastapi import HTTPException, Security, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from datetime import datetime, timezone
from database import get_db
from models import Agent, BootstrapToken
import secrets

security = HTTPBearer()


def generate_agent_token() -> str:
    """Generate a new agent token"""
    return f"agt_{secrets.token_urlsafe(32)}"


async def verify_bootstrap_token(
    credentials: HTTPAuthorizationCredentials = Security(security),
    db: Session = Depends(get_db)
) -> BootstrapToken:
    """Verify bootstrap token for agent registration"""
    token = credentials.credentials

    # Hash the token to look up
    token_hash = BootstrapToken.hash_token(token)

    # Look up token in database
    bootstrap = db.query(BootstrapToken).filter_by(token_hash=token_hash).first()

    if not bootstrap:
        raise HTTPException(status_code=401, detail="Invalid bootstrap token")

    if not bootstrap.is_valid():
        raise HTTPException(status_code=401, detail="Bootstrap token expired or exhausted")

    return bootstrap


async def verify_agent_token(
    credentials: HTTPAuthorizationCredentials = Security(security),
    db: Session = Depends(get_db)
) -> Agent:
    """Verify agent token and return agent"""
    token = credentials.credentials

    # Find agent with matching token hash
    agents = db.query(Agent).all()

    for agent in agents:
        if Agent.verify_token(token, agent.agent_token_hash):
            return agent

    raise HTTPException(status_code=401, detail="Invalid agent token")
