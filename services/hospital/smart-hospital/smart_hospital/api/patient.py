import frappe


@frappe.whitelist()
def get_patients():

    patients = frappe.get_all(

        "Patient",

        fields=[
            "name",
            "patient_name",
            "first_name",
            "middle_name",
            "last_name",
            "sex",
            "dob",
            "uid",
            "mobile",
            "phone",
            "email",
            "status",
            "blood_group",
            "allergies",
            "surgical_history",
            "medical_history",
            "custom_địa_chỉ_nhà"
        ],
        order_by="creation desc"

    )

    return patients


@frappe.whitelist()
def get_patient(patient_name):

    patient = frappe.get_doc(
        "Patient",
        patient_name
    )

    return patient.as_dict()

@frappe.whitelist()
def update_patient(
    patient_name,
    first_name=None,
    middle_name=None,
    last_name=None,
    sex=None,
    dob=None,
    uid=None,
    mobile=None,
    phone=None,
    email=None,
    cccd_address=None,
    blood_group=None,
    allergies=None,
    surgical_history=None,
    medical_history=None
):

    patient = frappe.get_doc(
        "Patient",
        patient_name
    )


    if first_name is not None:
        patient.first_name = first_name


    if middle_name is not None:
        patient.middle_name = middle_name


    if last_name is not None:
        patient.last_name = last_name


    if sex is not None:
        patient.sex = sex


    if dob is not None:
        patient.dob = dob


    if uid is not None:
        patient.uid = uid


    if mobile is not None:
        patient.mobile = mobile


    if phone is not None:
        patient.phone = phone


    if email is not None:
        patient.email = email


    if cccd_address is not None:

        if "custom_địa_chỉ_nhà" in \
            patient.meta.get_valid_columns():

            patient.set(
                "custom_địa_chỉ_nhà",
                cccd_address
            )
    if blood_group is not None:
        patient.blood_group = blood_group


    if allergies is not None:
        patient.allergies = allergies


    if surgical_history is not None:
        patient.surgical_history = surgical_history


    if medical_history is not None:
        patient.medical_history = medical_history

    patient.save(

        ignore_permissions=True

    )


    frappe.db.commit()


    return {

        "success":
            True,

        "patient":
            patient.name,

        "patient_name":
            patient.patient_name,

    }