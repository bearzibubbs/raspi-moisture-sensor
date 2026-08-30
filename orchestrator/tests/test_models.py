from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base
from models import Agent


def make_session():
    # StaticPool keeps a single persistent sqlite connection alive for the
    # life of the engine, which we need so the ATTACHed "public" schema
    # (models.py declares __table_args__ = {"schema": "public"}) survives
    # across the create_all() and session calls below.
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _attach_public_schema(dbapi_conn, connection_record):
        dbapi_conn.execute("ATTACH DATABASE ':memory:' AS public")

    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def _make_agent(session, agent_id="pi-test-01"):
    agent = Agent(
        agent_id=agent_id,
        hostname="test-host",
        agent_token_hash="hash",
    )
    session.add(agent)
    session.commit()
    return agent


def test_agent_metadata_in_place_mutation_persists():
    """Regression test for #2: mutating agent_metadata in place (as
    ingestion.report_health does on the second+ call for an agent) must
    be picked up by SQLAlchemy's unit-of-work and persisted on commit."""
    session = make_session()
    agent = _make_agent(session)

    # First report: assigns a new dict (always worked)
    agent.agent_metadata = {"health": {"uptime_seconds": 1}}
    session.commit()

    # Second report: mutates the existing dict in place, like ingestion.py does
    agent.agent_metadata["health"] = {"uptime_seconds": 2}
    session.commit()

    session.expire_all()
    reloaded = session.get(Agent, agent.agent_id)
    assert reloaded.agent_metadata["health"]["uptime_seconds"] == 2
