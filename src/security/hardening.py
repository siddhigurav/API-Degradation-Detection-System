"""
Environment & Configuration Hardening

Implements:
- Environment variable validation
- TLS/HTTPS configuration
- Secret management
- Configuration security
- Deployment security checklist
"""

import os
import logging
from typing import Dict, Optional, List
from pathlib import Path
from enum import Enum

log = logging.getLogger(__name__)


class Environment(str, Enum):
    """Deployment environment"""
    DEV = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class EnvironmentConfig:
    """Environment configuration with validation"""
    
    # Required env vars by environment
    REQUIRED_VARS = {
        Environment.DEV: [
            "API_PORT",
            "DATABASE_URL",
            "REDIS_URL",
        ],
        Environment.STAGING: [
            "API_PORT",
            "API_HOST",
            "DATABASE_URL",
            "DATABASE_POOL_SIZE",
            "REDIS_URL",
            "KAFKA_BROKERS",
            "SECRET_KEY",
            "JWT_ALGORITHM"
        ],
        Environment.PRODUCTION: [
            "API_PORT",
            "API_HOST",
            "DATABASE_URL",
            "DATABASE_POOL_SIZE",
            "DATABASE_TIMEOUT",
            "REDIS_URL",
            "REDIS_CLUSTER_ENABLED",
            "KAFKA_BROKERS",
            "SECRET_KEY",
            "JWT_ALGORITHM",
            "TLS_ENABLED",
            "TLS_CERT_PATH",
            "TLS_KEY_PATH",
            "VAULT_ADDR",
            "VAULT_TOKEN"
        ]
    }
    
    # Default values
    DEFAULTS = {
        "API_PORT": "8000",
        "API_HOST": "0.0.0.0",
        "API_TIMEOUT": "30",
        "DATABASE_POOL_SIZE": "20",
        "DATABASE_TIMEOUT": "10",
        "REDIS_POOL_SIZE": "50",
        "REDIS_CLUSTER_ENABLED": "false",
        "JWT_ALGORITHM": "HS256",
        "ACCESS_TOKEN_EXPIRE": "3600",
        "TLS_ENABLED": "false",
        "LOG_LEVEL": "INFO",
        "ENVIRONMENT": Environment.DEV.value
    }
    
    def __init__(self):
        """Load and validate environment"""
        self.env = os.getenv("ENVIRONMENT", Environment.DEV.value)
        self.validate()
    
    def validate(self):
        """Validate required variables"""
        try:
            env = Environment(self.env)
        except ValueError:
            raise ValueError(f"Invalid ENVIRONMENT: {self.env}")
        
        missing = []
        for var in self.REQUIRED_VARS[env]:
            if not os.getenv(var):
                missing.append(var)
        
        if missing:
            raise ValueError(
                f"Missing required environment variables: {', '.join(missing)}"
            )
        
        log.info(f"Environment validation passed for {env.value}")
    
    def get(self, key: str, default: str = None) -> str:
        """Get config value"""
        return os.getenv(key, default or self.DEFAULTS.get(key, ""))
    
    def get_int(self, key: str, default: int = None) -> int:
        """Get int config value"""
        value = self.get(key)
        if value:
            try:
                return int(value)
            except ValueError:
                if default is not None:
                    return default
                raise ValueError(f"Invalid int for {key}: {value}")
        return default or 0
    
    def get_bool(self, key: str, default: bool = False) -> bool:
        """Get bool config value"""
        value = self.get(key, str(default)).lower()
        return value in ("true", "1", "yes", "on")


class TLSConfig:
    """TLS/HTTPS configuration"""
    
    def __init__(self, config: EnvironmentConfig):
        self.config = config
        self.enabled = config.get_bool("TLS_ENABLED")
        self.cert_path = config.get("TLS_CERT_PATH")
        self.key_path = config.get("TLS_KEY_PATH")
        self.verify_client = config.get_bool("TLS_VERIFY_CLIENT", False)
    
    def validate(self) -> bool:
        """Validate TLS configuration"""
        if not self.enabled:
            log.info("TLS disabled")
            return True
        
        if not self.cert_path or not self.key_path:
            raise ValueError(
                "TLS_ENABLED but TLS_CERT_PATH or TLS_KEY_PATH not set"
            )
        
        cert_file = Path(self.cert_path)
        key_file = Path(self.key_path)
        
        if not cert_file.exists():
            raise ValueError(f"Certificate file not found: {self.cert_path}")
        
        if not key_file.exists():
            raise ValueError(f"Key file not found: {self.key_path}")
        
        # Check permissions (should not be world-readable)
        key_perms = oct(key_file.stat().st_mode)[-3:]
        if key_perms not in ("400", "600"):
            log.warning(f"Key file permissions may be too permissive: {key_perms}")
        
        log.info(f"TLS configuration valid")
        return True
    
    def get_ssl_context(self):
        """Get SSL context for HTTPS server"""
        if not self.enabled:
            return None
        
        import ssl
        
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(self.cert_path, self.key_path)
        
        # Security settings
        context.options |= ssl.OP_NO_TLSv1 | ssl.OP_NO_TLSv1_1  # Disable old protocols
        context.set_ciphers('ECDHE+AESGCM:ECDHE+CHACHA20:DHE+AESGCM:DHE+CHACHA20:!aNULL:!eNULL:!EXPORT:!DSS:!DES:!RC4:!3DES:!MD5:!PSK')
        
        if self.verify_client:
            context.verify_mode = ssl.CERT_REQUIRED
        
        return context


class SecretManager:
    """Secret management"""
    
    def __init__(self, config: EnvironmentConfig):
        self.config = config
        self.use_vault = config.get("VAULT_ADDR") is not None
        
        if self.use_vault:
            self._init_vault()
    
    def _init_vault(self):
        """Initialize Vault integration"""
        try:
            import hvac
            
            addr = self.config.get("VAULT_ADDR")
            token = self.config.get("VAULT_TOKEN")
            
            self.vault_client = hvac.Client(url=addr, token=token)
            self.vault_client.is_authenticated()
            
            log.info("Vault authentication successful")
        except Exception as e:
            log.error(f"Vault initialization failed: {e}")
            raise
    
    def get_secret(self, path: str, key: str = None) -> str:
        """Get secret from Vault or environment"""
        if self.use_vault:
            try:
                secret = self.vault_client.secrets.kv.read_secret_version(path)
                data = secret["data"]["data"]
                
                if key:
                    return data.get(key)
                return data
            except Exception as e:
                log.error(f"Failed to read secret from Vault: {e}")
                raise
        
        # Fallback to environment variable
        return os.getenv(key or path.upper().replace("/", "_"))
    
    def rotate_secret(self, path: str, new_value: str):
        """Rotate secret"""
        if self.use_vault:
            try:
                self.vault_client.secrets.kv.create_or_update_secret(
                    path=path,
                    secret_dict={"value": new_value}
                )
                log.info(f"Secret rotated: {path}")
            except Exception as e:
                log.error(f"Failed to rotate secret: {e}")
                raise


class DatabaseConfig:
    """Database configuration with security"""
    
    def __init__(self, config: EnvironmentConfig):
        self.config = config
        self.url = config.get("DATABASE_URL")
        self.pool_size = config.get_int("DATABASE_POOL_SIZE", 20)
        self.timeout = config.get_int("DATABASE_TIMEOUT", 10)
        self.ssl_mode = config.get("DATABASE_SSL_MODE", "require")
    
    def get_connection_string(self) -> str:
        """Get connection string with security params"""
        # Parse URL and add SSL settings
        if "?" in self.url:
            return f"{self.url}&sslmode={self.ssl_mode}"
        return f"{self.url}?sslmode={self.ssl_mode}"
    
    def get_pool_config(self) -> dict:
        """Get connection pool configuration"""
        return {
            "pool_size": self.pool_size,
            "max_overflow": int(self.pool_size * 0.5),
            "pool_timeout": self.timeout,
            "pool_recycle": 3600,  # Recycle connections hourly
            "echo": False,  # Disable SQL echo in production
        }


class ConfigValidator:
    """Overall configuration validation"""
    
    def __init__(self):
        self.config = EnvironmentConfig()
        self.tls_config = TLSConfig(self.config)
        self.db_config = DatabaseConfig(self.config)
        self.secret_manager = SecretManager(self.config)
    
    def validate_all(self) -> bool:
        """Run all validations"""
        checks = [
            ("Environment variables", self.config.validate),
            ("TLS configuration", self.tls_config.validate),
        ]
        
        results = []
        for name, check in checks:
            try:
                check()
                results.append((name, True, None))
                log.info(f"✓ {name}")
            except Exception as e:
                results.append((name, False, str(e)))
                log.error(f"✗ {name}: {e}")
        
        all_passed = all(passed for _, passed, _ in results)
        
        return all_passed
    
    def get_deployment_checklist(self) -> List[Dict]:
        """Get production deployment checklist"""
        env = self.config.env
        
        checklist = [
            {
                "category": "Infrastructure",
                "items": [
                    {"name": "Database backup enabled", "required": True},
                    {"name": "Database encryption at rest", "required": True},
                    {"name": "Redis cluster configured", "required": env == "production"},
                    {"name": "Kafka brokers redundant", "required": True},
                ]
            },
            {
                "category": "Security",
                "items": [
                    {"name": "TLS enabled", "required": env == "production"},
                    {"name": "Secrets in Vault", "required": env == "production"},
                    {"name": "API keys rotated", "required": True},
                    {"name": "Database credentials secure", "required": True},
                    {"name": "JWT secrets rotated", "required": env == "production"},
                ]
            },
            {
                "category": "Monitoring",
                "items": [
                    {"name": "Prometheus metrics exported", "required": True},
                    {"name": "Logging to ELK stack", "required": env in ("staging", "production")},
                    {"name": "Alerting configured", "required": env == "production"},
                    {"name": "Health check endpoints working", "required": True},
                ]
            },
            {
                "category": "Testing",
                "items": [
                    {"name": "Unit tests passing", "required": True},
                    {"name": "Integration tests passing", "required": True},
                    {"name": "Load tests completed", "required": env == "production"},
                    {"name": "Security audit completed", "required": env == "production"},
                ]
            },
            {
                "category": "Deployment",
                "items": [
                    {"name": "Deployment automation configured", "required": True},
                    {"name": "Rollback procedure documented", "required": True},
                    {"name": "Incident runbook prepared", "required": True},
                    {"name": "On-call rotation established", "required": env == "production"},
                ]
            }
        ]
        
        return checklist


class EnvironmentValidator:
    """High-level environment validator"""
    
    @staticmethod
    def validate_production() -> bool:
        """Validate production environment"""
        validator = ConfigValidator()
        
        if not validator.validate_all():
            log.error("Production environment validation failed")
            return False
        
        checklist = validator.get_deployment_checklist()
        
        # Check all required items
        for category in checklist:
            for item in category["items"]:
                if item.get("required"):
                    log.info(f"Production requirement: {item['name']}")
        
        log.info("Production environment validation passed")
        return True
    
    @staticmethod
    def get_security_report() -> dict:
        """Get security configuration report"""
        validator = ConfigValidator()
        
        return {
            "environment": validator.config.env,
            "tls_enabled": validator.tls_config.enabled,
            "vault_enabled": validator.secret_manager.use_vault,
            "database_ssl": validator.db_config.ssl_mode,
            "deployment_checklist": validator.get_deployment_checklist()
        }


# Initialize global config
config = EnvironmentConfig()
tls_config = TLSConfig(config)
db_config = DatabaseConfig(config)
secret_manager = SecretManager(config)
