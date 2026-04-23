"""Unit tests for marketing / newsletter suppression signals."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from services.marketing_email_signals import is_likely_marketing_or_newsletter  # noqa: E402


class TestMarketingEmailSignals(unittest.TestCase):
    def test_precedence_bulk(self) -> None:
        self.assertTrue(
            is_likely_marketing_or_newsletter(
                payload={"headers": {"Precedence": "bulk"}},
                subject="Hello",
                raw_text="Nothing special",
            )
        )

    def test_auto_submitted(self) -> None:
        self.assertTrue(
            is_likely_marketing_or_newsletter(
                payload={"headers": {"Auto-Submitted": "auto-generated"}},
                subject="Reminder",
                raw_text="x",
            )
        )

    def test_list_unsubscribe_with_promo_subject(self) -> None:
        self.assertTrue(
            is_likely_marketing_or_newsletter(
                payload={"headers": {"List-Unsubscribe": "<mailto:off@example.com>"}},
                subject="Weekly digest: your picks",
                raw_text="Body",
            )
        )

    def test_list_unsubscribe_ci_body_not_enough(self) -> None:
        self.assertFalse(
            is_likely_marketing_or_newsletter(
                payload={"headers": {"List-Unsubscribe": "<http://example.com/u>"}},
                subject="Build failed on main",
                raw_text="Please fix the failing test in CI.",
            )
        )

    def test_vendor_footer_and_promo_subject(self) -> None:
        self.assertTrue(
            is_likely_marketing_or_newsletter(
                payload={},
                subject="Newsletter: spring sale",
                raw_text="Powered by Mailchimp. Use this link to unsubscribe.",
            )
        )

    def test_normal_work_email(self) -> None:
        self.assertFalse(
            is_likely_marketing_or_newsletter(
                payload={},
                subject="Re: contract review",
                raw_text="Please see attached.",
            )
        )

    def test_headers_as_list_format(self) -> None:
        payload = {"headers": [{"name": "Precedence", "value": "bulk"}]}
        self.assertTrue(
            is_likely_marketing_or_newsletter(payload=payload, subject="x", raw_text="y")
        )


if __name__ == "__main__":
    unittest.main()
