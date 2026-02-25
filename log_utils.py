"""Simple structured logging for FinanceRadar."""
from datetime import datetime, timezone, timedelta

IST_TZ = timezone(timedelta(hours=5, minutes=30))


class FeedLogger:
    """Tracks feed fetch results and provides structured output."""

    def __init__(self, name="FinanceRadar"):
        self.name = name
        self._ok = 0
        self._fail = 0
        self._total_articles = 0

    def ok(self, source, detail=""):
        """Log a successful operation."""
        self._ok += 1
        ts = datetime.now(IST_TZ).strftime("%H:%M:%S")
        msg = f"[{ts}] [OK] {source}"
        if detail:
            msg += f" — {detail}"
        print(msg)

    def fail(self, source, error=""):
        """Log a failed operation."""
        self._fail += 1
        ts = datetime.now(IST_TZ).strftime("%H:%M:%S")
        msg = f"[{ts}] [FAIL] {source}"
        if error:
            msg += f" — {error}"
        print(msg)

    def warn(self, source, message):
        """Log a warning."""
        ts = datetime.now(IST_TZ).strftime("%H:%M:%S")
        print(f"[{ts}] [WARN] {source} — {message}")

    def info(self, message):
        """Log an info message."""
        ts = datetime.now(IST_TZ).strftime("%H:%M:%S")
        print(f"[{ts}] {message}")

    def add_articles(self, count):
        """Track article count."""
        self._total_articles += count

    def summary(self):
        """Print final summary line."""
        total = self._ok + self._fail
        print(f"\n=== {self._ok}/{total} sources succeeded, {self._fail} failed, {self._total_articles} articles ===")
        return self._ok, self._fail, self._total_articles
