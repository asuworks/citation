import logging
from collections import Counter
from datetime import datetime

from django.db.models import Count, Value
from django.db.models.functions import Concat

from ..models import CodeArchiveUrl, CodeArchiveUrlCategory, Publication
from .globals import NetworkGroupByType

logger = logging.getLogger(__name__)


def _year(value):
    if hasattr(value, "year"):
        return value.year
    return datetime.fromisoformat(str(value)).year


def filtered_publications(filter_criteria, require_year=False):
    criteria = dict(filter_criteria or {})
    start_value = criteria.pop("date_published__gte", None)
    end_value = criteria.pop("date_published__lte", None)
    author_name = criteria.pop("authors__name__exact", None)

    publications = Publication.objects.filter(**criteria)
    if author_name:
        publications = publications.annotate(
            author_full_name=Concat(
                "creators__given_name", Value(" "), "creators__family_name"
            )
        ).filter(author_full_name=author_name)
    publications = publications.distinct()

    start_year = _year(start_value) if start_value else None
    end_year = _year(end_value) if end_value else None
    if start_year is None and end_year is None and not require_year:
        return list(publications)

    result = []
    for publication in publications:
        year = publication.year_published
        if year is None:
            continue
        year = int(year)
        if start_year is not None and year < start_year:
            continue
        if end_year is not None and year > end_year:
            continue
        result.append(publication)
    return result


def publication_ids_for_filters(filter_criteria):
    return [publication.pk for publication in filtered_publications(filter_criteria)]


class NetworkData:
    def __init__(self, nodes, links, filter_value):
        self.graph = {"links": links, "nodes": nodes}
        self.filter_value = filter_value


# Generates unique list of nodes that will be used in network based on the provided link list
def generate_node_candidates(links_candidates):
    nodes = set()
    for source, target in links_candidates:
        nodes.add(source)
        nodes.add(target)
    return list(nodes)


# Generates links that will be used to form the network based on the provided filter criteria
def generate_link_candidates(filter_criteria):
    primary_pubs = filtered_publications(filter_criteria, require_year=True)
    primary_pk = [publication.pk for publication in primary_pubs]

    # fetches links that satisfies the given filter
    links_candidates = (
        Publication.api.primary()
        .filter(pk__in=primary_pk, citations__in=primary_pubs)
        .values_list("pk", "citations")
    )
    return links_candidates


def get_network_default_filter(group_by):
    if group_by == NetworkGroupByType.SPONSOR.value:
        return Publication.api.get_top_records(attribute="sponsors__name")
    else:
        return Publication.api.get_top_records(attribute="tags__name")


def generate_network_graph(filter_criteria, group_by=NetworkGroupByType.TAGS.value):
    filter_criteria = dict(filter_criteria)
    if group_by + "__name__in" in filter_criteria:
        filter_value = list(filter_criteria[group_by + "__name__in"])
    else:
        filter_value = list(get_network_default_filter(group_by))
        filter_criteria[group_by + "__name__in"] = filter_value

    # fetches links that satisfies the given filter
    links_candidates = generate_link_candidates(filter_criteria)

    # discarding rest keeping only nodes used in forming network link
    nodes_candidates = generate_node_candidates(links_candidates)

    # Forming network group
    nodes = get_nodes(nodes_candidates, filter_value, group_by)
    links = get_links(links_candidates, nodes_candidates)

    filter_value.append("Others")
    return NetworkData(nodes, links, filter_value)


def get_links(links_candidates, nodes_index):
    links = []
    for source, target in links_candidates:
        links.append(
            {
                "source": nodes_index.index(source),
                "target": nodes_index.index(target),
                "value": 1,
            }
        )
    return links


def get_nodes(nodes_candidates, filter_value, group_by):
    publications = Publication.api.primary(status="REVIEWED")
    nodes = []
    for pub in nodes_candidates:
        publication = publications.get(pk=pub)
        if group_by == NetworkGroupByType.SPONSOR.value:
            related = publication.sponsors
        else:
            related = publication.tags
        group_values = list(related.values_list("name", flat=True))

        value = get_common_value(group_values, filter_value)
        if value:
            group = value
        else:
            group = "Others"

        nodes.append(
            {
                "name": pub,
                "group": group,
                "tags": ", ".join(s.name for s in publication.tags.all()),
                "sponsors": ", ".join(s.name for s in publication.sponsors.all()),
                "Authors": ", ".join(
                    f"{creator.family_name}, {creator.given_name_initial}."
                    for creator in publication.creators.all()
                ),
                "title": publication.title,
            }
        )
    return nodes


def get_common_value(first, second):
    """
    :param first: list
    :param second: list
    :return: first common value found
    """
    for value in first:
        if value in second:
            return value
    return None


def generate_aggregated_distribution_data(filter_criteria, classifier, name):
    pubs = filtered_publications(filter_criteria)
    availability = Counter()
    non_availability = Counter()
    years_list = []
    if pubs:
        for pub in pubs:
            is_archived = pub.is_archived
            date_published = int(pub.year_published) if pub.year_published else None
            if date_published is not None:
                years_list.append(date_published)
                bucket = availability if is_archived else non_availability
                bucket[date_published] += 1

        distribution_data = []
        count = len(years_list)
        for year in set(years_list):
            present = availability[year] * 100 / count
            absent = non_availability[year] * 100 / count
            total = present + absent
            distribution_data.append(
                {
                    "relation": classifier,
                    "name": name,
                    "date": year,
                    "Code Available": availability[year],
                    "Code Not Available": non_availability[year],
                    "Code Available Per": present * 100 / total,
                    "Code Not Available Per": absent * 100 / total,
                }
            )

        return distribution_data
    return []


def generate_aggregated_code_archived_platform_data(filter_criteria=None):
    if filter_criteria is None:
        filter_criteria = {}
    publication_ids = publication_ids_for_filters(filter_criteria)
    counts = {
        category: 0
        for category in CodeArchiveUrlCategory.objects.order_by()
        .values_list("category", flat=True)
        .distinct()
    }
    rows = (
        CodeArchiveUrl.api.active(publication_id__in=publication_ids)
        .values("category__category")
        .annotate(count=Count("publication_id", distinct=True))
    )
    counts.update({row["category__category"]: row["count"] for row in rows})
    return counts
