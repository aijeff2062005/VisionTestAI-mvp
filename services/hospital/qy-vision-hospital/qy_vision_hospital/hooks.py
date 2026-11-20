app_name = "qy_vision_hospital"
app_title = "QY Vision Hospital"
app_publisher = "VisionTestAI"
app_description = "Giao diện và quy trình demo Quân y"
app_email = ""
app_license = "mit"

required_apps = ["smart_hospital"]

app_include_js = [
    "/assets/qy_vision_hospital/js/clinic_shell.js?v=qy-system-pages-3",
    "/assets/qy_vision_hospital/js/patient_list.js?v=patient-list-compact-1",
    "/assets/qy_vision_hospital/js/face_landmarker.js",
    "/assets/qy_vision_hospital/js/face_enroll.js",
    "/assets/qy_vision_hospital/vendor/jsqr-1.4.0/jsQR.js",
    "/assets/qy_vision_hospital/js/patient_cccd.js",
]

doctype_js = {"Patient": "public/js/patient_cccd.js"}
doctype_list_js = {"Patient": "public/js/patient_list.js"}
boot_session = "qy_vision_hospital.api.clinic_shell.boot_session"
after_migrate = [
    "qy_vision_hospital.api.clinic_roles.ensure_clinic_desk_roles",
    "qy_vision_hospital.api.xml_intake.ensure_xml_fields",
]

doc_events = {
	"Visual Acuity": {
		"after_insert": "qy_vision_hospital.api.xml_intake.mark_queue_completed",
	}
}
