# Copyright (c) 2025, Emanuel Fidelis and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
    if not filters:
        filters = {}

    columns = get_columns()
    data = get_data(filters)

    return columns, data


def get_columns():
    return [
        {
            "fieldname": "presenter",
            "label": _("Presenter"),
            "fieldtype": "Link",
            "options": "User",
            "width": 150,
        },
        {
            "fieldname": "total_scheduled",
            "label": _("Total Scheduled"),
            "fieldtype": "Int",
            "width": 120,
        },
        {
            "fieldname": "total_aired",
            "label": _("Total Aired"),
            "fieldtype": "Int",
            "width": 120,
        },
        {
            "fieldname": "total_missed",
            "label": _("Total Missed"),
            "fieldtype": "Int",
            "width": 120,
        },
        {
            "fieldname": "success_rate",
            "label": _("Success Rate %"),
            "fieldtype": "Percent",
            "width": 120,
        },
        {
            "fieldname": "revenue_generated",
            "label": _("Revenue Generated"),
            "fieldtype": "Currency",
            "width": 150,
        },
        {
            "fieldname": "revenue_lost",
            "label": _("Revenue Lost"),
            "fieldtype": "Currency",
            "width": 150,
        },
        {
            "fieldname": "avg_time_variance",
            "label": _("Avg Time Variance (min)"),
            "fieldtype": "Float",
            "width": 150,
        },
    ]


def get_data(filters):
    filters_list = [["docstatus", "=", 1]]

    if filters.get("from_date"):
        filters_list.append(["scheduled_date", ">=", filters.get("from_date")])

    if filters.get("to_date"):
        filters_list.append(["scheduled_date", "<=", filters.get("to_date")])

    if filters.get("presenter"):
        filters_list.append(["presenter", "=", filters.get("presenter")])

    ads = frappe.get_all(
        "Advertisement Broadcast",
        filters=filters_list,
        fields=["name", "presenter", "status", "total_amount"],
    )

    if not ads:
        return []

    stats = {}
    for ad in ads:
        presenter = ad.presenter
        if presenter not in stats:
            stats[presenter] = {
                "presenter": presenter,
                "total_scheduled": 0,
                "total_aired": 0,
                "total_missed": 0,
                "success_rate": 0,
                "revenue_generated": 0,
                "revenue_lost": 0,
                "avg_time_variance": 0,
                "_variance_sum": 0,
                "_variance_count": 0,
            }

        row = stats[presenter]
        row["total_scheduled"] += 1

        if ad.status == "Aired":
            row["total_aired"] += 1
            row["revenue_generated"] += flt(ad.total_amount or 0)
        elif ad.status == "Missed":
            row["total_missed"] += 1
            row["revenue_lost"] += flt(ad.total_amount or 0)

    parent_presenter = {ad.name: ad.presenter for ad in ads}
    logs = frappe.get_all(
        "Broadcast Log",
        filters={
            "parent": ("in", list(parent_presenter.keys())),
            "variance_seconds": ["is", "set"],
        },
        fields=["parent", "variance_seconds"],
    )

    for log in logs:
        presenter = parent_presenter.get(log.parent)
        if not presenter:
            continue
        row = stats[presenter]
        row["_variance_sum"] += flt(log.variance_seconds or 0)
        row["_variance_count"] += 1

    data = []
    for row in stats.values():
        if row["total_scheduled"]:
            row["success_rate"] = round(
                (row["total_aired"] * 100.0) / row["total_scheduled"], 2
            )
        if row["_variance_count"]:
            row["avg_time_variance"] = round(
                (row["_variance_sum"] / row["_variance_count"]) / 60, 2
            )
        row.pop("_variance_sum", None)
        row.pop("_variance_count", None)
        data.append(row)

    data.sort(key=lambda x: x["success_rate"], reverse=True)
    return data


