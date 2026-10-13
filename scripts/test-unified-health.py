"""Offline simulations for unified-health.py; never probes or writes services."""
from __future__ import annotations

import importlib.util
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


SCRIPT = Path(__file__).with_name("unified-health.py")
sys.dont_write_bytecode = True
SPEC = importlib.util.spec_from_file_location("unified_health", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load unified-health.py")
HEALTH = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(HEALTH)


class UnifiedHealthSimulations(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 10, 12, 15, 0, tzinfo=timezone.utc)
        self.checked_at = "2026-10-12T15:00:00+00:00"

    def checks(self, state: str = "healthy") -> list[dict[str, str]]:
        names = [
            "Twenty CRM",
            "订单报表服务",
            "审核后台",
            "WhatsApp Evolution API",
            "Docker 服务",
            "汇率缓存",
        ]
        return [
            HEALTH.make_check(name, state, "simulation", "simulated", self.checked_at)
            for name in names
        ]

    def test_all_normal_is_healthy(self) -> None:
        result = HEALTH.summarize(self.checks(), self.now)
        self.assertEqual(result["status"], "healthy")
        self.assertEqual(len(result["services"]), 6)

    def test_unavailable_service_is_failed(self) -> None:
        checks = self.checks()
        checks[0] = HEALTH.make_check(
            "Twenty CRM", "failed", "simulation", "simulated unavailable", self.checked_at
        )
        result = HEALTH.summarize(checks, self.now)
        self.assertEqual(result["status"], "failed")

    def test_expired_fx_cache_is_warning(self) -> None:
        cache = {
            "rate": "6.7",
            "sourceDate": "2026-10-11",
            "nextUpdateUnix": self.now.timestamp() - 3600,
        }
        fx_status, _reason = HEALTH.evaluate_fx_cache(cache, self.now)
        checks = self.checks()
        checks[-1] = HEALTH.make_check(
            "汇率缓存", fx_status, "simulation", "simulated expired cache", self.checked_at
        )
        result = HEALTH.summarize(checks, self.now)
        self.assertEqual(fx_status, "warning")
        self.assertEqual(result["status"], "warning")


if __name__ == "__main__":
    unittest.main(verbosity=2)
