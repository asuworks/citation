from django.contrib.auth.models import User
from django.test import TestCase

from citation.graphviz.data import (
    filtered_publications,
    generate_aggregated_code_archived_platform_data,
    generate_aggregated_distribution_data,
)
from citation.models import (
    Author,
    CodeArchiveUrl,
    CodeArchiveUrlCategory,
    Container,
    Publication,
    PublicationAuthors,
)


class GraphDataFilterTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="graph-data-user")
        container = Container.objects.create(name="Graph Data Journal")
        ada = Author.objects.create(
            given_name="Ada",
            family_name="Modeler",
            type=Author.INDIVIDUAL,
        )
        grace = Author.objects.create(
            given_name="Grace",
            family_name="Researcher",
            type=Author.INDIVIDUAL,
        )
        self.in_range = Publication.objects.create(
            title="In range",
            date_published_text="2019",
            status=Publication.Status.REVIEWED,
            container=container,
            added_by=self.user,
        )
        PublicationAuthors.objects.create(
            publication=self.in_range,
            author=ada,
            role=PublicationAuthors.RoleChoices.AUTHOR,
        )
        self.out_of_range = Publication.objects.create(
            title="Out of range",
            date_published_text="2021",
            status=Publication.Status.REVIEWED,
            container=container,
            added_by=self.user,
        )
        PublicationAuthors.objects.create(
            publication=self.out_of_range,
            author=ada,
            role=PublicationAuthors.RoleChoices.AUTHOR,
        )
        self.in_range_other_author = Publication.objects.create(
            title="In range, other author",
            date_published_text="2019",
            status=Publication.Status.REVIEWED,
            container=container,
            added_by=self.user,
        )
        PublicationAuthors.objects.create(
            publication=self.in_range_other_author,
            author=grace,
            role=PublicationAuthors.RoleChoices.AUTHOR,
        )

    def test_filters_by_iso_year_without_mutating_input(self):
        criteria = {
            "is_primary": True,
            "status": Publication.Status.REVIEWED,
            "date_published__gte": "2019-01-01T00:00:00Z",
            "date_published__lte": "2019-12-31T00:00:00Z",
        }
        original_criteria = criteria.copy()

        publications = filtered_publications(criteria)
        distribution = generate_aggregated_distribution_data(
            criteria,
            classifier="general",
            name="Publications",
        )

        self.assertEqual(
            {publication.pk for publication in publications},
            {self.in_range.pk, self.in_range_other_author.pk},
        )
        self.assertEqual(criteria, original_criteria)
        self.assertEqual(len(distribution), 1)
        self.assertEqual(distribution[0]["date"], 2019)
        self.assertEqual(distribution[0]["Code Not Available"], 2)

    def test_filters_by_author_without_mutating_input(self):
        criteria = {
            "is_primary": True,
            "status": Publication.Status.REVIEWED,
            "authors__name__exact": "Ada Modeler",
        }
        original_criteria = criteria.copy()

        publications = filtered_publications(criteria)

        self.assertEqual(
            {publication.pk for publication in publications},
            {self.in_range.pk, self.out_of_range.pk},
        )
        self.assertEqual(criteria, original_criteria)

    def test_counts_current_archive_categories_for_matching_publications(self):
        category = CodeArchiveUrlCategory.objects.create(
            category="Archive",
            subcategory="Test archive",
        )
        CodeArchiveUrl.objects.create(
            publication=self.in_range,
            category=category,
            status=CodeArchiveUrl.STATUS.available,
            creator=self.user,
            url="https://example.com/model",
        )
        CodeArchiveUrl.objects.create(
            publication=self.out_of_range,
            category=category,
            status=CodeArchiveUrl.STATUS.available,
            creator=self.user,
            url="https://example.com/out-of-range-model",
        )

        counts = generate_aggregated_code_archived_platform_data(
            {
                "is_primary": True,
                "date_published__gte": "2019-01-01T00:00:00Z",
                "date_published__lte": "2019-12-31T00:00:00Z",
            }
        )

        self.assertEqual(counts["Archive"], 1)
        self.assertEqual(sum(counts.values()), 1)
