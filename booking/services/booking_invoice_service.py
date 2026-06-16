"""BookingInvoiceService — create invoices with CUSTOM line items for bookings."""
import uuid
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from vbwd.models.enums import InvoiceStatus, LineItemType
from vbwd.models.invoice import UserInvoice
from vbwd.models.invoice_line_item import InvoiceLineItem

_CENTS = Decimal("0.01")


class BookingInvoiceService:
    def __init__(self, session, invoice_prefix="BK", price_factory=None):
        """Initialize BookingInvoiceService.

        Args:
            session: SQLAlchemy session.
            invoice_prefix: Invoice-number prefix.
            price_factory: The core ``PriceFactory`` (D1). REQUIRED before any
                invoice is built — the charged amount is the computed
                ``Price.brutto`` and the line item records the netto + per-tax
                breakdown. S96.2 removed the legacy ``None`` fallback that
                silently recorded ``tax == 0`` (a Liskov violation for a taxed
                resource); the charge path now raises if the factory is absent.
                An untaxed resource still yields ``tax == 0`` / ``net == gross``
                because the factory computes a tax-free ``Price``.
        """
        self.session = session
        self.invoice_prefix = invoice_prefix
        self._price_factory = price_factory

    def _charge_for(self, resource, quantity):
        """Resolve (unit_price, line_total, price_breakdown, tax_fields).

        S85.2 (D8): the charged unit price is ``Price.brutto``. The invoice is an
        immutable financial record (Numeric(10,2) columns), so the brutto float
        is quantized to cents here — the one legitimate rounding boundary. S85.4:
        ``tax_fields`` carries the recorded ``net_amount`` / ``tax_amount`` /
        ``tax_breakdown`` (per-rate, quantity-scaled).

        S96.2: the ``PriceFactory`` is required. There is no silent zero-tax
        fallback — an absent factory raises so a taxed resource can never be
        invoiced tax-free. An untaxed resource flows through the same path and
        the factory simply computes a tax-free ``Price`` (net == gross).
        """
        if self._price_factory is None:
            raise ValueError(
                "BookingInvoiceService requires a PriceFactory to derive the "
                "tax breakdown — refusing to invoice without one (S96.2: no "
                "silent zero-tax fallback)."
            )

        from vbwd.pricing.line_tax_fields import line_tax_fields

        computed_price = self._price_factory.get_price_from_object(resource)
        unit_price = Decimal(str(computed_price.brutto)).quantize(
            _CENTS, rounding=ROUND_HALF_UP
        )
        breakdown = computed_price.to_dict()
        tax_fields = line_tax_fields(computed_price, quantity=quantity)
        return unit_price, unit_price * quantity, breakdown, tax_fields

    @staticmethod
    def _apply_tax_fields(invoice, line_item, total_amount, tax_fields) -> None:
        """Set the per-line tax columns and roll the invoice net/tax/gross up.

        ``tax_fields`` is always present (S96.2: the factory is required). An
        untaxed resource yields ``tax_amount == 0`` and ``net_amount ==
        total_amount`` so subtotal + tax always equals the gross total.
        """
        line_item.net_amount = tax_fields["net_amount"]
        line_item.tax_amount = tax_fields["tax_amount"]
        line_item.tax_breakdown = tax_fields["tax_breakdown"]
        invoice.subtotal = tax_fields["net_amount"]
        invoice.tax_amount = tax_fields["tax_amount"]
        invoice.total_amount = total_amount

    def create_booking_invoice(self, user_id, resource, booking) -> UserInvoice:
        """Create an invoice with a CUSTOM line item for a booking."""
        unit_price, total_amount, breakdown, tax_fields = self._charge_for(
            resource, booking.quantity
        )

        invoice = UserInvoice()
        invoice.user_id = user_id
        invoice.invoice_number = f"{self.invoice_prefix}-{uuid.uuid4().hex[:8].upper()}"
        invoice.amount = total_amount
        # S85.1 (D5): the resource no longer carries a currency; the invoice
        # keeps the model default (the global operating currency, S84).
        invoice.status = InvoiceStatus.PENDING
        invoice.invoiced_at = datetime.utcnow()
        self.session.add(invoice)
        self.session.flush()

        line_item = InvoiceLineItem()
        line_item.invoice_id = invoice.id
        line_item.item_type = LineItemType.CUSTOM
        line_item.item_id = booking.id
        line_item.description = (
            f"{resource.name} — {booking.start_at.strftime('%Y-%m-%d %H:%M')}"
        )
        line_item.quantity = booking.quantity
        line_item.unit_price = unit_price
        line_item.total_price = total_amount
        line_item.extra_data = {
            "plugin": "booking",
            "booking_id": str(booking.id),
            "resource_id": str(resource.id),
            "resource_slug": resource.slug,
            "resource_name": resource.name,
            "resource_type": resource.custom_schema.slug
            if resource.custom_schema
            else "unclassified",
            "start_at": booking.start_at.isoformat(),
            "end_at": booking.end_at.isoformat(),
            "custom_fields": booking.custom_fields or {},
        }
        # S85.2: persist the per-line netto + per-tax breakdown from the Price
        # VO (recorded tax split for the charged brutto).
        line_item.extra_data["price_breakdown"] = breakdown
        # S85.4: set first-class per-rate tax columns + roll the invoice up.
        self._apply_tax_fields(invoice, line_item, total_amount, tax_fields)
        self.session.add(line_item)
        self.session.flush()

        return invoice

    def create_checkout_invoice(
        self,
        user_id,
        resource,
        start_at,
        end_at,
        quantity: int = 1,
        custom_fields: dict | None = None,
        notes: str | None = None,
    ) -> UserInvoice:
        """Create an invoice for booking checkout — no Booking record needed yet.

        All booking metadata is stored in line_item.extra_data so the
        payment handler can create the Booking after payment succeeds.
        """
        unit_price, total_amount, breakdown, tax_fields = self._charge_for(
            resource, quantity
        )

        invoice = UserInvoice()
        invoice.user_id = user_id
        invoice.invoice_number = f"{self.invoice_prefix}-{uuid.uuid4().hex[:8].upper()}"
        # Set all three so downstream consumers (e.g. token-balance payment,
        # which charges on total_amount) have a non-null total. The net / tax
        # split is filled in below via _apply_tax_fields (S85.4).
        invoice.amount = total_amount
        invoice.subtotal = total_amount
        invoice.total_amount = total_amount
        # S85.1 (D5): the resource no longer carries a currency; the invoice
        # keeps the model default (the global operating currency, S84).
        invoice.status = InvoiceStatus.PENDING
        invoice.invoiced_at = datetime.utcnow()
        self.session.add(invoice)
        self.session.flush()

        line_item = InvoiceLineItem()
        line_item.invoice_id = invoice.id
        line_item.item_type = LineItemType.CUSTOM
        line_item.item_id = resource.id
        line_item.description = (
            f"{resource.name} — {start_at.strftime('%Y-%m-%d %H:%M')}"
        )
        line_item.quantity = quantity
        line_item.unit_price = unit_price
        line_item.total_price = total_amount
        line_item.extra_data = {
            "plugin": "booking",
            "resource_id": str(resource.id),
            "resource_slug": resource.slug,
            "resource_name": resource.name,
            "resource_type": (
                resource.custom_schema.slug
                if resource.custom_schema
                else "unclassified"
            ),
            "start_at": start_at.isoformat(),
            "end_at": end_at.isoformat(),
            "quantity": quantity,
            "custom_fields": custom_fields or {},
            "notes": notes,
        }
        # S85.2: persist the per-line netto + per-tax breakdown from the Price
        # VO (recorded tax split for the charged brutto).
        line_item.extra_data["price_breakdown"] = breakdown
        # S85.4: set first-class per-rate tax columns + roll the invoice up.
        self._apply_tax_fields(invoice, line_item, total_amount, tax_fields)
        self.session.add(line_item)
        self.session.flush()

        return invoice
