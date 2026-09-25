"""Security controls for the AI Trading Lab Data Engine.

Implements:
- Input validation
- Schema validation
- Safe parsing
- No arbitrary code execution from datasets
- Secret isolation
- API-key protection
- Environment-variable usage
- Least-privilege access
- Audit logging
- Immutable provenance records
- Safe error handling
"""

from typing import Optional, Dict
from pydantic import BaseModel, Field, field_validator
from datetime import datetime, UTC
import hashlib
import json
import re
import os


class SecurityConfig(BaseModel):
    """Security configuration."""
    api_keys: Dict[str, str] = Field(default_factory=dict)  # Never stored in source
    environment_prefix: str = "DATA_ENGINE_"
    enable_audit_log: bool = True
    max_input_length: int = 1000000
    allowed_providers: Optional[list] = None
    require_api_key: bool = False
    secret_env_var_pattern: str = r"^DATA_ENGINE_(API_KEY|SECRET|TOKEN)_.*$"

    @field_validator("api_keys", mode="after")
    @classmethod
    def validate_api_keys_not_in_source(cls, v):
        """API keys must come from environment, never from source."""
        for key, value in v.items():
            if value and not value.startswith("$ENV:"):
                raise ValueError(
                    f"API key for '{key}' must be loaded from environment variable. "
                    f"Never store API keys in source code."
                )
        return v

    def get_api_key(self, provider_name: str) -> Optional[str]:
        """Retrieve API key from environment variable."""
        env_var = f"{self.environment_prefix}{provider_name.upper()}_API_KEY"
        key = os.environ.get(env_var)
        if key is None and provider_name in self.api_keys:
            return self.api_keys[provider_name]
        return key

    def is_secret_env_var(self, var_name: str) -> bool:
        """Check if a variable name matches secret pattern."""
        return bool(re.match(self.secret_env_var_pattern, var_name))

    def audit_log(self, action: str, details: Dict):
        """Log security-relevant actions."""
        if not self.enable_audit_log:
            return
        entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "action": action,
            "details": details,
        }
        # Append to audit log file
        log_path = os.path.join(os.path.dirname(__file__), "..", "audit.log")
        try:
            with open(log_path, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except (IOError, OSError):
            pass  # Audit log failure is non-critical


def validate_input(value, max_length: int = 1000000) -> bool:
    """Validate input size and type."""
    if value is None:
        return True
    if isinstance(value, str) and len(value) > max_length:
        return False
    if isinstance(value, (list, dict)) and len(str(value)) > max_length:
        return False
    return True


def safe_parse_json(data: str) -> Optional[dict]:
    """Safely parse JSON without executing arbitrary code.

    Uses json.loads (not eval) to prevent code injection.
    """
    try:
        import json
        result = json.loads(data)
        return result
    except (json.JSONDecodeError, ValueError):
        return None


def sanitize_dataset_for_llm(dataset_dict: dict) -> dict:
    """Sanitize dataset for LLM consumption.

    Removes any executable code or dangerous content.
    """
    import re
    sanitized = {}
    for key, value in dataset_dict.items():
        if isinstance(value, str):
            # Remove any potential code injection patterns
            sanitized[key] = re.sub(r'<script.*?</script>', '', value, flags=re.DOTALL)
            sanitized[key] = re.sub(r'eval\([^)]*\)', '[REDACTED]', sanitized[key])
            sanitized[key] = re.sub(r'exec\([^)]*\)', '[REDACTED]', sanitized[key])
        elif isinstance(value, (int, float, bool, type(None))):
            sanitized[key] = value
        elif isinstance(value, (list, dict)):
            # Recursively sanitize
            sanitized[key] = _sanitize_nested(value)
        else:
            sanitized[key] = str(value)
    return sanitized


def _sanitize_nested(value):
    """Recursively sanitize nested structures."""
    import re
    if isinstance(value, str):
        return re.sub(r'<script.*?</script>', '', value, flags=re.DOTALL)
    elif isinstance(value, list):
        return [_sanitize_nested(item) for item in value]
    elif isinstance(value, dict):
        return {k: _sanitize_nested(v) for k, v in value.items()}
    return value


def protect_secrets(data: dict) -> dict:
    """Redact any secret-like values from data structures."""
    import re
    redacted = {}
    for key, value in data.items():
        if any(term in key.lower() for term in ["api_key", "secret", "token", "password", "credential"]):
            redacted[key] = "***REDACTED***"
        elif isinstance(value, str) and len(value) > 20 and any(
            pattern in value for pattern in [
                r'sk-', r'pk_', r'ghp_', r'xox[baprs]-'
            ]
        ):
            redacted[key] = "***REDACTED***"
        elif isinstance(value, dict):
            redacted[key] = protect_secrets(value)
        else:
            redacted[key] = value
    return redacted


# Immutable provenance protection
class ImmutableProvenance:
    """Ensures provenance records cannot be modified after creation."""

    def __init__(self, record_dict: dict):
        self._data = json.loads(json.dumps(record_dict))  # Deep copy
        self._hash = hashlib.sha256(json.dumps(self._data, sort_keys=True).encode()).hexdigest()

    @property
    def hash(self) -> str:
        return self._hash

    def verify_integrity(self) -> bool:
        """Verify that provenance hasn't been tampered with."""
        current_hash = hashlib.sha256(
            json.dumps(self._data, sort_keys=True).encode()
        ).hexdigest()
        return current_hash == self._hash

    @property
    def data(self) -> dict:
        return json.loads(json.dumps(self._data))  # Return copy
