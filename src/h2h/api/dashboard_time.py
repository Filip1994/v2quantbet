"""Display helpers shared by the Research and Production dashboards."""

from __future__ import annotations

import base64
import hashlib
from datetime import UTC, datetime
from html import escape
from zoneinfo import ZoneInfo


BELGRADE = ZoneInfo("Europe/Belgrade")


def local_time(value: datetime | None, format_string: str) -> str:
    if value is None:
        return "—"
    return value.astimezone(BELGRADE).strftime(format_string)


def local_iso(value: str | None) -> str:
    """Format an ISO timestamp for the HTML drilldowns; keep API data in UTC."""
    if not value:
        return "—"
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return local_time(parsed, "%Y-%m-%d %H:%M")


def kickoff_countdown(kickoff: datetime | None) -> str:
    if kickoff is None:
        return ""
    timestamp = kickoff.astimezone(UTC).isoformat()
    return (
        f'<small class="kickoff-countdown" data-kickoff="{escape(timestamp, quote=True)}" '
        'aria-live="off">Starts in —</small>'
    )


# Updates only the current page. It does not poll Railway or any external API.
COUNTDOWN_SCRIPT = """<script>
(() => {
  const counters = [...document.querySelectorAll('.kickoff-countdown[data-kickoff]')];
  if (!counters.length) return;
  function update() {
    const now = Date.now();
    for (const counter of counters) {
      const kickoff = Date.parse(counter.dataset.kickoff);
      if (!Number.isFinite(kickoff)) {
        counter.textContent = '';
        continue;
      }
      const minutes = Math.ceil((kickoff - now) / 60000);
      if (minutes <= 0) {
        counter.textContent = 'Started';
        continue;
      }
      const hours = Math.floor(minutes / 60);
      counter.textContent = `Starts in ${hours}h ${String(minutes % 60).padStart(2, '0')}m`;
    }
  }
  update();
  setInterval(update, 30000);
})();
</script>"""

_script_body = COUNTDOWN_SCRIPT.removeprefix("<script>").removesuffix("</script>")
COUNTDOWN_SCRIPT_CSP = "'sha256-" + base64.b64encode(
    hashlib.sha256(_script_body.encode()).digest()
).decode() + "'"
