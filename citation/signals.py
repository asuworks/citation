import logging

from django.db import transaction
from django.dispatch import Signal

logger = logging.getLogger(__name__)

publications_changed = Signal()


def notify_publications_changed(*, sender, publication_ids, related_ids=()):
    publication_ids = tuple(sorted({int(pk) for pk in publication_ids}))
    related_ids = tuple(sorted({int(pk) for pk in related_ids}))
    if not publication_ids and not related_ids:
        return

    def notify():
        responses = publications_changed.send_robust(
            sender=sender,
            publication_ids=publication_ids,
            related_ids=related_ids,
        )
        for receiver, response in responses:
            if isinstance(response, Exception):
                logger.error(
                    "publication change receiver %r failed",
                    receiver,
                    exc_info=(type(response), response, response.__traceback__),
                )

    transaction.on_commit(notify)
