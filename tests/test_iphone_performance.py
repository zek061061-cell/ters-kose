"""Performance smoke checks for the iPhone-facing fixture path."""

import json
import time
import unittest

from fixture_store import STORE


class IPhonePerformanceSmokeTests(unittest.TestCase):
    def test_one_day_fixture_shard_is_small_and_fast(self):
        started = time.perf_counter()
        rows = STORE.query("2026-09-08")
        elapsed_ms = (time.perf_counter() - started) * 1000
        encoded_size = len(json.dumps(rows, ensure_ascii=False).encode("utf-8"))
        self.assertLess(elapsed_ms, 2_000, f"cold one-day query took {elapsed_ms:.1f} ms")
        self.assertLess(encoded_size, 512_000, f"one-day response was {encoded_size} bytes")
        self.assertLess(len(rows), 1_000, "fixture endpoint returned an unbounded dataset")


if __name__ == "__main__":
    unittest.main()
