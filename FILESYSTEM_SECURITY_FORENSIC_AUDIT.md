# FILESYSTEM SECURITY FORENSIC AUDIT
**Date:** 2026-09-30
**Mode:** READ-ONLY

---

## FileDataProvider Path Construction Analysis

### Source: src/data_engine/provider.py, lines 141-189

```python
class FileDataProvider(MarketDataProvider):
    def __init__(self, config: ProviderConfig, registry: Optional[InstrumentRegistry] = None):
        super().__init__(config, registry)
        import os
        self._data_dir = config.endpoint or "./data"

    def fetch_candles(self, instrument: str, timeframe: Timeframe, start: datetime, end: datetime) -> list:
        import os
        filepath = os.path.join(self._data_dir, f"{instrument}_{timeframe.value}.csv")
        if not os.path.exists(filepath):
            return []
        import pandas as pd
        df = pd.read_csv(filepath)
        ...
```

---

## ATTACK: ../ Traversal

**Attack:** Set `config.endpoint` to `"../../etc"` or `"../.."` and read files outside the intended data directory.

**Expected Result:** FileDataProvider should reject paths that resolve outside the data directory, or at minimum should not allow reading arbitrary filesystem paths.

**Actual Control:** NONE. `os.path.join(self._data_dir, filename)` simply concatenates paths. If `self._data_dir` is `"../../etc"`, the resulting path is `"../../etc/XAU/USD_1h.csv"` which resolves to `/etc/XAU/USD_1h.csv` (or equivalent on Windows). No validation, no normalization, no containment.

**Evidence:**
```python
self._data_dir = config.endpoint or "./data"  # No validation
filepath = os.path.join(self._data_dir, f"{instrument}_{timeframe.value}.csv")  # No containment
if not os.path.exists(filepath):  # Checks existence, not containment
    return []
```

**STATUS: FAIL**
- `os.path.join()` is NOT path-traversal prevention
- No `os.path.realpath()` or `os.path.abspath()` to resolve the final path
- No check that resolved path is within an expected base directory
- No sandbox, chroot, or path restriction

---

## ATTACK: Absolute-Path Injection

**Attack:** Set `config.endpoint` to an absolute path like `"/etc"` or `"C:\\Windows\\System32"` and read system files.

**Expected Result:** FileDataProvider should reject absolute paths or restrict reads to a specific data directory.

**Actual Control:** NONE. If `config.endpoint` is `"/etc"`, then `os.path.join("/etc", "XAU/USD_1h.csv")` produces `"/etc/XAU/USD_1h.csv"`. On Windows, `os.path.join("C:\\Windows\\System32", "XAU/USD_1h.csv")` produces `"C:\\Windows\\System32\\XAU/USD_1h.csv"`. No validation of absolute vs relative paths.

**Evidence:**
```python
self._data_dir = config.endpoint or "./data"  # Accepts any string
# No check: if os.path.isabs(self._data_dir): raise ...
```

**STATUS: FAIL**
- No absolute-path rejection
- No path-type validation
- Config.endpoint accepts any string value

---

## ATTACK: Alternate Path Representations

**Attack:** Use path representations that bypass naive string checks:
- `////etc/passwd` (multiple slashes)
- `C:\\\\Windows\\\\System32` (Windows UNC-style)
- `..%2f..%2fetc` (URL-encoded, if processed)
- Symlinks pointing outside the data directory

**Expected Result:** FileDataProvider should normalize paths and reject alternate representations.

**Actual Control:** NONE. No path normalization is performed. `os.path.join()` does not resolve symlinks, normalize redundant slashes, or decode URL-encoded paths. If the file at `self._data_dir + "/" + filename` is a symlink to `/etc/passwd`, `os.path.exists()` follows the symlink and `pd.read_csv()` reads the target.

**Evidence:**
```python
filepath = os.path.join(self._data_dir, f"{instrument}_{timeframe.value}.csv")
if not os.path.exists(filepath):  # Follows symlinks
    return []
df = pd.read_csv(filepath)  # Reads through symlinks
```

**STATUS: FAIL**
- No symlink detection or rejection
- No path normalization
- No resolution of alternate path representations

---

## ATTACK: Symlink Escape

**Attack:** Create a symlink inside the data directory that points to a file outside the data directory. FileDataProvider follows the symlink and reads the target.

**Expected Result:** FileDataProvider should detect symlinks and either reject them or resolve them and verify the target is within the allowed directory.

**Actual Control:** NONE. `os.path.exists()` and `pd.read_csv()` both follow symlinks by default. No `os.path.islink()` check, no `os.readlink()` check, no target verification.

**Evidence:**
```python
# No symlink check before read
if not os.path.exists(filepath):
    return []
df = pd.read_csv(filepath)  # Follows symlinks
```

**STATUS: FAIL**
- Symlinks are followed without detection
- No target containment verification
- Symlink escape is possible

---

## ATTACK: Path Normalization Bypass

**Attack:** Use paths that os.path.join() handles differently than expected:
- Empty strings: `os.path.join("/data", "")` → `"/data"`
- Mixed separators on Windows: `os.path.join("C:\\data", "/etc/passwd")` → may produce unexpected results
- `os.path.join` behavior with absolute second argument: `os.path.join("/data", "/etc/passwd")` → `"/etc/passwd"` (second absolute path replaces first)

**Expected Result:** FileDataProvider should handle edge cases in path construction safely.

**Actual Control:** NONE. The `instrument` parameter is user-controlled (comes from the `instrument` argument to `fetch_candles`). If `instrument` contains path separators or is an absolute path, `os.path.join()` behavior may be unexpected.

**Evidence:**
```python
filepath = os.path.join(self._data_dir, f"{instrument}_{timeframe.value}.csv")
# If instrument = "/etc/passwd", filepath = os.path.join("./data", "/etc/passwd_XAU_1h.csv")
# On Unix: os.path.join("./data", "/etc/passwd_XAU_1h.csv") = "/etc/passwd_XAU_1h.csv" (absolute second arg wins)
```

Wait — let me check this more carefully. `f"{instrument}_{timeframe.value}.csv"` — if instrument is `"/etc/passwd"`, the filename becomes `"/etc/passwd_H1.csv"`. On Unix, `os.path.join("./data", "/etc/passwd_H1.csv")` would produce `"/etc/passwd_H1.csv"` because the second argument is absolute. This is a path traversal vector.

**STATUS: FAIL**
- User-controlled `instrument` parameter enters path construction
- Absolute path in instrument bypasses data directory
- No sanitization of instrument parameter for path safety

---

## ATTACK: Unexpected Parent-Directory Access

**Attack:** Use `../../` sequences in the instrument name or config.endpoint to access parent directories.

**Expected Result:** FileDataProvider should prevent access to parent directories.

**Actual Control:** NONE. See ../ Traversal attack above. No parent-directory restriction exists.

**STATUS: FAIL**

---

## ATTACK: Arbitrary File Selection

**Attack:** The filename is constructed as `f"{instrument}_{timeframe.value}.csv"`. The `instrument` parameter is user-controlled. An attacker can select arbitrary filenames by controlling the instrument parameter.

**Expected Result:** FileDataProvider should restrict which files can be read to a known set or pattern.

**Actual Control:** NONE. Any instrument string produces a filename. No allowlist, no pattern restriction, no file-type validation beyond the .csv extension (which is appended, not checked).

**Evidence:**
```python
filepath = os.path.join(self._data_dir, f"{instrument}_{timeframe.value}.csv")
# instrument = "....//....//etc/passwd" produces path traversal
# instrument = "XAU/USD" produces "XAU/USD_H1.csv" (valid)
# instrument = "/" produces "/_H1.csv" (path traversal on Unix)
```

**STATUS: FAIL**
- Arbitrary file selection possible through instrument parameter
- No allowlist of valid instruments for file access
- No filename sanitization

---

## SUMMARY: FILESYSTEM SECURITY AUDIT

| Attack Vector | Expected Result | Actual Control | Status |
|--------------|-----------------|----------------|--------|
| ../ Traversal | Reject or contain | NONE — os.path.join() only | FAIL |
| Absolute-Path Injection | Reject absolute paths | NONE — any endpoint accepted | FAIL |
| Alternate Path Representations | Normalize and reject | NONE — no normalization | FAIL |
| Symlink Escape | Detect and reject symlinks | NONE — symlinks followed | FAIL |
| Path Normalization Bypass | Handle edge cases | NONE — no edge case handling | FAIL |
| Unexpected Parent-Directory Access | Prevent parent access | NONE — no containment | FAIL |
| Arbitrary File Selection | Restrict to allowlist | NONE — any instrument accepted | FAIL |

**OVERALL: FAIL**

FileDataProvider does NOT prevent path traversal, absolute-path injection, symlink escape, or arbitrary file selection. The only "control" is `os.path.join()` which is NOT a security mechanism.

**Do not consider os.path.join() alone as evidence of path-traversal prevention.**

IMPLEMENTATION AUTHORIZATION: NOT_AUTHORIZED
