"""BookableResource carries a nullable ``vendor_id`` and serialises it.

Ownership: a vendor-owned resource records the owning user's id; a
platform-owned resource leaves it ``None``. ``to_dict`` exposes it so the admin
UI / marketplace can read the owner.
"""
from uuid import uuid4

from plugins.booking.booking.models.resource import BookableResource


def test_resource_to_dict_includes_vendor_id():
    vendor_id = uuid4()
    resource = BookableResource(
        id=uuid4(),
        name="Vendor Room",
        slug=f"vr-{uuid4().hex[:8]}",
        price=10.0,
        vendor_id=vendor_id,
    )
    serialized = resource.to_dict()
    assert "vendor_id" in serialized
    assert serialized["vendor_id"] == str(vendor_id)


def test_resource_to_dict_vendor_id_none_for_platform_resource():
    resource = BookableResource(
        id=uuid4(),
        name="Platform Room",
        slug=f"pr-{uuid4().hex[:8]}",
        price=10.0,
    )
    assert resource.to_dict()["vendor_id"] is None
