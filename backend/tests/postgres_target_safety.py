"""Fail closed before any schema-writing or destructive parity connection."""
import ipaddress
import os


def _local_host(value: str) -> bool:
    # pg/postgres are the fixed service aliases supported by the disposable Docker stack.
    if value.lower() in {"localhost", "pg", "postgres"}:
        return True
    try:
        return ipaddress.ip_address(value).is_loopback
    except ValueError:
        return False


def assert_local_postgres_dsn(dsn: str) -> None:
    """Validate libpq's parsed targets, including URI overrides and env defaults.

    Service files can supply hostaddr even when a DSN explicitly supplies a local host.
    Refuse service routing rather than reading an arbitrary local service definition.
    """
    from psycopg.conninfo import conninfo_to_dict

    refusal = (
        "REFUSING TO RUN: PARITY_POSTGRES_DSN must target an explicit local test stack. "
        "This suite changes schemas and test data; use ./scripts/parity-stack.sh up."
    )
    try:
        params = conninfo_to_dict(dsn)
    except Exception:
        # libpq error text may include the original DSN/password.
        raise RuntimeError(refusal + " Invalid connection parameters.") from None

    if params.get("service") or os.getenv("PGSERVICE"):
        raise RuntimeError(refusal + " Service-based routing is not allowed.")

    host = params.get("host") or os.getenv("PGHOST", "")
    hostaddr = params.get("hostaddr") or os.getenv("PGHOSTADDR", "")
    if not host and not hostaddr:
        raise RuntimeError(refusal + " A local host or hostaddr is required.")
    for target in (host, hostaddr):
        if target and any(not _local_host(part) for part in target.split(",")):
            raise RuntimeError(refusal + " A host or hostaddr is outside the local stack.")


def connect_local_postgres(dsn: str, *, autocommit: bool = False):
    """Keep validation inseparable from the direct parity-suite connection."""
    assert_local_postgres_dsn(dsn)
    import psycopg

    return psycopg.connect(dsn, autocommit=autocommit)
