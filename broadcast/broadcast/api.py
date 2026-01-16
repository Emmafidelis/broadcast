import frappe
from frappe import _
from frappe.utils import now_datetime, get_datetime, add_to_date, cstr
from datetime import timedelta


def _get_ads_between(start_dt, end_dt, filters, fields):
    start_date = start_dt.date()
    end_date = end_dt.date()
    start_time = start_dt.time().strftime("%H:%M:%S")
    end_time = end_dt.time().strftime("%H:%M:%S")

    def _fetch(extra_filters):
        return frappe.get_all(
            "Advertisement Broadcast",
            fields=fields,
            filters=filters + extra_filters,
            order_by="scheduled_date, scheduled_time",
        )

    if start_date == end_date:
        return _fetch(
            [
                ["scheduled_date", "=", start_date.isoformat()],
                ["scheduled_time", "between", [start_time, end_time]],
            ]
        )

    records = []
    seen = set()

    chunks = [
        _fetch(
            [
                ["scheduled_date", "=", start_date.isoformat()],
                ["scheduled_time", ">=", start_time],
            ]
        ),
        _fetch(
            [
                ["scheduled_date", "=", end_date.isoformat()],
                ["scheduled_time", "<=", end_time],
            ]
        ),
    ]

    if (end_date - start_date).days > 1:
        mid_start = (start_date + timedelta(days=1)).isoformat()
        mid_end = (end_date - timedelta(days=1)).isoformat()
        chunks.append(
            _fetch([["scheduled_date", "between", [mid_start, mid_end]]])
        )

    for chunk in chunks:
        for row in chunk:
            if row.name not in seen:
                seen.add(row.name)
                records.append(row)

    return records
import json


# ⭐ FRAPPE BEST PRACTICE: Simple @frappe.whitelist() decorator
@frappe.whitelist()
def log_detected_broadcast(
    advertisement_id, detected_datetime, duration, confidence, notes=None
):
    """
    API method to log detected broadcast

    Called via:
    - HTTP: POST /api/method/broadcast.broadcast.api.log_detected_broadcast
    - Frappe: frappe.call('broadcast.broadcast.api.log_detected_broadcast', {...})
    - Hooks: frappe.get_attr('broadcast.broadcast.api.log_detected_broadcast')
    """
    try:
        # Validate inputs using frappe's built-in validation
        if not advertisement_id:
            frappe.throw(_("Advertisement ID is required"))

        if not frappe.db.exists("Advertisement Broadcast", advertisement_id):
            frappe.throw(
                _("Advertisement Broadcast {0} not found").format(advertisement_id)
            )

        # Get document using frappe's ORM
        ad_broadcast = frappe.get_doc("Advertisement Broadcast", advertisement_id)

        # Validate permissions using frappe's permission system
        ad_broadcast.check_permission("write")

        # Validate confidence threshold
        min_confidence = (
            frappe.db.get_single_value(
                "Broadcasting Settings", "min_detection_confidence"
            )
            or 80
        )
        confidence = frappe.utils.flt(confidence)

        if confidence < min_confidence:
            return {
                "status": "warning",
                "message": _("Detection confidence {0}% below threshold {1}%").format(
                    confidence, min_confidence
                ),
                "requires_manual_verification": True,
            }

        # Use document method to log broadcast
        ad_broadcast.log_broadcast(
            actual_datetime=detected_datetime,
            actual_duration=frappe.utils.cint(duration),
            logged_by=frappe.session.user,
            broadcast_type="Auto Detection",
            confidence=confidence,
            notes=notes or _("Automatically detected broadcast"),
        )

        return {
            "status": "success",
            "message": _("Broadcast logged successfully"),
            "advertisement_broadcast": ad_broadcast.name,
            "invoice_generated": bool(ad_broadcast.sales_invoice),
        }

    except frappe.ValidationError as e:
        frappe.local.response["http_status_code"] = 400
        return {"status": "error", "message": str(e)}

    except frappe.PermissionError as e:
        frappe.local.response["http_status_code"] = 403
        return {"status": "error", "message": _("Permission denied")}

    except Exception as e:
        frappe.log_error(
            message=frappe.get_traceback(), title="Log Detected Broadcast Error"
        )
        frappe.local.response["http_status_code"] = 500
        return {"status": "error", "message": _("Internal server error")}


@frappe.whitelist()
def get_scheduled_broadcasts(hours_ahead=24):
    """
    Get scheduled broadcasts for specified hours ahead

    Called via:
    - HTTP: GET /api/method/broadcast.broadcast.api.get_scheduled_broadcasts
    - Frappe: frappe.call('broadcast.broadcast.api.get_scheduled_broadcasts')
    """
    try:
        hours_ahead = frappe.utils.cint(hours_ahead) or 24

        # Use frappe's date utilities
        start_time = now_datetime()
        end_time = add_to_date(start_time, hours=hours_ahead)

        broadcasts = _get_ads_between(
            start_time,
            end_time,
            filters=[["status", "=", "Scheduled"], ["docstatus", "=", 1]],
            fields=[
                "name",
                "advertisement_title",
                "customer",
                "scheduled_date",
                "scheduled_time",
                "duration_seconds",
                "presenter",
                "priority",
                "total_amount",
                "audio_file",
                "autoplay_enabled",
                "payment_status",
                "sales_order",
                "sales_invoice",
            ],
        )

        # Check read permissions for each record
        filtered_broadcasts = []
        for broadcast in broadcasts:
            if frappe.has_permission("Advertisement Broadcast", "read", broadcast.name):
                # Check if autoplay is allowed
                doc = frappe.get_doc("Advertisement Broadcast", broadcast.name)
                autoplay_check = doc.check_payment_and_autoplay()
                broadcast["payment_status"] = doc.payment_status
                broadcast["sales_invoice"] = doc.sales_invoice
                broadcast["autoplay_allowed"] = autoplay_check.get("allowed", False)
                broadcast["autoplay_reason"] = autoplay_check.get("reason", "")
                filtered_broadcasts.append(broadcast)

        return {
            "status": "success",
            "broadcasts": filtered_broadcasts,
            "total_count": len(filtered_broadcasts),
        }

    except Exception as e:
        frappe.log_error(
            message=frappe.get_traceback(), title="Get Scheduled Broadcasts Error"
        )
        return {"status": "error", "message": _("Failed to fetch scheduled broadcasts")}


@frappe.whitelist()
def manual_broadcast_log(
    advertisement_id, actual_datetime, actual_duration, notes=None
):
    """
    Manual broadcast logging for presenters

    Called via:
    - HTTP: POST /api/method/broadcast.broadcast.api.manual_broadcast_log
    - JavaScript: frappe.call('broadcast.broadcast.api.manual_broadcast_log', {...})
    """
    try:
        if not advertisement_id:
            frappe.throw(_("Advertisement ID is required"))

        ad_broadcast = frappe.get_doc("Advertisement Broadcast", advertisement_id)
        ad_broadcast.check_permission("write")

        # Log the broadcast using document method
        ad_broadcast.log_broadcast(
            actual_datetime=actual_datetime,
            actual_duration=frappe.utils.cint(actual_duration),
            logged_by=frappe.session.user,
            broadcast_type="Manual Entry",
            notes=notes or _("Manually logged broadcast"),
        )

        return {
            "status": "success",
            "message": _("Broadcast logged manually"),
            "advertisement_broadcast": ad_broadcast.name,
        }

    except Exception as e:
        frappe.log_error(
            message=frappe.get_traceback(), title="Manual Broadcast Log Error"
        )
        frappe.local.response["http_status_code"] = 400
        return {"status": "error", "message": str(e)}


@frappe.whitelist()
def sync_detection_system():
    """
    Sync with external detection system - called by scheduler
    This method can be called from hooks.py scheduler_events
    """
    try:
        # Get all active advertisements for next 4 hours
        upcoming_ads = get_scheduled_broadcasts(hours_ahead=4)

        if upcoming_ads.get("status") == "success":
            broadcasts = upcoming_ads.get("broadcasts", [])

            # Log sync activity
            frappe.logger().info(
                f"Synced {len(broadcasts)} advertisements with detection system"
            )

            # You could call external system here if needed
            # But keeping it Frappe-only as requested

            return {"status": "success", "synced_count": len(broadcasts)}

    except Exception as e:
        frappe.log_error(
            message=frappe.get_traceback(), title="Detection System Sync Error"
        )
        return {"status": "error", "message": str(e)}


@frappe.whitelist()
def notify_detection_system(doc, method):
    """
    Called when Advertisement Broadcast is submitted
    This is called from hooks.py doc_events
    """
    try:
        if doc.doctype == "Advertisement Broadcast" and method == "on_submit":
            # Notify that new ad is scheduled
            frappe.logger().info(f"New advertisement scheduled: {doc.name}")

            # Create a background job using frappe.enqueue
            frappe.enqueue(
                method="broadcast.broadcast.api.process_new_advertisement",
                queue="short",
                advertisement_id=doc.name,
                is_async=True,
            )

    except Exception as e:
        frappe.log_error(
            message=frappe.get_traceback(), title="Detection System Notification Error"
        )


def process_new_advertisement(advertisement_id):
    """
    Background job to process new advertisement
    Called asynchronously via frappe.enqueue
    """
    try:
        ad_doc = frappe.get_doc("Advertisement Broadcast", advertisement_id)

        # Process the advertisement (e.g., prepare for detection)
        frappe.logger().info(f"Processing new advertisement: {advertisement_id}")

        # Update some status or send notification
        # This runs in background without blocking the UI

    except Exception as e:
        frappe.log_error(
            message=frappe.get_traceback(), title="Process New Advertisement Error"
        )


@frappe.whitelist()
def cancel_detection_monitoring(doc, method):
    """
    Called when Advertisement Broadcast is cancelled
    This is called from hooks.py doc_events
    """
    try:
        if doc.doctype == "Advertisement Broadcast" and method == "on_cancel":
            # Cancel any monitoring for this advertisement
            frappe.logger().info(f"Advertisement cancelled: {doc.name}")

            # You could cancel external monitoring here if needed
            # But keeping it Frappe-only as requested

    except Exception as e:
        frappe.log_error(
            message=frappe.get_traceback(), title="Cancel Detection Monitoring Error"
        )


@frappe.whitelist()
def send_scheduling_notification(doc, method):
    """
    Send notification when advertisement is scheduled
    This is called from hooks.py doc_events
    """
    try:
        if doc.doctype == "Advertisement Broadcast" and method == "after_insert":
            frappe.logger().info(f"New advertisement scheduled: {doc.name}")

            # Send email notification to presenter
            if doc.presenter:
                frappe.sendmail(
                    recipients=[doc.presenter],
                    subject=f"New Advertisement Scheduled - {doc.advertisement_title}",
                    message=f"""
                    New Advertisement Scheduled
                    
                    Advertisement: {doc.advertisement_title}
                    Customer: {doc.customer}
                    Scheduled: {doc.scheduled_date} at {doc.scheduled_time}
                    Duration: {doc.duration_seconds} seconds
                    Amount: {frappe.utils.fmt_money(doc.total_amount)}
                    
                    Media File: {'Uploaded' if doc.audio_file else 'Not uploaded'}
                    Autoplay: {'Enabled' if doc.autoplay_enabled else 'Disabled'}
                    
                    Please ensure you are ready for the broadcast.
                    """,
                    reference_doctype="Advertisement Broadcast",
                    reference_name=doc.name,
                )

    except Exception as e:
        frappe.log_error(
            message=frappe.get_traceback(), title="Send Scheduling Notification Error"
        )


def sync_ad_payment_status_from_invoice(doc, method=None):
    """Sync Advertisement Broadcast payment status when Sales Invoice updates."""
    try:
        sales_orders = {
            item.sales_order for item in (doc.items or []) if item.sales_order
        }
        if not sales_orders:
            return

        ads = frappe.get_all(
            "Advertisement Broadcast",
            filters={"sales_order": ("in", list(sales_orders))},
            fields=["name"],
        )
        for ad in ads:
            ad_doc = frappe.get_doc("Advertisement Broadcast", ad.name)
            ad_doc.sales_invoice = doc.name
            ad_doc.db_set("sales_invoice", doc.name, update_modified=False)
            ad_doc.update_payment_status()
    except Exception:
        frappe.log_error(
            message=frappe.get_traceback(),
            title="Sync Advertisement Payment Status Error",
        )


@frappe.whitelist()
def sync_advertisement_payment_status(advertisement_id):
    """Manually sync payment status for a single Advertisement Broadcast."""
    doc = frappe.get_doc("Advertisement Broadcast", advertisement_id)
    doc.update_payment_status()
    return {
        "status": "success",
        "advertisement_broadcast": doc.name,
        "payment_status": doc.payment_status,
        "sales_invoice": doc.sales_invoice,
    }
