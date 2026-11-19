function stripDiacritics(value) {
    return String(value || "")
        .normalize("NFD")
        .replace(/[\u0300-\u036f]/g, "");
}


function mapCCCDGender(raw) {
    const normalized = stripDiacritics(
        String(raw || "").trim().toLowerCase()
    );

    if (!normalized) {
        return "";
    }

    if (
        normalized === "nam" ||
        normalized === "male" ||
        normalized === "m" ||
        normalized === "1" ||
        normalized.startsWith("nam")
    ) {
        return "Male";
    }

    if (
        normalized === "nu" ||
        normalized === "nữ" ||
        normalized === "female" ||
        normalized === "f" ||
        normalized === "2" ||
        normalized === "0"
    ) {
        return "Female";
    }

    return "";
}


function getField(id) {
    return document.getElementById(id);
}


function setField(id, value) {
    const field = getField(id);
    if (field) {
        field.value = value || "";
    }
}


function fillPatientFromCCCD(data) {
    setField("uid", data.nationalId);

    const fullName = (data.fullName || "").trim();
    const nameParts = fullName.split(/\s+/);

    if (nameParts.length >= 1) {
        setField("first-name", nameParts[0]);
    }
    if (nameParts.length >= 2) {
        setField("last-name", nameParts[nameParts.length - 1]);
    }
    if (nameParts.length > 2) {
        setField("middle-name", nameParts.slice(1, -1).join(" "));
    }

    if (data.birthDate) {
        const parts = data.birthDate.split("/");
        if (parts.length === 3) {
            const day = parts[0].padStart(2, "0");
            const month = parts[1].padStart(2, "0");
            const year = parts[2];
            setField("dob", `${year}-${month}-${day}`);
        }
    }

    const sexValue = mapCCCDGender(data.gender || data.sex);
    if (sexValue) {
        setField("sex", sexValue);
    }

    setField("cccd-address", data.address);
}


function loadCCCDResult() {
    const rawData = sessionStorage.getItem("cccd_scan_result");
    if (!rawData) {
        return;
    }

    try {
        fillPatientFromCCCD(JSON.parse(rawData));
        sessionStorage.removeItem("cccd_scan_result");
    } catch (error) {
        console.error("Không thể đọc dữ liệu CCCD:", error);
    }
}


window.addEventListener("load", loadCCCDResult);

function hideHealthcarePatientButtons(frm) {
    const labels = [
        __("Patient History"),
        __("Patient Progress"),
        __("Get Prescribed Clinical Procedures"),
    ];
    for (const label of labels) {
        frm.remove_custom_button(label);
        frm.remove_custom_button(label, __("View"));
        frm.remove_custom_button(label, __("Healthcare"));
    }
}

frappe.ui.form.on("Patient", {
    refresh(frm) {
        frm.toggle_display("phone", false);
        hideHealthcarePatientButtons(frm);
        if (frm.is_new()) {
            return;
        }
        frm.add_custom_button(__("Xóa bệnh nhân"), function () {
            if (typeof window.clinicWipePatients === "function") {
                window.clinicWipePatients([frm.doc.name], function () {
                    frappe.set_route("List", "Patient");
                });
                return;
            }
            frappe.msgprint("Không tải được thao tác xóa. Hãy tải lại trang.");
        }).addClass("btn-danger");
    },
});
