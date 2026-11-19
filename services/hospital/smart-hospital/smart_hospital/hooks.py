app_name = "smart_hospital"
app_title = "Smart Hospital"
app_publisher = "a"
app_description = "A"
app_email = "minhchau01012005@gmail.com"
app_license = "mit"
required_apps = ["healthcare"]
# Apps
# ------------------
app_include_js = []
app_include_css = []
# The VisionCare Desk Page loads its conventional page/visioncare JS and CSS
# files through Frappe's Page.load_assets().

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "smart_hospital",
# 		"logo": "/assets/smart_hospital/logo.png",
# 		"title": "Smart Hospital",
# 		"route": "/smart_hospital",
# 		"has_permission": "smart_hospital.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/smart_hospital/css/smart_hospital.css"
# app_include_js = "/assets/smart_hospital/js/smart_hospital.js"

# include js, css files in header of web template
# web_include_css = "/assets/smart_hospital/css/smart_hospital.css"
# web_include_js = "/assets/smart_hospital/js/smart_hospital.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "smart_hospital/public/scss/website"

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
# app_include_icons = "smart_hospital/public/icons.svg"


after_migrate = [
    "smart_hospital.api.face_identity._ensure_custom_fields",
    "smart_hospital.api.face_identity.ensure_patient_genders",
    "smart_hospital.api.clinic_desk._ensure_appointment_desk_fields",
]

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# automatically load and sync documents of this doctype from downstream apps
# importable_doctypes = [doctype_1]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "smart_hospital.utils.jinja_methods",
# 	"filters": "smart_hospital.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "smart_hospital.install.before_install"
# after_install = "smart_hospital.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "smart_hospital.uninstall.before_uninstall"
# after_uninstall = "smart_hospital.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "smart_hospital.utils.before_app_install"
# after_app_install = "smart_hospital.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "smart_hospital.utils.before_app_uninstall"
# after_app_uninstall = "smart_hospital.utils.after_app_uninstall"

# Build
# ------------------
# To hook into the build process

# after_build = "smart_hospital.build.after_build"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "smart_hospital.notifications.get_notification_config"

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

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
	"Patient": {
		"on_trash": "smart_hospital.overrides.patient.on_patient_trash",
	},
}

# Extend DocType Class
# ------------------------------
#
# Specify custom mixins to extend the standard doctype controller.
# extend_doctype_class = {
# 	"Task": "smart_hospital.custom.task.CustomTaskMixin"
# }

override_doctype_class = {
	"Patient": "smart_hospital.overrides.patient.SmartPatient",
	"Sales Order": "smart_hospital.overrides.sales_oder.CustomSalesOrder",
}

override_whitelisted_methods = {
	"frappe.client.delete": "smart_hospital.overrides.patient.safe_client_delete",
}

# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "smart_hospital.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

ignore_links_on_delete = ["Contact", "Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["smart_hospital.utils.before_request"]
# after_request = ["smart_hospital.utils.after_request"]

# Job Events
# ----------
# before_job = ["smart_hospital.utils.before_job"]
# after_job = ["smart_hospital.utils.after_job"]

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
# 	"smart_hospital.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []
