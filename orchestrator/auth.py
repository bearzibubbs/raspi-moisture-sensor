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

    # Tokens are stored with bcrypt (random salt), so we must verify against each candidate
    candidates = db.query(BootstrapToken).all()
    for bootstrap in candidates:
        if BootstrapToken.verify_token(token, bootstrap.token_hash):
            if not bootstrap.is_valid():
                raise HTTPException(status_code=401, detail="Bootstrap token expired or exhausted")
            return bootstrap

    raise HTTPException(status_code=401, detail="Invalid bootstrap token")


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
