# Copyright (c) 2025, Emanuel Fidelis and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt, getdate, add_days


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
    conditions = ["docstatus = 1"]
    values = {}
    
    if filters.get("from_date"):
        conditions.append("scheduled_date >= %(from_date)s")
        values["from_date"] = filters.get("from_date")
    
    if filters.get("to_date"):
        conditions.append("scheduled_date <= %(to_date)s")
        values["to_date"] = filters.get("to_date")
    
    if filters.get("presenter"):
        conditions.append("presenter = %(presenter)s")
        values["presenter"] = filters.get("presenter")

    where_clause = " AND ".join(conditions)
    
    data = frappe.db.sql(
        """
        SELECT 
            presenter,
            COUNT(*) as total_scheduled,
            SUM(CASE WHEN status = 'Aired' THEN 1 ELSE 0 END) as total_aired,
            SUM(CASE WHEN status = 'Missed' THEN 1 ELSE 0 END) as total_missed,
            ROUND(
                (SUM(CASE WHEN status = 'Aired' THEN 1 ELSE 0 END) * 100.0 / COUNT(*)), 
                2
            ) as success_rate,
            SUM(CASE WHEN status = 'Aired' THEN total_amount ELSE 0 END) as revenue_generated,
            SUM(CASE WHEN status = 'Missed' THEN total_amount ELSE 0 END) as revenue_lost
        FROM `tabAdvertisement Broadcast`
        WHERE %s
        GROUP BY presenter
        ORDER BY success_rate DESC
    """,
        where_clause,
        values,
        as_dict=True,
    )

    # Calculate average time variance for each presenter
    for row in data:
        variance_data = frappe.db.sql(
            """
            SELECT AVG(bl.variance_seconds) as avg_variance
            FROM `tabBroadcast Log` bl
            JOIN `tabAdvertisement Broadcast` ab ON bl.parent = ab.name
            WHERE ab.presenter = %s AND bl.variance_seconds IS NOT NULL
        """,
            row.presenter,
        )

        if variance_data and variance_data[0][0]:
            row["avg_time_variance"] = round(
                variance_data[0][0] / 60, 2
            )  # Convert to minutes
        else:
            row["avg_time_variance"] = 0

    return data



