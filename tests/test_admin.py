from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase

from citation.admin import assign_curator
from citation.models import AuditLog, Container, Publication


class AssignCuratorTests(TestCase):
    def test_assignment_is_audited_and_notifies_after_commit(self):
        curator = User.objects.create_user(username="curator")
        container = Container.objects.create(name="Journal")
        first_publication = Publication.objects.create(
            title="First indexed publication",
            container=container,
            added_by=curator,
        )
        second_publication = Publication.objects.create(
            title="Second indexed publication",
            container=container,
            added_by=curator,
        )
        publication_ids = {first_publication.pk, second_publication.pk}
        request = SimpleNamespace(
            user=curator,
            POST={"assigned_curator_id": str(curator.pk)},
        )

        with (
            patch(
                "citation.signals.publications_changed.send_robust",
                return_value=[],
            ) as send_robust,
            self.captureOnCommitCallbacks(execute=True),
        ):
            assign_curator(
                None,
                request,
                Publication.objects.filter(pk__in=publication_ids),
            )
            send_robust.assert_not_called()

        self.assertEqual(
            set(
                Publication.objects.filter(assigned_curator=curator).values_list(
                    "pk", flat=True
                )
            ),
            publication_ids,
        )
        self.assertEqual(
            set(
                AuditLog.objects.filter(
                    action="UPDATE",
                    table="publication",
                ).values_list("row_id", flat=True)
            ),
            publication_ids,
        )
        send_robust.assert_called_once_with(
            sender=Publication,
            publication_ids=tuple(sorted(publication_ids)),
            related_ids=(),
        )
