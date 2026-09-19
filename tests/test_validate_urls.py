from unittest.mock import call, patch

import requests
from django.core.management import call_command
from django.test import TestCase

from citation import models


class ValidateUrlsCommandTest(TestCase):
    @patch("citation.signals.publications_changed.send_robust")
    @patch("citation.models.requests.get")
    def test_connection_failure_does_not_abort_remaining_urls(self, get, send_robust):
        user = models.User.objects.create_user(username="url-checker")
        container = models.Container.objects.create(name="Journal")
        publication = models.Publication.objects.create(
            title="URL validation publication",
            added_by=user,
            container=container,
        )
        category = models.CodeArchiveUrlCategory.objects.get(category="Unknown")
        unreachable = models.CodeArchiveUrl.objects.create(
            publication=publication,
            category=category,
            status=models.CodeArchiveUrl.STATUS.available,
            creator=user,
            url="https://unreachable.example/",
        )
        available = models.CodeArchiveUrl.objects.create(
            publication=publication,
            category=category,
            status=models.CodeArchiveUrl.STATUS.unavailable,
            creator=user,
            url="https://available.example/",
        )
        successful_response = requests.Response()
        successful_response.status_code = 200
        successful_response.reason = "OK"
        get.side_effect = [
            requests.ConnectionError("DNS failure"),
            successful_response,
        ]

        with self.captureOnCommitCallbacks(execute=True):
            call_command("validate_urls")

        unreachable.refresh_from_db()
        available.refresh_from_db()
        self.assertEqual(unreachable.status, models.CodeArchiveUrl.STATUS.unavailable)
        self.assertEqual(available.status, models.CodeArchiveUrl.STATUS.available)
        failed_log = models.URLStatusLog.objects.get(url=unreachable.url)
        self.assertEqual(failed_log.status_code, 0)
        self.assertEqual(failed_log.status_reason, "DNS failure")
        self.assertTrue(models.URLStatusLog.objects.filter(url=available.url).exists())
        self.assertEqual(
            send_robust.call_args_list,
            [
                call(
                    sender=models.CodeArchiveUrl,
                    publication_ids=(publication.pk,),
                    related_ids=(),
                ),
                call(
                    sender=models.CodeArchiveUrl,
                    publication_ids=(publication.pk,),
                    related_ids=(),
                ),
            ],
        )
