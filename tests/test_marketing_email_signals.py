"""Unit tests for marketing / newsletter suppression signals."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from services.marketing_email_signals import (  # noqa: E402
    is_automated_or_bulk_sender,
    is_likely_marketing_or_newsletter,
    should_suppress_as_non_actionable,
)


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

    def test_delivery_survey_subject_bg(self) -> None:
        subj = "Happy Delivery / Анкета за оценяване"
        self.assertTrue(
            is_likely_marketing_or_newsletter(payload={}, subject=subj, raw_text="Please rate us.")
        )

    def test_airline_sweepstakes_campaign_subject(self) -> None:
        self.assertTrue(
            is_likely_marketing_or_newsletter(
                payload={},
                subject="U3M6FD | Chance to win a €100 Ryanair Gift Card",
                raw_text="Terms apply.",
            )
        )

    def test_mcnuggets_menu_promo_subject(self) -> None:
        self.assertTrue(
            is_likely_marketing_or_newsletter(
                payload={},
                subject="Spicy McNuggets® are back",
                raw_text="Open the app.",
            )
        )

    def test_takeaway_order_invoice_subject(self) -> None:
        self.assertTrue(
            is_likely_marketing_or_newsletter(
                payload={},
                subject="Here is the invoice of your order on Takeaway.com",
                raw_text="Total 12.50 EUR",
            )
        )

    def test_customer_satisfaction_phrase_alone_not_marketing(self) -> None:
        self.assertFalse(
            is_likely_marketing_or_newsletter(
                payload={},
                subject="Q3 customer satisfaction scores for ACME",
                raw_text="Attached is the deck.",
            )
        )

    def test_headers_as_list_format(self) -> None:
        payload = {"headers": [{"name": "Precedence", "value": "bulk"}]}
        self.assertTrue(
            is_likely_marketing_or_newsletter(payload=payload, subject="x", raw_text="y")
        )


class TestAutomatedOrBulkSender(unittest.TestCase):
    def test_list_unsubscribe_header_alone(self) -> None:
        self.assertTrue(
            is_automated_or_bulk_sender(
                payload={"headers": {"List-Unsubscribe": "<mailto:u@x.com>"}},
                sender="Some Brand <hello@brand.com>",
            )
        )

    def test_noreply_local_part(self) -> None:
        self.assertTrue(
            is_automated_or_bulk_sender(
                payload={},
                sender="Stripe <no-reply@stripe.com>",
            )
        )

    def test_notifications_local_substring(self) -> None:
        self.assertTrue(
            is_automated_or_bulk_sender(
                payload={},
                sender="GitHub <notifications@github.com>",
            )
        )

    def test_bulk_domain_substring_newsletter(self) -> None:
        # Headers missing (older DB row), but domain contains "newsletter".
        self.assertTrue(
            is_automated_or_bulk_sender(
                payload={},
                sender="TLDR AI <dan@tldrnewsletter.com>",
            )
        )

    def test_esp_return_path(self) -> None:
        self.assertTrue(
            is_automated_or_bulk_sender(
                payload={
                    "headers": {
                        "From": "Brand <hello@brand.com>",
                        "Return-Path": "bounces+abc@mcsv.net",
                    }
                },
                sender="Brand <hello@brand.com>",
            )
        )

    def test_body_unsubscribe_fallback_when_no_headers(self) -> None:
        self.assertTrue(
            is_automated_or_bulk_sender(
                payload={},
                sender="Store <hello@store.example>",
                raw_text="Check out our new items. Click here to unsubscribe at any time.",
            )
        )

    def test_human_1to1_not_bulk(self) -> None:
        self.assertFalse(
            is_automated_or_bulk_sender(
                payload={
                    "headers": {
                        "From": "Alice <alice@acme.com>",
                        "Return-Path": "alice@acme.com",
                    }
                },
                sender="Alice <alice@acme.com>",
                raw_text="Hi, can you review the attached doc tomorrow?",
            )
        )

    def test_calendar_notification_email(self) -> None:
        self.assertTrue(
            is_automated_or_bulk_sender(
                payload={},
                sender="Google Calendar <calendar-notification@google.com>",
            )
        )


class TestShouldSuppressAsNonActionable(unittest.TestCase):
    def test_newsletter_domain_suppressed(self) -> None:
        ok, reason = should_suppress_as_non_actionable(
            payload={},
            subject="Anthropic's cyber play",
            raw_text="View in your browser.",
            sender="TLDR AI <dan@tldrnewsletter.com>",
        )
        self.assertTrue(ok)
        self.assertEqual(reason, "automated_or_bulk_sender")

    def test_promo_subject_without_sender_signals(self) -> None:
        ok, reason = should_suppress_as_non_actionable(
            payload={},
            subject="Spicy McNuggets® are back",
            raw_text="Open the app.",
            sender="mcd@example.com",
        )
        self.assertTrue(ok)
        self.assertEqual(reason, "likely_marketing_newsletter")

    def test_real_work_email_not_suppressed(self) -> None:
        ok, reason = should_suppress_as_non_actionable(
            payload={"headers": {"From": "Alice <alice@acme.com>"}},
            subject="Re: contract review",
            raw_text="Please see attached and let me know by Friday.",
            sender="Alice <alice@acme.com>",
        )
        self.assertFalse(ok)
        self.assertIsNone(reason)


class TestNewBulkSignals(unittest.TestCase):
    """Signals added specifically for the real-mailbox escapees."""

    def test_standalone_unsubscribe_word_in_body(self) -> None:
        # NYT newsletter / DataCamp etc. just render "Unsubscribe" as a link
        # label with no surrounding "here/from/to" phrasing.
        self.assertTrue(
            is_automated_or_bulk_sender(
                payload={},
                sender="Some Brand <nytdirect@nytimes.com>",
                raw_text="...long content... | Privacy Policy | Unsubscribe | Contact Us",
            )
        )

    def test_email_subdomain_is_bulk(self) -> None:
        # email.ns.nl — common EU marketing subdomain convention.
        self.assertTrue(
            is_automated_or_bulk_sender(
                payload={},
                sender="Spoordeelwinkel <info@email.ns.nl>",
                raw_text="Ontdek de aanbieding.",
            )
        )

    def test_mailing_subdomain_is_bulk(self) -> None:
        self.assertTrue(
            is_automated_or_bulk_sender(
                payload={},
                sender="ITALO <italo@mailing.italotreno.it>",
                raw_text="Scopri le novita.",
            )
        )

    def test_comms_subdomain_is_bulk(self) -> None:
        self.assertTrue(
            is_automated_or_bulk_sender(
                payload={},
                sender="Vueling <vueling@comms.vueling.com>",
                raw_text="Longer days to get away",
            )
        )

    def test_news_dash_subdomain_is_bulk(self) -> None:
        # e.g. news-hb.hugoboss.com
        self.assertTrue(
            is_automated_or_bulk_sender(
                payload={},
                sender="BOSS <boss@news-hb.hugoboss.com>",
                raw_text="Discover the new",
            )
        )

    def test_emailmarket_subdomain_is_bulk(self) -> None:
        self.assertTrue(
            is_automated_or_bulk_sender(
                payload={},
                sender="SHEIN <shein@emailmarket.shein.com>",
                raw_text="Style playbook",
            )
        )

    def test_numbered_email_subdomain_is_bulk(self) -> None:
        # email2.microsoft.com
        self.assertTrue(
            is_automated_or_bulk_sender(
                payload={},
                sender="Best of MSN <msn@email2.microsoft.com>",
                raw_text="Daily digest",
            )
        )

    def test_lottery_domain_is_bulk(self) -> None:
        # info@postcodeloterij.nl — role-local + lottery domain.
        self.assertTrue(
            is_automated_or_bulk_sender(
                payload={},
                sender="Postcode Loterij <info@postcodeloterij.nl>",
                raw_text="Laatste kans",
            )
        )

    def test_html_heavy_body_alone_is_bulk(self) -> None:
        # Large HTML marketing body with no unsubscribe word but classic
        # cellpadding table layout — almost always bulk.
        html = "<!DOCTYPE html><html>" + ("<table cellpadding=\"0\"><tr><td>x</td></tr></table>" * 200) + "</html>"
        self.assertTrue(
            is_automated_or_bulk_sender(
                payload={},
                sender="Uber Eats <uber@uber.com>",
                raw_text=html,
            )
        )

    def test_info_role_local_with_html_body_is_bulk(self) -> None:
        self.assertTrue(
            is_automated_or_bulk_sender(
                payload={},
                sender="Casino <info@inbet.com>",
                raw_text="<!DOCTYPE html><html>promo content</html>",
            )
        )

    def test_info_role_local_with_short_plain_body_not_bulk(self) -> None:
        # We don't want to nuke every ``info@`` reply — a short plain-text
        # one should still pass through unless another signal appears.
        self.assertFalse(
            is_automated_or_bulk_sender(
                payload={"headers": {"From": "Info <info@smallbiz.co>"}},
                sender="Info <info@smallbiz.co>",
                raw_text="Hi Vanesa, yes Friday works for the call. Thanks.",
            )
        )

    def test_calendar_cancellation_subject_is_marketing(self) -> None:
        # Bulgarian Google Calendar cancellation subject.
        subj = "Анулирано събитие: Weekly @ пт 2026.05.22 12:00 - 13:00 (Гринуич+2)"
        self.assertTrue(
            is_likely_marketing_or_newsletter(
                payload={}, subject=subj, raw_text="Това събитие бе отменено."
            )
        )

    def test_calendar_tail_alone_is_marketing(self) -> None:
        # Even without a recognizable verb prefix, the "@ date time" tail
        # is a strong enough signal.
        subj = "Team Standup @ Mon 2026.05.20 09:00 (GMT+2)"
        self.assertTrue(
            is_likely_marketing_or_newsletter(
                payload={}, subject=subj, raw_text="x"
            )
        )

    def test_dutch_promo_subject_suppressed(self) -> None:
        # "Laatste kans om gratis mee te spelen" — Dutch lottery promo.
        ok, reason = should_suppress_as_non_actionable(
            payload={},
            subject="Miljoenenjacht | Laatste kans om gratis mee te spelen",
            raw_text="Klik hieronder.",
            sender="Postcode Loterij <info@postcodeloterij.nl>",
        )
        self.assertTrue(ok)

    def test_real_dinner_invitation_not_calendar_notification(self) -> None:
        # "Dinner @ 8" is NOT a calendar notification tail because it lacks a
        # full date pattern.
        self.assertFalse(
            is_likely_marketing_or_newsletter(
                payload={},
                subject="Dinner @ 8",
                raw_text="Want to join us tomorrow?",
            )
        )


if __name__ == "__main__":
    unittest.main()
