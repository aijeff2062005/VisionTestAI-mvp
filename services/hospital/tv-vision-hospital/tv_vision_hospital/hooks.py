app_name = "tv_vision_hospital"
app_title = "TV Vision Hospital"
app_publisher = "VisionTestAI"
app_description = "Giao diện và quy trình VisionCare của Bệnh viện Trưng Vương"
app_email = ""
app_license = "mit"

required_apps = ["smart_hospital"]


app_include_js = ["/assets/tv_vision_hospital/js/visioncare_redirect.js?v=20261015-25"]
app_include_css = ["/assets/tv_vision_hospital/css/visioncare_boot.css?v=20261015-25"]

after_migrate = ["tv_vision_hospital.api.clinic_roles.execute"]

doc_events = {
    "Patient Appointment": {
        "before_insert": "tv_vision_hospital.api.clinic_desk.require_bookable_face",
    },
}
