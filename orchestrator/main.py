#!/usr/bin/env python3
"""
Orchestrator Service - Moisture Monitoring Fleet Management

Main entry point for the orchestrator service that manages Pi agents,
receives sensor data, and provides API endpoints for monitoring.
"""

import logging
import sys
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# Import database
from database import init_db

# Import routers
from agents import router as agents_router
from ingestion import router as ingestion_router, init_influx
from alerts import router as alerts_router
from config_mgmt import router as config_router

# Import InfluxDB writer
from influx import InfluxWriter

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Moisture Monitoring Orchestrator",
    version="1.0.0",
    description="Fleet management and data orchestration for Pi agents"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(agents_router)
app.include_router(ingestion_router)
app.include_router(alerts_router)
app.include_router(config_router)


@app.on_event("startup")
async def startup_event():
    """Initialize services on startup"""
    logger.info("Starting orchestrator service")

    # Initialize database
    logger.info("Initializing database")
    init_db()

    # Initialize InfluxDB writer
    logger.info("Initializing InfluxDB writer")
    influx_writer = InfluxWriter()
    init_influx(influx_writer)

    logger.info("Orchestrator service started successfully")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("Shutting down orchestrator service")


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "Moisture Monitoring Orchestrator",
        "version": "1.0.0",
        "status": "running"
    }


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "orchestrator"
    }


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        log_level="info",
        reload=False
    )
