import frappe


@frappe.whitelist(allow_guest=True, methods=["POST"])
def receive_visual_acuity(
    vision_measurement=None,
    right_score=None,
    left_score=None,
    both_score=None,
):
    # Prefer JSON callback body from assistant_controller when present
    raw = frappe.request.get_json(silent=True) if frappe.request else None
    if isinstance(raw, dict) and raw.get("acuity"):
        from smart_hospital.api.vision import receive_results

        return receive_results()

    if vision_measurement is None:
        vision_measurement = frappe.form_dict.get("vision_measurement")
    if right_score is None:
        right_score = frappe.form_dict.get("right_score")
    if left_score is None:
        left_score = frappe.form_dict.get("left_score")
    if both_score is None:
        both_score = frappe.form_dict.get("both_score")

    if not vision_measurement:
        frappe.throw("Chưa xác định lần đo")

    if not right_score:
        frappe.throw("Chưa có điểm mắt phải")

    if not left_score:
        frappe.throw("Chưa có điểm mắt trái")

    if not both_score:
        frappe.throw("Chưa có điểm cả hai mắt")

    if not frappe.db.exists("Vision Measurement", vision_measurement):
        frappe.throw(f"Không tìm thấy Vision Measurement: {vision_measurement}")

    visual_acuity = frappe.get_doc(
        {
            "doctype": "Visual Acuity",
            "vision_measurement": vision_measurement,
            "right_score": right_score,
            "left_score": left_score,
            "both_score": both_score,
        }
    )

    visual_acuity.insert(ignore_permissions=True)
    frappe.db.commit()

    return {
        "success": True,
        "visual_acuity": visual_acuity.name,
        "vision_measurement": visual_acuity.vision_measurement,
        "right_score": visual_acuity.right_score,
        "left_score": visual_acuity.left_score,
        "both_score": visual_acuity.both_score,
    }
