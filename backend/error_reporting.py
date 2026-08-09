"""Ship ERROR-level logs to Google Cloud Logging, where Error Reporting groups them.

WHY THIS AND NOT SENTRY (decided 2026-08-09, replacing the short-lived Sentry wiring):
Sentry would have meant a third-party account, a vendor dependency, an SDK in the image, and
exception payloads — which here can carry device ids, wallet ids and emails — leaving our
infrastructure. Google already hosts the VM and the database, so this adds no new trust boundary,
no new account, and no new privacy-policy processor.

HOW IT WORKS — no Error Reporting API call is made:
Error Reporting *infers* error events from Cloud Logging entries whose payload contains a stack
trace at severity ERROR or above. So we only need to write logs, which requires the
`logging.write` scope the VM already has. (Using the Error Reporting client library directly would
have needed `cloud-platform`, and VM scopes can only change while the instance is STOPPED — i.e.
prod downtime, for no benefit.)

WHAT GETS REPORTED: every `logger.error(...)` and `logger.exception(...)` in the app, plus
uvicorn's own "Exception in ASGI application" for unhandled endpoint errors — and therefore the
`spawn()` background-task crash reports (`question-timer:ABC123`, `housie-auto:XYZ`), which
previously existed only in `docker logs` that nobody reads.

FAIL-OPEN BY DESIGN: if the client can't be built (no credentials, missing package, wrong scope),
we log a warning and carry on. Observability must never be able to take the app down — the same
rule the rest of this codebase follows.
"""
import logging
from typing import Optional

import config

logger = logging.getLogger(__name__)

_handler: Optional[logging.Handler] = None


def init() -> bool:
    """Attach the Cloud Logging handler for ERROR+ records. Returns True if active.

    Idempotent: a second call is a no-op, so an accidental double-init in a reload/lifespan path
    cannot double-report every error.
    """
    global _handler
    if not config.ERROR_REPORTING_ENABLED:
        return False
    if _handler is not None:
        return True
    try:
        import google.cloud.logging
        from google.cloud.logging.handlers import CloudLoggingHandler

        client = google.cloud.logging.Client()
        # `name` becomes the Cloud Logging log name — keeping prod and gamma distinct matters,
        # because otherwise a gamma stack trace looks exactly like a production incident.
        handler = CloudLoggingHandler(
            client,
            name=f"revelry-games-{config.ENVIRONMENT or 'unknown'}",
        )
        handler.setLevel(logging.ERROR)
        # A formatter that renders exc_info into the message text: the traceback IS the signal
        # Error Reporting keys on. Without it the entry is a bare one-liner and never groups.
        handler.setFormatter(logging.Formatter(
            "%(levelname)s %(name)s: %(message)s"
        ))
        logging.getLogger().addHandler(handler)
        _handler = handler
        logger.info("Cloud Logging error reporting active (env=%s)", config.ENVIRONMENT or "unknown")
        return True
    except Exception as e:  # noqa: BLE001 — never let observability break startup
        logger.warning("ERROR_REPORTING_ENABLED is set but Cloud Logging init failed: %s", e)
        return False


def shutdown() -> None:
    """Flush the background transport. Called from the lifespan shutdown so a crash logged
    milliseconds before SIGTERM still reaches Cloud Logging instead of dying in the buffer."""
    global _handler
    if _handler is None:
        return
    try:
        _handler.flush()
        logging.getLogger().removeHandler(_handler)
    except Exception:  # noqa: BLE001
        pass
    finally:
        _handler = None
