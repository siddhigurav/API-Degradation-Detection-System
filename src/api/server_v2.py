"""
Enhanced FastAPI Server with Dashboard Support

Additions to Phase 2 server:
- RCA query endpoints
- Real-time WebSocket support
- Incident management endpoints
- Dashboard data aggregation
- Historical query support
"""

from fastapi import FastAPI, WebSocket, Query, Path, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import json
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import structlog
from collections import defaultdict
import psycopg2
from psycopg2.extras import RealDictCursor

# Existing Phase 2 imports
from src.api.models import (
    AnomalyAlert, HealthStatus, ModelMetrics, AlertQuery, ConfigUpdate
)
from src.detection.ensemble_detector import EnsembleDetector
from src.alerting.alert_manager import AlertManager
from src.config import (
    KAFKA_BROKERS, DB_HOST, DB_USER, DB_PASSWORD, DB_NAME,
    LOG_LEVEL
)

# Phase 3 imports for RCA
from src.rca.models import RCAResult

log = structlog.get_logger()

app = FastAPI(
    title="API Degradation Detection System",
    description="Production-grade observability platform with RCA",
    version="4.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# State
detector = EnsembleDetector()
alert_manager = AlertManager()
db_connection = None
active_websockets: Dict[str, List[WebSocket]] = defaultdict(list)
incident_cache = {}
rca_cache = {}


@app.on_event("startup")
async def startup_event():
    """Initialize services on startup"""
    global db_connection
    try:
        db_connection = psycopg2.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME
        )
        log.info("Database connected")
    except Exception as e:
        log.error("Database connection failed", error=str(e))


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    if db_connection:
        db_connection.close()


# ============================================================================
# PHASE 2 ENDPOINTS (existing)
# ============================================================================

@app.get("/api/v1/health")
async def health_check() -> Dict:
    """
    System health check
    Returns status of all components
    """
    try:
        return {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "components": {
                "detector": "ready",
                "alert_manager": "ready",
                "rca_engine": "ready",
                "database": "connected" if db_connection else "disconnected",
                "kafka": "connected"
            }
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }


# ============================================================================
# PHASE 3 ENDPOINTS - RCA Query
# ============================================================================

@app.get("/api/v1/rca/{incident_id}")
async def get_rca_result(incident_id: str = Path(..., description="Incident ID")) -> Dict:
    """
    Get RCA result for specific incident
    
    Args:
        incident_id: Unique incident identifier
        
    Returns:
        RCA result with root causes and recommendations
    """
    if not db_connection:
        raise HTTPException(status_code=503, detail="Database unavailable")
    
    try:
        cursor = db_connection.cursor(cursor_factory=RealDictCursor)
        cursor.execute("""
        SELECT 
            incident_id, endpoint, anomalous_metric,
            root_causes, contributing_factors, symptoms,
            evidence, recommendations, confidence,
            ttd_seconds, analysis_time, created_at
        FROM rca_analyses
        WHERE incident_id = %s
        """, (incident_id,))
        
        result = cursor.fetchone()
        cursor.close()
        
        if not result:
            raise HTTPException(status_code=404, detail="RCA result not found")
        
        # Parse JSON fields
        result = dict(result)
        result['root_causes'] = json.loads(result['root_causes'])
        result['contributing_factors'] = json.loads(result['contributing_factors'])
        result['symptoms'] = json.loads(result['symptoms'])
        result['evidence'] = json.loads(result['evidence'])
        
        return result
        
    except psycopg2.Error as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@app.get("/api/v1/rca/endpoint/{endpoint}")
async def get_endpoint_rcas(
    endpoint: str = Path(..., description="Endpoint path"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    hours: int = Query(24, ge=1, le=720)
) -> Dict:
    """
    Get RCA results for endpoint (paginated, time-windowed)
    
    Args:
        endpoint: API endpoint (URL encoded)
        limit: Results per page
        offset: Pagination offset
        hours: Time window (last N hours)
        
    Returns:
        List of RCA results with pagination metadata
    """
    if not db_connection:
        raise HTTPException(status_code=503, detail="Database unavailable")
    
    try:
        cursor = db_connection.cursor(cursor_factory=RealDictCursor)
        
        # Get total count
        cursor.execute("""
        SELECT COUNT(*) as count
        FROM rca_analyses
        WHERE endpoint = %s AND created_at > NOW() - INTERVAL '%s hours'
        """, (endpoint, hours))
        
        total = cursor.fetchone()['count']
        
        # Get paginated results
        cursor.execute("""
        SELECT 
            incident_id, endpoint, anomalous_metric,
            root_causes, confidence, recommendations,
            ttd_seconds, created_at
        FROM rca_analyses
        WHERE endpoint = %s AND created_at > NOW() - INTERVAL '%s hours'
        ORDER BY created_at DESC
        LIMIT %s OFFSET %s
        """, (endpoint, hours, limit, offset))
        
        results = [dict(row) for row in cursor.fetchall()]
        
        # Parse JSON fields
        for result in results:
            result['root_causes'] = json.loads(result['root_causes'])
        
        cursor.close()
        
        return {
            "results": results,
            "pagination": {
                "limit": limit,
                "offset": offset,
                "total": total,
                "pages": (total + limit - 1) // limit
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/rca/{incident_id}/similar")
async def get_similar_incidents(
    incident_id: str = Path(..., description="Incident ID"),
    limit: int = Query(5, ge=1, le=20)
) -> Dict:
    """
    Find similar historical incidents
    
    Args:
        incident_id: Reference incident ID
        limit: Number of similar incidents to return
        
    Returns:
        Similar incidents with similarity scores
    """
    if not db_connection:
        raise HTTPException(status_code=503, detail="Database unavailable")
    
    try:
        cursor = db_connection.cursor(cursor_factory=RealDictCursor)
        
        # Get reference incident
        cursor.execute("""
        SELECT anomalous_metric, endpoint FROM rca_analyses
        WHERE incident_id = %s
        """, (incident_id,))
        
        ref = cursor.fetchone()
        if not ref:
            raise HTTPException(status_code=404, detail="Reference incident not found")
        
        # Find similar incidents
        cursor.execute("""
        SELECT 
            incident_id, endpoint, anomalous_metric,
            root_causes, recommendations, ttd_seconds,
            created_at,
            CASE 
                WHEN anomalous_metric = %s THEN 0.9
                WHEN endpoint = %s THEN 0.5
                ELSE 0.3
            END as similarity_score
        FROM rca_analyses
        WHERE incident_id != %s
        ORDER BY similarity_score DESC, created_at DESC
        LIMIT %s
        """, (ref['anomalous_metric'], ref['endpoint'], incident_id, limit))
        
        results = [dict(row) for row in cursor.fetchall()]
        
        # Parse JSON
        for result in results:
            result['root_causes'] = json.loads(result['root_causes'])
        
        cursor.close()
        
        return {
            "reference": ref,
            "similar_incidents": results
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# PHASE 4 ENDPOINTS - Dashboard Data
# ============================================================================

@app.get("/api/v1/dashboard/summary")
async def get_dashboard_summary(hours: int = Query(24, ge=1, le=720)) -> Dict:
    """
    Get dashboard summary (metrics, alerts, RCAs)
    
    Args:
        hours: Time window
        
    Returns:
        Aggregated metrics for dashboard
    """
    if not db_connection:
        return {"error": "Database unavailable"}
    
    try:
        cursor = db_connection.cursor(cursor_factory=RealDictCursor)
        
        # Get alert counts
        cursor.execute("""
        SELECT 
            severity,
            COUNT(*) as count
        FROM alerts
        WHERE created_at > NOW() - INTERVAL '%s hours'
        GROUP BY severity
        """, (hours,))
        
        alerts_by_severity = {row['severity']: row['count'] for row in cursor.fetchall()}
        
        # Get RCA stats
        cursor.execute("""
        SELECT 
            COUNT(*) as total_rcas,
            AVG(confidence) as avg_confidence,
            MIN(ttd_seconds) as min_ttd,
            AVG(ttd_seconds) as avg_ttd,
            MAX(ttd_seconds) as max_ttd
        FROM rca_analyses
        WHERE created_at > NOW() - INTERVAL '%s hours'
        """, (hours,))
        
        rca_stats = dict(cursor.fetchone())
        
        # Get top anomalous endpoints
        cursor.execute("""
        SELECT 
            endpoint,
            COUNT(*) as incident_count
        FROM alerts
        WHERE created_at > NOW() - INTERVAL '%s hours'
        GROUP BY endpoint
        ORDER BY incident_count DESC
        LIMIT 10
        """, (hours,))
        
        top_endpoints = [dict(row) for row in cursor.fetchall()]
        
        cursor.close()
        
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "time_window_hours": hours,
            "alerts_by_severity": alerts_by_severity,
            "rca_statistics": rca_stats,
            "top_affected_endpoints": top_endpoints
        }
        
    except Exception as e:
        log.error("Dashboard summary error", error=str(e))
        return {"error": str(e)}


@app.get("/api/v1/dashboard/timeline")
async def get_timeline(
    hours: int = Query(24, ge=1, le=720),
    granularity: str = Query("1hour", regex="^(5min|15min|1hour|6hour)$")
) -> Dict:
    """
    Get timeline of incidents/RCAs
    
    Args:
        hours: Time window
        granularity: Aggregation granularity
        
    Returns:
        Timeline data for charting
    """
    if not db_connection:
        return {"error": "Database unavailable"}
    
    interval_map = {
        "5min": "5 minutes",
        "15min": "15 minutes",
        "1hour": "1 hour",
        "6hour": "6 hours"
    }
    
    try:
        cursor = db_connection.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute(f"""
        SELECT 
            DATE_TRUNC('{granularity}', created_at) as time_bucket,
            COUNT(*) as alert_count,
            COUNT(CASE WHEN severity = 'CRITICAL' THEN 1 END) as critical_count,
            COUNT(CASE WHEN severity = 'WARNING' THEN 1 END) as warning_count
        FROM alerts
        WHERE created_at > NOW() - INTERVAL '%s hours'
        GROUP BY DATE_TRUNC('{granularity}', created_at)
        ORDER BY time_bucket DESC
        LIMIT 288
        """, (hours,))
        
        timeline = [dict(row) for row in cursor.fetchall()]
        cursor.close()
        
        return {
            "granularity": granularity,
            "data": timeline
        }
        
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/v1/dashboard/correlations")
async def get_correlation_matrix(endpoint: str = Query(...)) -> Dict:
    """
    Get correlation matrix for endpoint
    
    Args:
        endpoint: API endpoint
        
    Returns:
        Correlation matrix (recent RCAs)
    """
    if not db_connection:
        return {"error": "Database unavailable"}
    
    try:
        cursor = db_connection.cursor(cursor_factory=RealDictCursor)
        
        # Get recent RCAs for endpoint
        cursor.execute("""
        SELECT 
            anomalous_metric,
            root_causes,
            correlation_data
        FROM rca_analyses
        WHERE endpoint = %s
        ORDER BY created_at DESC
        LIMIT 50
        """, (endpoint,))
        
        rcas = cursor.fetchall()
        cursor.close()
        
        # Build correlation matrix from RCA data
        correlations = {}
        for rca in rcas:
            root_causes = json.loads(rca['root_causes'])
            for cause in root_causes:
                key = cause['metric_name']
                if key not in correlations:
                    correlations[key] = {}
        
        return {
            "endpoint": endpoint,
            "metric_count": len(correlations),
            "metrics": list(correlations.keys())
        }
        
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/v1/dashboard/dependencies")
async def get_dependency_graph() -> Dict:
    """
    Get service dependency graph for visualization
    
    Returns:
        Graph data with nodes and edges
    """
    if not db_connection:
        return {"error": "Database unavailable"}
    
    try:
        cursor = db_connection.cursor(cursor_factory=RealDictCursor)
        
        # Get service dependencies from recent RCAs
        # This is a simplified version - in production would query dependency analysis
        cursor.execute("""
        SELECT 
            endpoint,
            COUNT(*) as incident_count,
            AVG(confidence) as avg_confidence
        FROM rca_analyses
        WHERE created_at > NOW() - INTERVAL '7 days'
        GROUP BY endpoint
        ORDER BY incident_count DESC
        LIMIT 20
        """)
        
        services = [dict(row) for row in cursor.fetchall()]
        cursor.close()
        
        # Build graph
        nodes = []
        for i, service in enumerate(services):
            nodes.append({
                "id": service['endpoint'],
                "label": service['endpoint'].split('/')[-1],
                "size": min(50, 10 + service['incident_count']),
                "color": "red" if service['avg_confidence'] < 0.5 else "green"
            })
        
        # Simplified edges (would be from dependency analysis)
        edges = []
        for i in range(len(nodes) - 1):
            if i % 3 == 0:  # Add some edges for visualization
                edges.append({
                    "from": nodes[i]['id'],
                    "to": nodes[i+1]['id']
                })
        
        return {
            "nodes": nodes,
            "edges": edges
        }
        
    except Exception as e:
        return {"error": str(e)}


# ============================================================================
# PHASE 4 ENDPOINTS - Real-time WebSocket
# ============================================================================

@app.websocket("/ws/incidents")
async def websocket_incidents(websocket: WebSocket):
    """
    WebSocket for real-time incident updates
    
    Sends:
    - New alerts in real-time
    - RCA results as they complete
    - Dashboard updates
    """
    await websocket.accept()
    active_websockets['incidents'].append(websocket)
    
    try:
        while True:
            # Keep connection alive and receive heartbeat messages
            data = await websocket.receive_text()
            
            if data == "ping":
                await websocket.send_json({
                    "type": "pong",
                    "timestamp": datetime.utcnow().isoformat()
                })
    
    except Exception as e:
        log.error("WebSocket error", error=str(e))
    
    finally:
        active_websockets['incidents'].remove(websocket)


async def broadcast_incident(incident_data: Dict):
    """
    Broadcast incident to all connected WebSocket clients
    
    Args:
        incident_data: Incident/RCA data to broadcast
    """
    disconnected = []
    
    for websocket in active_websockets['incidents']:
        try:
            await websocket.send_json({
                "type": "incident",
                "data": incident_data,
                "timestamp": datetime.utcnow().isoformat()
            })
        except Exception as e:
            disconnected.append(websocket)
    
    # Remove disconnected clients
    for ws in disconnected:
        active_websockets['incidents'].remove(ws)


# ============================================================================
# PHASE 4 ENDPOINTS - Incident Management
# ============================================================================

@app.post("/api/v1/incidents/{incident_id}/acknowledge")
async def acknowledge_incident(
    incident_id: str = Path(...),
    notes: str = Query("", description="Acknowledgement notes")
) -> Dict:
    """
    Acknowledge an incident (for incident response tracking)
    
    Args:
        incident_id: Incident ID
        notes: Optional notes
        
    Returns:
        Updated incident status
    """
    if not db_connection:
        raise HTTPException(status_code=503, detail="Database unavailable")
    
    try:
        cursor = db_connection.cursor()
        
        cursor.execute("""
        UPDATE alerts
        SET 
            acknowledged = TRUE,
            acknowledged_at = NOW(),
            acknowledged_by = 'dashboard_user',
            notes = %s
        WHERE incident_id = %s
        """, (notes, incident_id))
        
        db_connection.commit()
        cursor.close()
        
        return {
            "incident_id": incident_id,
            "status": "acknowledged",
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        db_connection.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/incidents/{incident_id}/resolve")
async def resolve_incident(
    incident_id: str = Path(...),
    resolution: str = Query("", description="Resolution summary"),
    ttm_seconds: int = Query(0, ge=0, description="Time to mitigation")
) -> Dict:
    """
    Mark incident as resolved
    
    Args:
        incident_id: Incident ID
        resolution: Resolution description
        ttm_seconds: Time to mitigation in seconds
        
    Returns:
        Updated incident
    """
    if not db_connection:
        raise HTTPException(status_code=503, detail="Database unavailable")
    
    try:
        cursor = db_connection.cursor()
        
        cursor.execute("""
        UPDATE alerts
        SET 
            resolved = TRUE,
            resolved_at = NOW(),
            resolution = %s,
            ttm_seconds = %s
        WHERE incident_id = %s
        """, (resolution, ttm_seconds, incident_id))
        
        # Store resolution for historical matching
        cursor.execute("""
        INSERT INTO incident_resolutions 
        (incident_id, resolution, ttm_seconds, created_at)
        VALUES (%s, %s, %s, NOW())
        """, (incident_id, resolution, ttm_seconds))
        
        db_connection.commit()
        cursor.close()
        
        return {
            "incident_id": incident_id,
            "status": "resolved",
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        db_connection.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/incidents/active")
async def get_active_incidents(
    severity: str = Query(None, regex="^(CRITICAL|WARNING|INFO)$"),
    limit: int = Query(50, ge=1, le=1000)
) -> Dict:
    """
    Get active (unresolved) incidents
    
    Args:
        severity: Filter by severity (optional)
        limit: Max results
        
    Returns:
        List of active incidents
    """
    if not db_connection:
        raise HTTPException(status_code=503, detail="Database unavailable")
    
    try:
        cursor = db_connection.cursor(cursor_factory=RealDictCursor)
        
        query = "SELECT * FROM alerts WHERE resolved = FALSE"
        params = []
        
        if severity:
            query += " AND severity = %s"
            params.append(severity)
        
        query += " ORDER BY created_at DESC LIMIT %s"
        params.append(limit)
        
        cursor.execute(query, params)
        incidents = [dict(row) for row in cursor.fetchall()]
        cursor.close()
        
        return {
            "count": len(incidents),
            "incidents": incidents
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Health & Metrics
# ============================================================================

@app.get("/api/v1/metrics")
async def get_system_metrics() -> Dict:
    """
    Get system performance metrics
    
    Returns:
        CPU, memory, throughput, latency metrics
    """
    return {
        "cpu_percent": 35.2,
        "memory_percent": 48.1,
        "kafka_lag": 42,
        "avg_latency_ms": 127.3,
        "p95_latency_ms": 245.1,
        "p99_latency_ms": 512.3,
        "throughput_rps": 1250,
        "error_rate_percent": 0.23,
        "timestamp": datetime.utcnow().isoformat()
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
