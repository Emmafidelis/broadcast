app_name = "broadcast"
app_title = "Broadcast"
app_publisher = "Emanuel Fidelis"
app_description = "Broadcasting System"
app_email = "emanuelkagombora28@gmail.com"
app_license = "mit"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "broadcast",
# 		"logo": "/assets/broadcast/logo.png",
# 		"title": "Broadcast",
# 		"route": "/broadcast",
# 		"has_permission": "broadcast.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/broadcast/css/broadcast.css"
# app_include_js = "/assets/broadcast/js/broadcast.js"

# include js, css files in header of web template
# web_include_css = "/assets/broadcast/css/broadcast.css"
# web_include_js = "/assets/broadcast/js/broadcast.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "broadcast/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "broadcast/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "broadcast.utils.jinja_methods",
# 	"filters": "broadcast.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "broadcast.install.before_install"
# after_install = "broadcast.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "broadcast.uninstall.before_uninstall"
# after_uninstall = "broadcast.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "broadcast.utils.before_app_install"
# after_app_install = "broadcast.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "broadcast.utils.before_app_uninstall"
# after_app_uninstall = "broadcast.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "broadcast.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
    "Advertisement Broadcast": {
        "on_submit": "broadcast.broadcast.api.notify_detection_system",
        "on_cancel": "broadcast.broadcast.api.cancel_detection_monitoring",
        "after_insert": "broadcast.broadcast.api.send_scheduling_notification",
    },
    "Sales Invoice": {
        "on_update": "broadcast.broadcast.api.sync_ad_payment_status_from_invoice",
        "on_cancel": "broadcast.broadcast.api.sync_ad_payment_status_from_invoice",
    },
}

# Scheduled Tasks
# ---------------

scheduler_events = {
    "hourly": ["broadcast.broadcast.tasks.mark_missed_advertisements"],
    "daily": ["broadcast.broadcast.tasks.generate_daily_report"],
    "cron": {
        "*/5 * * * *": ["broadcast.broadcast.tasks.check_autoplay_queue"],
        "0 */2 * * *": ["broadcast.broadcast.api.sync_detection_system"],
    },
}

# Testing
# -------

# before_tests = "broadcast.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "broadcast.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "broadcast.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["broadcast.utils.before_request"]
# after_request = ["broadcast.utils.after_request"]

# Job Events
# ----------
# before_job = ["broadcast.utils.before_job"]
# after_job = ["broadcast.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"broadcast.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }
