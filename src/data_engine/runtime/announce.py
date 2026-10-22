"""mDNS announcement for the local monitor service (v4.0, PART 5 B3 / P5).

Announces the authenticated monitoring API on the local network as
``_aitl-monitor._tcp.local.`` so the Android client can auto-discover
the Windows PC it should pair with. A manual "PC address" entry always
remains available as the documented fallback — mDNS is a convenience
layer, NEVER a hard dependency:

- ``zeroconf`` not installed → graceful ``unavailable`` status (the
  monitor still serves; the phone falls back to manual entry);
- ANY registration failure → graceful ``failed`` status, serving is
  never blocked;
- announcing is opt-in: only enabled when the server is started with
  ``--mdns-announce`` (the Windows ``run-monitor.ps1 -AllowLan`` path).

All data served is SYNTHETIC/paper-only in this repository. LIVE
TRADING REMAINS NOT AUTHORIZED. PAPER_READY stays FALSE.
"""

from __future__ import annotations

import socket
from dataclasses import dataclass
from typing import Any, Callable, Optional

#: The mDNS service type announced on the LAN (P5).
SERVICE_TYPE = "_aitl-monitor._tcp.local."

#: Default mDNS instance name (override with ``--mdns-instance``).
DEFAULT_INSTANCE = "aitl-monitor"


@dataclass
class MdnsAnnouncement:
    """Result handle for one announcement attempt (never raises)."""

    status: str
    handle: Optional[Any] = None  # (Zeroconf, ServiceInfo) when registered

    @property
    def announced(self) -> bool:
        return self.handle is not None

    def stop(self) -> None:
        if self.handle is None:
            return
        zeroconf, info = self.handle
        try:
            zeroconf.unregister_service(info)
        except Exception:  # noqa: BLE001 — best-effort teardown
            pass
        try:
            zeroconf.close()
        except Exception:  # noqa: BLE001
            pass
        self.handle = None


def _lan_address(host: str) -> str:
    """Resolve a concrete announce address for the given bind host.

    ``0.0.0.0`` (all interfaces) has no single mDNS address — detect
    the primary outbound IPv4 instead (a UDP connect determines the
    route WITHOUT sending a packet). Loopback binds announce their own
    address (useful for same-device/emulator setups).
    """
    if host not in ("0.0.0.0", "::"):
        return host
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("192.0.2.1", 9))  # TEST-NET — never sent on the wire
        return probe.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        probe.close()


def _default_zeroconf_factory():
    """Import zeroconf lazily (import-time failure is a graceful status)."""
    from zeroconf import ServiceInfo, Zeroconf  # noqa: PLC0415

    return Zeroconf, ServiceInfo


def try_announce_mdns(
    *,
    instance: str = DEFAULT_INSTANCE,
    host: str = "127.0.0.1",
    port: int = 8018,
    txt: Optional[dict] = None,
    zeroconf_factory: Optional[Callable[[], Any]] = None,
) -> MdnsAnnouncement:
    """Attempt to announce the monitor service; NEVER raise / block.

    ``zeroconf_factory`` is injectable for tests (returns a
    ``(Zeroconf, ServiceInfo)`` pair). Production uses the lazy import
    above; a missing package is a graceful degradation, not an error.
    """
    factory = zeroconf_factory or _default_zeroconf_factory
    try:
        Zeroconf, ServiceInfo = factory()
    except ImportError:
        return MdnsAnnouncement(
            status=(
                "mDNS unavailable (zeroconf not installed); "
                "use the manual PC address"
            )
        )
    except Exception as exc:  # noqa: BLE001 — factory failure = graceful
        return MdnsAnnouncement(
            status=(
                f"mDNS unavailable ({type(exc).__name__}); "
                "use the manual PC address"
            )
        )

    address = _lan_address(host)
    try:
        zeroconf = Zeroconf()
        info = ServiceInfo(
            SERVICE_TYPE,
            f"{instance}.{SERVICE_TYPE}",
            addresses=[socket.inet_aton(address)],
            port=int(port),
            properties=dict(txt or {}),
        )
        zeroconf.register_service(info)
    except Exception as exc:  # noqa: BLE001 — NEVER block serving
        return MdnsAnnouncement(
            status=(
                f"mDNS announce failed ({type(exc).__name__}); "
                "use the manual PC address"
            )
        )
    return MdnsAnnouncement(
        status=f"mDNS announced: {instance}.{SERVICE_TYPE} at {address}:{port}",
        handle=(zeroconf, info),
    )


__all__ = [
    "DEFAULT_INSTANCE",
    "MdnsAnnouncement",
    "SERVICE_TYPE",
    "try_announce_mdns",
]
