# Copyright (c) 2026, a and contributors
# For license information, please see license.txt

# import frappe
import frappe
from frappe.model.document import Document
from frappe.utils import getdate


class EyePrescription(Document):

    def autoname(self):
        patient_name = frappe.db.get_value(
            "Patient",
            self.patient,
            "patient_name"
        )

        date = getdate()

        self.name = f"PRES-{patient_name}-{date.strftime('%d%m%Y')}"