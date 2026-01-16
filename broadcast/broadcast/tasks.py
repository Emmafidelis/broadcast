import frappe
from frappe.utils import now_datetime, get_datetime, add_to_date
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


def _get_ads_before(threshold_dt, filters, fields):
    date_str = threshold_dt.date().isoformat()
    time_str = threshold_dt.time().strftime("%H:%M:%S")

    records = []
    seen = set()

    chunks = [
        frappe.get_all(
            "Advertisement Broadcast",
            fields=fields,
            filters=filters + [["scheduled_date", "<", date_str]],
        ),
        frappe.get_all(
            "Advertisement Broadcast",
            fields=fields,
            filters=filters
            + [
                ["scheduled_date", "=", date_str],
                ["scheduled_time", "<", time_str],
            ],
        ),
    ]

    for chunk in chunks:
        for row in chunk:
            if row.name not in seen:
                seen.add(row.name)
                records.append(row)

    return records


def mark_missed_advertisements():
    """Mark advertisements as missed if not broadcasted within threshold"""

    # Get threshold from settings
    threshold_hours = (
        frappe.db.get_single_value(
            "Broadcasting Settings", "auto_mark_missed_after_hours"
        )
        or 2
    )

    # Find advertisements that should be marked as missed
    threshold_time = add_to_date(now_datetime(), hours=-threshold_hours)

    missed_ads = _get_ads_before(
        threshold_time,
        filters=[["status", "=", "Scheduled"], ["docstatus", "=", 1]],
        fields=["name", "repeat_interval_minutes"],
    )

    for ad in missed_ads:
        if ad.repeat_interval_minutes:
            continue
        try:
            ad_doc = frappe.get_doc("Advertisement Broadcast", ad.name)
            ad_doc.status = "Missed"
            ad_doc.save(ignore_permissions=True)

            # Send missed advertisement alert
            send_missed_ad_alert(ad_doc)

        except Exception as e:
            frappe.log_error(
                message=str(e), title=f"Error marking ad as missed: {ad_name[0]}"
            )


def send_missed_ad_alert(ad_doc):
    """Send alert for missed advertisement"""

    recipients = [ad_doc.presenter]

    # Add broadcasting managers
    managers = frappe.get_all(
        "User", filters={"role_profile_name": "Broadcasting Manager"}, fields=["email"]
    )
    recipients.extend([m.email for m in managers])

    frappe.sendmail(
        recipients=recipients,
        subject=f"URGENT: Advertisement Missed - {ad_doc.advertisement_title}",
        message=f"""
        URGENT: Advertisement has been automatically marked as MISSED
        
        Advertisement: {ad_doc.advertisement_title}
        Customer: {ad_doc.customer}
        Scheduled: {ad_doc.scheduled_date} at {ad_doc.scheduled_time}
        Presenter: {ad_doc.presenter}
        Potential Revenue Loss: {frappe.utils.fmt_money(ad_doc.total_amount)}
        Payment Status: {ad_doc.payment_status or 'Unknown'}
        
        Immediate investigation required!
        """,
        reference_doctype="Advertisement Broadcast",
        reference_name=ad_doc.name,
    )


def check_autoplay_queue():
    """Check for advertisements ready to autoplay in next 5 minutes"""
    try:
        current_time = now_datetime()
        check_until = add_to_date(current_time, minutes=5)

        base_filters = [["docstatus", "=", 1], ["autoplay_enabled", "=", 1]]
        scheduled_ads = _get_ads_between(
            current_time,
            check_until,
            filters=base_filters + [["status", "=", "Scheduled"]],
            fields=["name", "repeat_interval_minutes"],
        )
        repeating_ads = _get_ads_between(
            current_time,
            check_until,
            filters=base_filters + [["status", "=", "Aired"]],
            fields=["name", "repeat_interval_minutes"],
        )

        upcoming_ads = scheduled_ads + [
            ad for ad in repeating_ads if (ad.repeat_interval_minutes or 0) > 0
        ]

        for ad in upcoming_ads:
            try:
                ad_doc = frappe.get_doc("Advertisement Broadcast", ad.name)
                autoplay_check = ad_doc.check_payment_and_autoplay()

                if autoplay_check.get("allowed"):
                    # Queue for autoplay
                    frappe.enqueue(
                        method="broadcast.broadcast.tasks.trigger_autoplay",
                        queue="short",
                        advertisement_id=ad.name,
                        at_time=get_datetime(f"{ad_doc.scheduled_date} {ad_doc.scheduled_time}"),
                    )
                    frappe.logger().info(f"Queued autoplay for: {ad.name}")
                else:
                    # Send alert about blocked autoplay
                    send_autoplay_blocked_alert(ad_doc, autoplay_check.get("reason"))

            except Exception as e:
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=f"Error checking autoplay for {ad.name}",
                )

    except Exception as e:
        frappe.log_error(
            message=frappe.get_traceback(), title="Check Autoplay Queue Error"
        )


def trigger_autoplay(advertisement_id):
    """Trigger autoplay for advertisement"""
    try:
        ad_doc = frappe.get_doc("Advertisement Broadcast", advertisement_id)
        autoplay_check = ad_doc.check_payment_and_autoplay()

        if not autoplay_check.get("allowed"):
            frappe.logger().error(
                f"Autoplay blocked for {advertisement_id}: {autoplay_check.get('reason')}"
            )
            send_autoplay_blocked_alert(ad_doc, autoplay_check.get("reason"))
            return

        # Log that autoplay was triggered
        frappe.logger().info(f"Autoplay triggered for: {advertisement_id}")

        # Send notification to external autoplay system
        send_autoplay_command(ad_doc)

        # Send confirmation email
        frappe.sendmail(
            recipients=[ad_doc.presenter],
            subject=f"Autoplay Triggered - {ad_doc.advertisement_title}",
            message=f"""
            Autoplay has been triggered for your advertisement.
            
            Advertisement: {ad_doc.advertisement_title}
            Customer: {ad_doc.customer}
            Scheduled: {ad_doc.scheduled_date} at {ad_doc.scheduled_time}
            Audio File: {ad_doc.audio_file}
            
            The system will automatically log the broadcast.
            """,
            reference_doctype="Advertisement Broadcast",
            reference_name=ad_doc.name,
        )

        if ad_doc.repeat_interval_minutes:
            scheduled_dt = get_datetime(
                f"{ad_doc.scheduled_date} {ad_doc.scheduled_time}"
            )
            next_dt = add_to_date(
                scheduled_dt, minutes=ad_doc.repeat_interval_minutes
            )
            if ad_doc.repeat_until_date and next_dt.date() > ad_doc.repeat_until_date:
                frappe.db.set_value(
                    "Advertisement Broadcast",
                    ad_doc.name,
                    {
                        "autoplay_enabled": 0,
                        "repeat_interval_minutes": 0,
                    },
                    update_modified=False,
                )
            else:
                frappe.db.set_value(
                    "Advertisement Broadcast",
                    ad_doc.name,
                    {
                        "scheduled_date": next_dt.date().isoformat(),
                        "scheduled_time": next_dt.time().strftime("%H:%M:%S"),
                    },
                    update_modified=False,
                )

    except Exception as e:
        frappe.log_error(
            message=frappe.get_traceback(), title=f"Trigger Autoplay Error: {advertisement_id}"
        )


def send_autoplay_command(ad_doc):
    """Send command to external autoplay system"""
    autoplay_data = {
        "advertisement_id": ad_doc.name,
        "audio_file": ad_doc.audio_file,
        "scheduled_time": f"{ad_doc.scheduled_date} {ad_doc.scheduled_time}",
        "duration": ad_doc.duration_seconds,
        "customer": ad_doc.customer,
    }
    
    frappe.logger().info(f"Autoplay command sent: {autoplay_data}")
    # TODO: Implement actual integration with broadcast system


def send_autoplay_blocked_alert(ad_doc, reason):
    """Send alert when autoplay is blocked"""
    frappe.sendmail(
        recipients=[ad_doc.presenter],
        subject=f"ALERT: Autoplay Blocked - {ad_doc.advertisement_title}",
        message=f"""
        ALERT: Autoplay has been blocked for your advertisement.
        
        Advertisement: {ad_doc.advertisement_title}
        Customer: {ad_doc.customer}
        Scheduled: {ad_doc.scheduled_date} at {ad_doc.scheduled_time}
        
        Reason: {reason}
        
        Please take immediate action to resolve this issue.
        """,
        reference_doctype="Advertisement Broadcast",
        reference_name=ad_doc.name,
    )


def generate_daily_report():
    """Generate daily broadcasting report"""
    try:
        from frappe.utils import today, add_days

        # Get yesterday's date
        report_date = add_days(today(), -1)

        # Get all advertisements for yesterday
        ads = frappe.get_all(
            "Advertisement Broadcast",
            filters={"scheduled_date": report_date, "docstatus": 1},
            fields=[
                "name",
                "advertisement_title",
                "customer",
                "scheduled_date",
                "scheduled_time",
                "duration_seconds",
                "presenter",
                "status",
                "total_amount",
            ],
            order_by="scheduled_time",
        )

        if not ads:
            frappe.logger().info(f"No advertisements found for {report_date}")
            return

        # Calculate statistics
        total_ads = len(ads)
        aired_ads = len([ad for ad in ads if ad.status == "Aired"])
        missed_ads = len([ad for ad in ads if ad.status == "Missed"])
        scheduled_ads = len([ad for ad in ads if ad.status == "Scheduled"])
        total_revenue = sum([ad.total_amount or 0 for ad in ads if ad.status == "Aired"])

        # Create report content
        report_content = f"""
        Daily Broadcasting Report - {report_date}

        Summary:
        - Total Advertisements: {total_ads}
        - Successfully Aired: {aired_ads}
        - Missed: {missed_ads}
        - Still Scheduled: {scheduled_ads}
        - Total Revenue: {frappe.utils.fmt_money(total_revenue)}

        Detailed List:
        """

        for ad in ads:
            report_content += f"""
        {ad.scheduled_time} - {ad.advertisement_title} ({ad.customer})
        Status: {ad.status} | Presenter: {ad.presenter} | Amount: {frappe.utils.fmt_money(ad.total_amount or 0)}
        """

        # Send report to broadcasting managers
        managers = frappe.get_all(
            "User",
            filters={"role_profile_name": "Broadcasting Manager"},
            fields=["email"]
        )

        if managers:
            frappe.sendmail(
                recipients=[m.email for m in managers],
                subject=f"Daily Broadcasting Report - {report_date}",
                message=report_content,
            )

        frappe.logger().info(f"Daily report generated for {report_date}")

    except Exception as e:
        frappe.log_error(
            message=frappe.get_traceback(), title="Generate Daily Report Error"
        )
