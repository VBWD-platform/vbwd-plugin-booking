"""Resource copy (duplicate) service.

Duplicates a ``BookableResource`` into a fresh, inactive copy: a new id + fresh
timestamps, a ``"<name> (Copy)"`` name, a collision-safe unique slug, and a
verbatim copy of the resource-definition fields (including the recurring
``availability`` JSON). Owned image link rows are duplicated and re-pointed at
the new resource while the shared ``cms_image`` rows they reference are left
untouched. Shared refs — taxes (M2M), categories (M2M), ``custom_schema_id`` and
``vendor_id`` — are re-pointed, never duplicated.

Deliberately NOT copied: dated one-off slot blocks (calendar exceptions on the
original, not part of the resource definition) and bookings (user transactions).
"""
import copy as copy_module

from plugins.booking.booking.models.resource import BookableResource
from plugins.booking.booking.models.resource_image import BookableResourceImage


# Resource-definition fields copied verbatim onto the duplicate. Excludes ``id``
# / timestamps (fresh), ``name`` / ``slug`` / ``is_active`` (handled explicitly)
# and the M2M relations (re-pointed separately).
COPIED_RESOURCE_FIELDS = (
    "description",
    "capacity",
    "slot_duration_minutes",
    "price",
    "price_unit",
    "custom_fields_schema",
    "image_url",
    "sort_order",
    "price_display_mode",
    "vendor_id",
    "custom_schema_id",
)

# Fields whose stored value is mutable JSON; deep-copied so the copy and the
# source never share a Python reference.
COPIED_JSON_FIELDS = ("availability", "config")

COPY_NAME_SUFFIX = " (Copy)"
COPY_SLUG_SUFFIX = "copy"


class ResourceCopyService:
    """Duplicate bookable resources (definition + image links + shared refs)."""

    def __init__(self, resource_repository):
        """Initialize ResourceCopyService.

        Args:
            resource_repository: The ``ResourceRepository`` used to look up
                sources, check slug availability, and persist copies.
        """
        self._resource_repository = resource_repository

    def copy_resources(self, resource_ids) -> list:
        """Duplicate each existing resource id; unknown ids are skipped.

        Returns the list of created ``BookableResource`` copies in request order.
        """
        copies = []
        for resource_id in resource_ids:
            source = self._resource_repository.find_by_id(resource_id)
            if source is None:
                continue
            copies.append(self.copy_resource(source))
        return copies

    def copy_resource(self, source: BookableResource) -> BookableResource:
        """Return a persisted, inactive duplicate of ``source``."""
        duplicate = BookableResource()
        duplicate.name = f"{source.name}{COPY_NAME_SUFFIX}"
        duplicate.slug = self._unique_copy_slug(source.slug)
        # Copies are never live — they must be reviewed and activated explicitly.
        duplicate.is_active = False

        for field in COPIED_RESOURCE_FIELDS:
            setattr(duplicate, field, getattr(source, field))
        for field in COPIED_JSON_FIELDS:
            setattr(duplicate, field, copy_module.deepcopy(getattr(source, field)))

        # Shared M2M refs are re-pointed onto the copy (new link rows), never
        # duplicating the referenced tax / category rows themselves.
        duplicate.taxes = list(source.taxes)
        duplicate.categories = list(source.categories)

        self._resource_repository.save(duplicate)
        self._duplicate_image_links(source, duplicate)
        return duplicate

    def _unique_copy_slug(self, source_slug: str) -> str:
        """Return the first free ``<base>-copy[-N]`` slug for ``source_slug``.

        Tries ``<base>-copy``, then ``<base>-copy-2``, ``-copy-3`` … probing the
        repository until an unused slug is found. Because each copy is flushed
        via ``save`` before the next is built, back-to-back copies within one
        request see each other and never collide on the UNIQUE slug column.
        """
        base_candidate = f"{source_slug}-{COPY_SLUG_SUFFIX}"
        if self._resource_repository.find_by_slug(base_candidate) is None:
            return base_candidate

        suffix_index = 2
        while True:
            candidate = f"{base_candidate}-{suffix_index}"
            if self._resource_repository.find_by_slug(candidate) is None:
                return candidate
            suffix_index += 1

    def _duplicate_image_links(
        self, source: BookableResource, duplicate: BookableResource
    ) -> None:
        """Copy ``source``'s image link rows, re-pointed at ``duplicate``.

        Each new ``BookableResourceImage`` keeps ``cms_image_id`` pointing at the
        SAME shared CMS image; only ``resource_id`` changes. The fresh
        ``resource_id`` keeps the UNIQUE(resource_id, cms_image_id) constraint
        satisfied.
        """
        source_links = (
            self._resource_repository.session.query(BookableResourceImage)
            .filter_by(resource_id=source.id)
            .order_by(BookableResourceImage.sort_order)
            .all()
        )
        for link in source_links:
            duplicate_link = BookableResourceImage()
            duplicate_link.resource_id = duplicate.id
            duplicate_link.cms_image_id = link.cms_image_id
            duplicate_link.is_primary = link.is_primary
            duplicate_link.sort_order = link.sort_order
            self._resource_repository.session.add(duplicate_link)
        self._resource_repository.session.flush()
