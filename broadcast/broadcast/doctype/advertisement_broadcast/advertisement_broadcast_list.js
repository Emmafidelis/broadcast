frappe.listview_settings['Advertisement Broadcast'] = {
    add_fields: ["status", "scheduled_date", "scheduled_time", "customer", "presenter"],
    has_indicator_for_draft: true,
    get_indicator: function(doc) {
        const status_map = {
            "Scheduled": "orange",
            "Aired": "green",
            "Missed": "red",
            "Cancelled": "grey"
        };

        return [__(doc.status), status_map[doc.status], "status,=," + doc.status];
    }
};


