import logging

from django.core.management.base import BaseCommand
from django.db import transaction

from citation import models
from citation.signals import notify_publications_changed

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Removes orphans from Platform and Sponsors Table"

    @transaction.atomic
    def handle(self, *args, **options):
        qs = models.Platform.objects.exclude(
            pk__in=models.Publication.platforms.through.objects.values("platform")
        )
        platform_orphans = list(qs.values_list("pk", "name"))
        platform_ids = tuple(pk for pk, _ in platform_orphans)
        logger.info(
            "              -----------------------------------------------------------------           "
        )
        logger.info("                    Following platform orphans has been deleted: ")
        logger.info(
            "              -----------------------------------------------------------------           "
        )
        logger.info("\n".join(name for _, name in platform_orphans))
        logger.info("Total platforms deleted: %s", len(platform_orphans))
        qs.delete()
        notify_publications_changed(
            sender=models.Platform,
            publication_ids=(),
            related_ids=platform_ids,
        )
        qs = models.Sponsor.objects.exclude(
            pk__in=models.Publication.sponsors.through.objects.values("sponsor")
        )
        sponsor_orphans = list(qs.values_list("pk", "name"))
        sponsor_ids = tuple(pk for pk, _ in sponsor_orphans)
        logger.info(
            "              -----------------------------------------------------------------            "
        )
        logger.info(
            "                     Following sponsor orphans has been deleted:                           "
        )
        logger.info(
            "              -----------------------------------------------------------------            "
        )
        logger.info("\n".join(name for _, name in sponsor_orphans))
        logger.info("Total sponsors deleted: %s", len(sponsor_orphans))
        qs.delete()
        notify_publications_changed(
            sender=models.Sponsor,
            publication_ids=(),
            related_ids=sponsor_ids,
        )
        logger.debug("Orphans deleted successfully")
