"""BookingInvoiceService — create invoices with CUSTOM line items for bookings."""
import uuid
from datetime import datetime

from vbwd.models.enums import InvoiceStatus, LineItemType
from vbwd.models.invoice import UserInvoice
from vbwd.models.invoice_line_item import InvoiceLineItem


class BookingInvoiceService:
    def __init__(self, session, invoice_prefix="BK"):
        self.session = session
        self.invoice_prefix = invoice_prefix

    def create_booking_invoice(self, user_id, resource, booking) -> UserInvoice:
        """Create an invoice with a CUSTOM line item for a booking."""
        total_amount = resource.price * booking.quantity

        invoice = UserInvoice()
        invoice.user_id = user_id
        invoice.invoice_number = f"{self.invoice_prefix}-{uuid.uuid4().hex[:8].upper()}"
        invoice.amount = total_amount
        invoice.currency = resource.currency or "EUR"
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
        line_item.unit_price = resource.price
        line_item.total_price = total_amount
        line_item.extra_data = {
            "plugin": "booking",
            "booking_id": str(booking.id),
            "resource_slug": resource.slug,
            "resource_name": resource.name,
            "resource_type": resource.custom_schema.slug if resource.custom_schema else "unclassified",
            "start_at": booking.start_at.isoformat(),
            "end_at": booking.end_at.isoformat(),
            "custom_fields": booking.custom_fields or {},
        }
        self.session.add(line_item)
        self.session.flush()

        return invoice
