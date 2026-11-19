# Copyright (c) 2026, a and contributors
# For license information, please see license.txt

# import frappe
import frappe
from frappe.model.document import Document
from frappe.utils import getdate


class VisualAcuity(Document):
    def autoname(self):
        measurement = frappe.get_doc(
            "Vision Measurement",
            self.vision_measurement
        )

        patient = frappe.get_doc(
            "Patient",
            measurement.patient
        )

        date_string = frappe.utils.nowdate()

        prefix = f"VA-{date_string}-{patient.patient_name}"

        existing = frappe.db.count(
            "Visual Acuity",
            {
                "name": ["like", f"{prefix}%"]
            }
        )

        self.name = f"{prefix}-{existing + 1:02d}"