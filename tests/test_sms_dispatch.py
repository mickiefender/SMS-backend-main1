from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from apps.messaging.models import SMSJob
from apps.messaging.services.arkesel import ArkeselError
from apps.messaging.services.sms import dispatch_sms_job, send_sms
from apps.schools.models import School


class SmsDispatchTests(SimpleTestCase):
    def make_job(self, messages, status="queued"):
        job = Mock()
        job.pk = 41
        job.status = status
        job.school = Mock()
        job.messages.filter.return_value = messages

        manager = Mock()
        manager.select_related.return_value.get.return_value = job
        return job, manager

    @patch("apps.messaging.services.sms.ArkeselProvider")
    @patch("apps.messaging.services.sms.SMSJob.objects.select_for_update")
    def test_dispatch_sends_each_recipient_and_completes_job(
        self, select_for_update, provider_class
    ):
        first, second = Mock(), Mock()
        job, manager = self.make_job([first, second])
        select_for_update.return_value = manager
        provider_class.return_value.send.return_value = {"message_id": "provider-123"}

        with patch(
            "apps.messaging.services.sms.transaction.atomic",
            return_value=nullcontext(),
        ):
            result = dispatch_sms_job(job.pk)

        self.assertIs(result, job)
        self.assertEqual(provider_class.return_value.send.call_count, 2)
        self.assertEqual(first.status, "sent")
        self.assertEqual(second.status, "sent")
        self.assertEqual(first.provider_message_id, "provider-123")
        self.assertEqual(job.status, "completed")
        self.assertIsNotNone(job.completed_at)

    @patch("apps.messaging.services.sms.refund_credits")
    @patch("apps.messaging.services.sms.ArkeselProvider")
    @patch("apps.messaging.services.sms.SMSJob.objects.select_for_update")
    def test_failed_delivery_marks_recipient_failed_and_refunds_credits(
        self, select_for_update, provider_class, refund
    ):
        sms = Mock(credits_used=2)
        job, manager = self.make_job([sms])
        select_for_update.return_value = manager
        provider_class.return_value.send.side_effect = ArkeselError("Provider rejected the request.")

        with patch(
            "apps.messaging.services.sms.transaction.atomic",
            return_value=nullcontext(),
        ):
            result = dispatch_sms_job(job.pk)

        self.assertIs(result, job)
        self.assertEqual(sms.status, "failed")
        self.assertEqual(sms.error_message, "Provider rejected the request.")
        self.assertEqual(job.status, "failed")
        refund.assert_called_once_with(job.school, 2, job=job)

    @patch("apps.messaging.services.sms.ArkeselProvider")
    @patch("apps.messaging.services.sms.SMSJob.objects.select_for_update")
    def test_terminal_or_in_progress_jobs_are_not_dispatched(
        self, select_for_update, provider_class
    ):
        job, manager = self.make_job([], status="processing")
        select_for_update.return_value = manager

        with patch(
            "apps.messaging.services.sms.transaction.atomic",
            return_value=nullcontext(),
        ):
            result = dispatch_sms_job(job.pk)

        self.assertIs(result, job)
        provider_class.assert_not_called()

    @patch("apps.messaging.services.sms.dispatch_sms_job")
    @patch("apps.messaging.services.sms.SMSMessage.objects.bulk_create")
    @patch("apps.messaging.services.sms.reserve_credits")
    @patch("apps.messaging.services.sms.SMSJob.objects.create")
    @patch("apps.messaging.models.SMSConfiguration.objects.filter")
    def test_send_sms_dispatches_before_returning(
        self,
        configuration_filter,
        create_job,
        reserve,
        bulk_create,
        dispatch,
    ):
        school = School(pk=17)
        config = SimpleNamespace(
            sender_id="ALARA",
            is_enabled=True,
            sender_id_status="approved",
        )
        configuration_filter.return_value.first.return_value = config
        job = SMSJob(pk=41, status="completed")
        create_job.return_value = job
        dispatch.return_value = job

        with patch(
            "apps.messaging.services.sms.transaction.atomic",
            return_value=nullcontext(),
        ):
            result, created = send_sms(
                school=school,
                recipients=["+233201234567"],
                message="School notice",
            )

        self.assertIs(result, job)
        self.assertTrue(created)
        dispatch.assert_called_once_with(job.pk)
        reserve.assert_called_once()
        bulk_create.assert_called_once()
