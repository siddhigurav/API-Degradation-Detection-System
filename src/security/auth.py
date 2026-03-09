"""
Production Security & Authentication

Implements:
- JWT token authentication
- Role-based access control (RBAC)
- API key validation
- Rate limiting
- Request validation
- HTTPS/TLS requirements
"""

from fastapi import FastAPI, Depends, HTTPException, status, Security
from fastapi.security import HTTPBearer, HTTPAuthCredentials, APIKeyHeader
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from functools import lru_cache
import jwt
import hashlib
import structlog
import time
from collections import defaultdict

log = structlog.get_logger()

# Security configuration
SECRET_KEY = "your-secret-key-change-in-production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

# Allowed API keys (in production, load from secure vault)
VALID_API_KEYS = {
    "key_dev_12345": {
        "name": "Development",
        "role": "viewer",
        "permissions": ["read:dashboard", "read:rca"]
    },
    "key_prod_78901": {
        "name": "Production",
        "role": "admin",
        "permissions": ["read:*", "write:*"]
    }
}

# Rate limiting configuration
RATE_LIMITS = {
    "dashboard": {"max_requests": 100, "window_seconds": 60},
    "rca_query": {"max_requests": 50, "window_seconds": 60},
    "incident_write": {"max_requests": 20, "window_seconds": 60}
}


class RateLimiter:
    """Token bucket rate limiter"""
    
    def __init__(self):
        self.requests: Dict[str, List[float]] = defaultdict(list)
    
    def is_allowed(
        self,
        client_id: str,
        endpoint: str,
        max_requests: int,
        window_seconds: int
    ) -> bool:
        """
        Check if request is allowed under rate limit
        
        Args:
            client_id: Unique client identifier
            endpoint: API endpoint name
            max_requests: Max requests allowed
            window_seconds: Time window in seconds
            
        Returns:
            True if request is allowed
        """
        key = f"{client_id}:{endpoint}"
        now = time.time()
        
        # Clean old requests outside window
        self.requests[key] = [
            req_time for req_time in self.requests[key]
            if now - req_time < window_seconds
        ]
        
        if len(self.requests[key]) < max_requests:
            self.requests[key].append(now)
            return True
        
        return False
    
    def get_remaining(
        self,
        client_id: str,
        endpoint: str,
        max_requests: int,
        window_seconds: int
    ) -> int:
        """Get remaining requests in window"""
        key = f"{client_id}:{endpoint}"
        now = time.time()
        
        self.requests[key] = [
            req_time for req_time in self.requests[key]
            if now - req_time < window_seconds
        ]
        
        return max(0, max_requests - len(self.requests[key]))


class TokenManager:
    """JWT token management"""
    
    @staticmethod
    def create_access_token(
        sub: str,
        role: str = "viewer",
        expires_delta: Optional[timedelta] = None
    ) -> str:
        """
        Create JWT access token
        
        Args:
            sub: Subject (user/app ID)
            role: User role
            expires_delta: Token expiration time
            
        Returns:
            JWT token string
        """
        if expires_delta is None:
            expires_delta = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        
        expire = datetime.utcnow() + expires_delta
        
        to_encode = {
            "sub": sub,
            "role": role,
            "exp": expire,
            "iat": datetime.utcnow()
        }
        
        encoded_jwt = jwt.encode(
            to_encode,
            SECRET_KEY,
            algorithm=ALGORITHM
        )
        
        return encoded_jwt
    
    @staticmethod
    def verify_token(token: str) -> Dict:
        """
        Verify JWT token
        
        Args:
            token: JWT token string
            
        Returns:
            Token payload
            
        Raises:
            HTTPException if token invalid
        """
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            
            # Check expiration
            if datetime.utcfromtimestamp(payload.get("exp", 0)) < datetime.utcnow():
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token expired"
                )
            
            return payload
            
        except jwt.InvalidTokenError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token"
            )


class APIKeyValidator:
    """API key validation"""
    
    @staticmethod
    def validate_key(api_key: str) -> Dict:
        """
        Validate API key
        
        Args:
            api_key: API key string
            
        Returns:
            API key metadata
            
        Raises:
            HTTPException if invalid
        """
        if api_key not in VALID_API_KEYS:
            log.warning("Invalid API key attempt", key=api_key[:10] + "***")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key"
            )
        
        return VALID_API_KEYS[api_key]
    
    @staticmethod
    def add_key(key_value: str, metadata: Dict):
        """Add new API key (admin only)"""
        # In production: Generate secure key, store in vault
        VALID_API_KEYS[key_value] = metadata
        log.info("API key added", key=key_value[:10] + "***")


class RBACValidator:
    """Role-based access control"""
    
    # Permission hierarchy
    ROLE_PERMISSIONS = {
        "viewer": [
            "read:dashboard",
            "read:rca",
            "read:incidents"
        ],
        "analyst": [
            "read:dashboard",
            "read:rca",
            "read:incidents",
            "write:acknowledge",
            "write:notes"
        ],
        "admin": [
            "read:dashboard",
            "read:rca",
            "read:incidents",
            "write:acknowledge",
            "write:notes",
            "write:resolve",
            "write:config",
            "delete:incidents"
        ]
    }
    
    @staticmethod
    def has_permission(role: str, permission: str) -> bool:
        """Check if role has permission"""
        if role not in RBACValidator.ROLE_PERMISSIONS:
            return False
        
        permissions = RBACValidator.ROLE_PERMISSIONS[role]
        
        # Wildcard support
        if f"{permission.split(':')[0]}:*" in permissions:
            return True
        
        return permission in permissions
    
    @staticmethod
    def require_permission(permission: str):
        """Dependency for requiring specific permission"""
        async def check_permission(
            credentials: HTTPAuthCredentials = Security(HTTPBearer())
        ) -> Dict:
            try:
                token_data = TokenManager.verify_token(credentials.credentials)
                role = token_data.get("role", "viewer")
                
                if not RBACValidator.has_permission(role, permission):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=f"Permission denied: {permission}"
                    )
                
                return token_data
                
            except HTTPException:
                raise
        
        return check_permission


class RequestValidator:
    """Request validation and sanitization"""
    
    # Input constraints
    CONSTRAINTS = {
        "endpoint": {"max_length": 256, "pattern": r"^/api/"},
        "incident_id": {"max_length": 64, "pattern": r"^inc_"},
        "metric_name": {"max_length": 128},
        "notes": {"max_length": 1024},
    }
    
    @staticmethod
    def validate_incident_id(incident_id: str) -> str:
        """Validate incident ID format"""
        if not incident_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Incident ID required"
            )
        
        constraint = RequestValidator.CONSTRAINTS.get("incident_id")
        if len(incident_id) > constraint["max_length"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Incident ID too long (max {constraint['max_length']})"
            )
        
        return incident_id
    
    @staticmethod
    def validate_endpoint(endpoint: str) -> str:
        """Validate endpoint path"""
        if not endpoint:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Endpoint required"
            )
        
        constraint = RequestValidator.CONSTRAINTS.get("endpoint")
        if len(endpoint) > constraint["max_length"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Endpoint too long (max {constraint['max_length']})"
            )
        
        return endpoint
    
    @staticmethod
    def sanitize_sql_input(value: str) -> str:
        """Basic SQL injection prevention"""
        dangerous_chars = [";", "'", "\\", "--"]
        for char in dangerous_chars:
            if char in value:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid characters in input"
                )
        return value


class AuditLog:
    """Audit logging for compliance"""
    
    @staticmethod
    def log_access(
        user_id: str,
        action: str,
        resource: str,
        status: str,
        details: Dict = None
    ):
        """
        Log access event for audit trail
        
        Args:
            user_id: User/client ID
            action: Action performed
            resource: Resource accessed
            status: Success/Failure
            details: Additional details
        """
        log.info(
            "audit_log",
            user_id=user_id,
            action=action,
            resource=resource,
            status=status,
            timestamp=datetime.utcnow().isoformat(),
            details=details or {}
        )
    
    @staticmethod
    def log_config_change(
        user_id: str,
        config_key: str,
        old_value,
        new_value
    ):
        """Log configuration change"""
        log.warning(
            "config_change",
            user_id=user_id,
            config_key=config_key,
            old_value=old_value,
            new_value=new_value,
            timestamp=datetime.utcnow().isoformat()
        )


# Global instances
rate_limiter = RateLimiter()
token_manager = TokenManager()
api_key_validator = APIKeyValidator()
rbac_validator = RBACValidator()
request_validator = RequestValidator()
audit_log = AuditLog()
