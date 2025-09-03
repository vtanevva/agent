import logging
import time
from typing import Dict, Any
from datetime import datetime

from .database import get_db
from .config import Config

logger = logging.getLogger(__name__)

class HealthChecker:
    """Application health monitoring"""
    
    def __init__(self):
        self.start_time = time.time()
        self.db_manager = get_db()
    
    def check_database(self) -> Dict[str, Any]:
        """Check database connectivity and health"""
        try:
            if not self.db_manager.is_connected:
                return {
                    "status": "disconnected",
                    "message": "Database not configured or connection failed",
                    "timestamp": datetime.utcnow().isoformat()
                }
            
            # Perform health check
            if self.db_manager.health_check():
                return {
                    "status": "healthy",
                    "message": "Database connection is working",
                    "timestamp": datetime.utcnow().isoformat()
                }
            else:
                return {
                    "status": "unhealthy", 
                    "message": "Database health check failed",
                    "timestamp": datetime.utcnow().isoformat()
                }
                
        except Exception as e:
            logger.error(f"Database health check error: {e}")
            return {
                "status": "error",
                "message": f"Database health check failed: {str(e)}",
                "timestamp": datetime.utcnow().isoformat()
            }
    
    def check_openai(self) -> Dict[str, Any]:
        """Check OpenAI API connectivity"""
        try:
            import openai
            if not Config.OPENAI_API_KEY:
                return {
                    "status": "unconfigured",
                    "message": "OpenAI API key not configured",
                    "timestamp": datetime.utcnow().isoformat()
                }
            
            # Simple test - this would need to be implemented based on your OpenAI usage
            return {
                "status": "configured",
                "message": "OpenAI API key is configured",
                "timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"OpenAI health check error: {e}")
            return {
                "status": "error",
                "message": f"OpenAI health check failed: {str(e)}",
                "timestamp": datetime.utcnow().isoformat()
            }
    
    def check_pinecone(self) -> Dict[str, Any]:
        """Check Pinecone connectivity"""
        try:
            if not Config.PINECONE_API_KEY:
                return {
                    "status": "unconfigured",
                    "message": "Pinecone API key not configured",
                    "timestamp": datetime.utcnow().isoformat()
                }
            
            # Simple test - this would need to be implemented based on your Pinecone usage
            return {
                "status": "configured",
                "message": "Pinecone API key is configured",
                "timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Pinecone health check error: {e}")
            return {
                "status": "error",
                "message": f"Pinecone health check failed: {str(e)}",
                "timestamp": datetime.utcnow().isoformat()
            }
    
    def get_system_info(self) -> Dict[str, Any]:
        """Get system information"""
        import psutil
        
        return {
            "uptime_seconds": time.time() - self.start_time,
            "memory_usage_percent": psutil.virtual_memory().percent,
            "cpu_usage_percent": psutil.cpu_percent(),
            "python_version": f"{psutil.sys.version_info.major}.{psutil.sys.version_info.minor}.{psutil.sys.version_info.micro}",
            "environment": Config.FLASK_ENV,
            "timestamp": datetime.utcnow().isoformat()
        }
    
    def get_full_health_status(self) -> Dict[str, Any]:
        """Get comprehensive health status"""
        health_status = {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "version": "1.0.0",
            "checks": {
                "database": self.check_database(),
                "openai": self.check_openai(),
                "pinecone": self.check_pinecone(),
                "system": self.get_system_info()
            }
        }
        
        # Determine overall status
        unhealthy_checks = [
            check for check in health_status["checks"].values()
            if check.get("status") in ["unhealthy", "error"]
        ]
        
        if unhealthy_checks:
            health_status["status"] = "unhealthy"
            health_status["message"] = f"{len(unhealthy_checks)} service(s) are unhealthy"
        else:
            health_status["message"] = "All services are healthy"
        
        return health_status

# Global health checker instance
health_checker = HealthChecker()

def get_health_status() -> Dict[str, Any]:
    """Get current health status"""
    return health_checker.get_full_health_status()
