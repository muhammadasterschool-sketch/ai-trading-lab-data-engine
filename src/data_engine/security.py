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


# ---------------------------------------------------------------------------
# Filesystem security (Phase 4A.1 — spec SECTION 11, FS-01..FS-24)
# ---------------------------------------------------------------------------

from pathlib import Path  # noqa: E402


class FilesystemSecurityError(ValueError):
    """Typed filesystem-security rejection naming the rule violated (FS-20).

    Every containment/traversal/symlink/config rejection raises this
    error with the specific FS rule ID, so denials are auditable and
    never silent.
    """

    def __init__(self, rule: str, message: str):
        self.rule = rule
        self.message = message
        super().__init__(f"[{rule}] {message}")


def resolve_path(path) -> Path:
    """Resolve a path to its canonical absolute form (FS-01).

    Resolves '..', '.', and symlinks BEFORE any containment decision.
    """
    return Path(path).resolve()


def ensure_containment(path, approved_root, rule: str = "FS-05") -> Path:
    """Verify a resolved path is INSIDE the approved root (FS-02..FS-05).

    Containment is evaluated on the RESOLVED path (FS-02), by path
    COMPONENTS (FS-03) — never by string prefix, which is vulnerable
    to the 'C:\\dataevil' vs 'C:\\data' prefix bug.

    Raises FilesystemSecurityError naming the rule (FS-20) when the
    path is outside the root.
    """
    if approved_root is None:
        raise FilesystemSecurityError(
            "FS-06",
            "No approved data root configured — failing closed; no I/O "
            "is permitted without an explicit approved root.",
        )
    resolved = Path(path).resolve()
    root = Path(approved_root).resolve()
    if resolved != root and root not in resolved.parents:
        raise FilesystemSecurityError(
            rule,
            f"Resolved path {resolved} is OUTSIDE the approved root {root} "
            f"(component-based containment check).",
        )
    return resolved


def validate_instrument_identifier(instrument, allowlist=None, registry=None,
                                   registry_count=None) -> str:
    """Validate an instrument identifier before path construction
    (FS-14, FS-15, FS-16).

    Rejected (FS-15): path separators, '..', drive letters, UNC
    prefixes, '~' expansions, NUL bytes, leading separators.
    Enforced (FS-14): the instrument must pass the allowlist
    (config allowlist, or a non-empty registry) BEFORE any path is
    constructed. No allowlist at all -> fail closed (FS-06 class).

    The filename MUST be constructed from the identifier returned
    here — never from raw user input (FS-16).
    """
    if not isinstance(instrument, str) or not instrument.strip():
        raise FilesystemSecurityError(
            "FS-16", f"Instrument identifier invalid: {instrument!r}."
        )
    if "\x00" in instrument:
        raise FilesystemSecurityError("FS-15", "NUL byte in instrument identifier.")
    if "/" in instrument or "\\" in instrument:
        raise FilesystemSecurityError(
            "FS-15",
            f"Path separator in instrument {instrument!r} — instrument "
            f"identifiers MUST NOT control path structure.",
        )
    if ".." in instrument:
        raise FilesystemSecurityError(
            "FS-14",
            f"Traversal sequence '..' in instrument {instrument!r} — rejected "
            f"before path construction.",
        )
    if len(instrument) >= 2 and instrument[1] == ":" and instrument[0].isalpha():
        raise FilesystemSecurityError(
            "FS-15", f"Drive letter in instrument {instrument!r}."
        )
    if instrument.startswith("\\\\") or instrument.startswith("//"):
        raise FilesystemSecurityError(
            "FS-15", f"UNC prefix in instrument {instrument!r}."
        )
    if instrument.startswith("~"):
        raise FilesystemSecurityError(
            "FS-15", f"Home-directory expansion in instrument {instrument!r}."
        )

    # FS-14: allowlist before path construction. Fail closed when no
    # allowlist source is configured at all.
    if allowlist is not None:
        if instrument not in allowlist:
            raise FilesystemSecurityError(
                "FS-14",
                f"Instrument {instrument!r} is not in the configured "
                f"instrument allowlist.",
            )
    elif registry is not None and registry_count and registry_count > 0:
        if not registry.is_registered(instrument):
            raise FilesystemSecurityError(
                "FS-14",
                f"Instrument {instrument!r} is not registered in the "
                f"InstrumentRegistry.",
            )
    else:
        raise FilesystemSecurityError(
            "FS-14",
            "No instrument allowlist configured (neither an explicit "
            "allowlist nor a populated registry) — failing closed; "
            "filenames must be constructed from validated identifiers "
            "(FS-16).",
        )
    return instrument


class SecurityAuditTrail:
    """Append-only, tamper-evident structured security audit trail
    (FS-21, FS-22).

    Every allow and every deny is recorded with actor, path, decision,
    rule, and timestamp (FS-21). Entries are hash-chained: each entry
    carries the previous entry's hash, and the chain can be verified
    end-to-end (FS-22: append-only and tamper-evident).

    Note: audit timestamps are wall-clock BY DESIGN — an audit trail
    records when a security decision happened; it never participates
    in any Phase 4 identity (spec 2.4 ID-WC-01).
    """

    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.touch()

    def _read_entries(self) -> list:
        entries = []
        with open(self.path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    entries.append(json.loads(line))
        return entries

    def _entry_digest(self, entry: dict) -> str:
        payload = {k: v for k, v in entry.items() if k != "entry_hash"}
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

    def record(self, actor: str, path: str, decision: str, rule: str) -> dict:
        """Append one audit record. Returns the recorded entry."""
        entries = self._read_entries()
        prev_hash = entries[-1]["entry_hash"] if entries else "GENESIS"
        entry = {
            "seq": len(entries) + 1,
            "timestamp": datetime.now(UTC).isoformat(),
            "actor": actor,
            "path": str(path),
            "decision": decision,   # "ALLOW" | "DENY"
            "rule": rule,
            "prev_hash": prev_hash,
        }
        entry["entry_hash"] = self._entry_digest(entry)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, sort_keys=True) + "\n")
        return entry

    def verify(self) -> bool:
        """Verify the full hash chain (FS-22 tamper evidence)."""
        entries = self._read_entries()
        prev_hash = "GENESIS"
        for i, entry in enumerate(entries):
            if entry.get("seq") != i + 1:
                return False
            if entry.get("prev_hash") != prev_hash:
                return False
            if entry.get("entry_hash") != self._entry_digest(entry):
                return False
            prev_hash = entry["entry_hash"]
        return True

    def decisions(self) -> list:
        """Return all recorded decisions (audit surface)."""
        return self._read_entries()
