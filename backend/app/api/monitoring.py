from fastapi import APIRouter
import psutil
import shutil
import sqlite3
import os
from ..services.memory_service import MemoryService

router = APIRouter()
memory_service = MemoryService()

@router.get("/health")
def health_check():
    """Basic Liveness Probe."""
    return {"status": "ok"}

@router.get("/metrics")
def get_metrics():
    """Production Observability Endpoint (Prometheus Style)."""
    metrics = {}
    
    # 1. System Vital Signs
    mem = psutil.virtual_memory()
    disk = shutil.disk_usage("/")
    
    metrics["system_cpu_percent"] = psutil.cpu_percent()
    metrics["system_memory_percent"] = mem.percent
    metrics["system_disk_free_gb"] = round(disk.free / (1024**3), 2)
    
    # 2. Database Health
    db_size = os.path.getsize("data/orion.db") / (1024*1024) # MB
    wal_size = 0
    if os.path.exists("data/orion.db-wal"):
        wal_size = os.path.getsize("data/orion.db-wal") / (1024*1024)
        
    metrics["db_size_mb"] = round(db_size, 2)
    metrics["db_wal_size_mb"] = round(wal_size, 2)
    
    # Check DB Connectivity
    try:
        with sqlite3.connect("data/orion.db") as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT count(*) FROM conversation_history")
            metrics["db_rows_history"] = cursor.fetchone()[0]
            metrics["db_status"] = 1 # Healthy
    except Exception:
        metrics["db_status"] = 0 # Corrupted/Locked
        
    # 3. Basic Alerting (Self-Diagnosis)
    alerts = []
    if metrics["system_disk_free_gb"] < 1.0:
        alerts.append("CRITICAL: Disk Space Low (< 1GB)")
    if metrics["db_status"] == 0:
        alerts.append("CRITICAL: Database Locked/Corrupt")
    if metrics["db_wal_size_mb"] > metrics["db_size_mb"]:
        alerts.append("WARNING: WAL file larger than DB (Checkpoint needed)")
        
    metrics["alerts"] = alerts
    metrics["status"] = "unhealthy" if alerts else "healthy"

    return metrics
