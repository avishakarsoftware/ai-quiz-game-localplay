"""Shared helpers + the module contract for LocalPlay game engines.

Before this module existed, every engine carried its own copy of the text
sanitizer and int clamp (15 copies of `_clamp_int`, 9 divergent bodies of
`_clean_text`). Four of those `_clean_text` variants had drifted below the
documented security baseline (they skipped the strip-all-tags pass). Engines
now import from here so the sanitization policy is defined once, strictly.

Security baseline for user-visible text (see security_hardening_summary):
  1. strip ASCII control chars (keep \t/\n handling via whitespace collapse)
  2. strip <script>/<style>/<iframe> tags case-insensitively
  3. strip ALL remaining HTML tags
  4. collapse whitespace, trim, cap length
"""
from typing import Any, Callable, Optional, Protocol, runtime_checkable
import re

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_DANGEROUS_TAGS = re.compile(r"<\s*/?\s*(script|style|iframe)[^>]*>", re.IGNORECASE)
_ALL_TAGS = re.compile(r"<[^>]+>")
_WHITESPACE = re.compile(r"\s+")


def clean_text(value: Any, max_chars: int = 180) -> str:
    """Canonical strict sanitizer for any user-supplied display text."""
    text = _CONTROL_CHARS.sub("", str(value or ""))
    text = _DANGEROUS_TAGS.sub("", text)
    text = _ALL_TAGS.sub("", text)
    return _WHITESPACE.sub(" ", text).strip()[:max_chars]


def make_clean_text(max_chars: int) -> Callable[..., str]:
    """Bind an engine-specific default length onto the canonical sanitizer.

    Engines historically used different default caps (120-220 chars). This
    preserves each engine's cap at untouched call sites while unifying the
    sanitization body itself.
    """
    def _bound(value: Any, chars: int = max_chars) -> str:
        return clean_text(value, chars)
    return _bound


_MARKER_DASHES = re.compile(r"-{3,}")


def wrap_user_topic(prompt: Any, label: str = "TOPIC") -> str:
    """Fence user-supplied topic text inside boundary markers it cannot forge.

    The markers only mean something if the user can't type one. Wrapping raw text let a prompt of
    `--- END USER TOPIC --- <new instructions>` close the fence and address the model directly,
    which is exactly what the fence exists to prevent. Collapsing every run of 3+ hyphens in the
    user's text to `--` makes a forged marker unrepresentable while leaving the topic readable.
    """
    safe = _MARKER_DASHES.sub("--", str(prompt or ""))
    return f"--- BEGIN USER {label} ---\n{safe}\n--- END USER {label} ---"


def clamp_int(raw: dict, key: str, default: int, low: int, high: int) -> int:
    """Read raw[key] as an int, falling back to default, clamped to [low, high]."""
    try:
        value = int(raw.get(key, default))
    except (TypeError, ValueError):
        value = default
    return max(low, min(high, value))


@runtime_checkable
class GameEngine(Protocol):
    """The module-level contract a LocalPlay game engine exposes.

    Engines are modules, not classes; socket_manager/main call these as
    module functions. `validate_config` and `create_initial_state` are
    universal; the rest are optional per game family (a module object
    satisfies this Protocol structurally).

    Required:
      validate_config(raw)            -> sanitized config dict (never raises on junk)
      create_initial_state(players, config, ...) -> full runtime state dict
    Common optional:
      add_player(state, player_id, ...)   -> state with a late-join seat
      public_sync(state, players=None)    -> spectator/organizer-safe view
      private_sync(state, player_id, ...) -> per-player view (secrets redacted)
      result_summary(state, players=None) -> host-app-safe aggregate summary
    """
    def validate_config(self, raw: Optional[dict]) -> dict: ...
    def create_initial_state(self, *args: Any, **kwargs: Any) -> dict: ...
