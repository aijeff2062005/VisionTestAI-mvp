frappe.pages["patient-vision-booking"].on_page_show = function (wrapper) {
	if (wrapper && typeof wrapper._reset_pvb_form === "function") {
		wrapper._reset_pvb_form();
		if (frappe._clinic_booking_patient && typeof wrapper._set_pvb_patient === "function") {
			wrapper._set_pvb_patient(frappe._clinic_booking_patient);
			delete frappe._clinic_booking_patient;
		}
	}
};

frappe.pages["patient-vision-booking"].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Đặt lịch thị lực"),
		single_column: true,
	});

	$(wrapper).find(".layout-main-section").html(`
		<style>@media(max-width:640px){#pvb-book{width:100%;min-height:44px}#pvb-patient input{font-size:16px}}</style>
		<div style="padding:clamp(12px,3vw,20px);max-width:640px;margin:auto;font-family:system-ui,sans-serif">
			<div class="frappe-control" style="margin:12px 0">
				<div id="pvb-patient"></div>
				<button type="button" class="btn btn-default btn-sm" id="pvb-new-patient" style="margin-top:8px">${__("+ Đăng ký bệnh nhân")}</button>
			</div>
			<div style="margin:12px 0">
					<label>${__("Ngày hẹn")}</label>
				<input type="date" id="pvb-date" class="form-control" />
			</div>
			<div style="margin:12px 0">
					<label>${__("Giờ hẹn (HH:MM)")}</label>
				<input type="time" id="pvb-time" class="form-control" step="60" />
			</div>
			<div style="margin:12px 0">
					<label>${__("Ghi chú")}</label>
				<input type="text" id="pvb-notes" class="form-control" value="${__("Vision examination")}" />
			</div>
			<button class="btn btn-primary" id="pvb-book">${__("Đặt lịch")}</button>
			<p id="pvb-result" style="margin-top:16px"></p>
		</div>
	`);

	var patient_control = frappe.ui.form.make_control({
		df: {
			fieldtype: "Link",
			options: "Patient",
			fieldname: "patient",
			label: __("Bệnh nhân"),
			reqd: 1,
		},
		parent: $("#pvb-patient"),
		render_input: true,
	});
	patient_control.refresh();
	wrapper._set_pvb_patient = function (patient) { patient_control.set_value(patient); };

	function nowTimeStr() {
		var t = "";
		if (frappe.datetime.now_time) {
			t = String(frappe.datetime.now_time() || "");
		}
		if (!t && frappe.datetime.now_datetime) {
			t = String(frappe.datetime.now_datetime() || "").split(" ")[1] || "";
		}
		var m = t.match(/^(\d{1,2}):(\d{2})/);
		if (m) {
			return String(m[1]).padStart(2, "0") + ":" + m[2];
		}
		return "";
	}

	function nowDateStr() {
		return frappe.datetime.get_today();
	}

	var today = nowDateStr();
	$("#pvb-date").val(today);
	$("#pvb-date").attr("min", today);
	var nowHm = nowTimeStr();
	$("#pvb-time").attr("placeholder", nowHm);
	if (nowHm) {
		$("#pvb-time").val(nowHm);
	}

	function resetBookingForm() {
		patient_control.set_value("");
		var freshDate = nowDateStr();
		var freshTime = nowTimeStr();
		$("#pvb-date").attr("min", freshDate).val(freshDate);
		$("#pvb-time").attr("placeholder", freshTime).val(freshTime);
		$("#pvb-notes").val(__("Vision examination"));
		$("#pvb-result").empty();
	}

	// Frappe reuses Page DOM when navigating away and back. Keep the booking
	// screen fresh instead of showing the previous patient/result.
	wrapper._reset_pvb_form = resetBookingForm;
	document.addEventListener("visibilitychange", function () {
		if (document.visibilityState === "visible" && frappe.get_route()[0] === "patient-vision-booking") {
			resetBookingForm();
		}
	});

	function parseBookTime(raw) {
		var s = String(raw || "").trim();
		var m = s.match(/^(\d{1,2}):(\d{2})(?::(\d{2}))?$/);
		if (!m) {
			return null;
		}
		var hh = parseInt(m[1], 10);
		var mm = parseInt(m[2], 10);
		if (hh > 23 || mm > 59) {
			return null;
		}
		return hh * 60 + mm;
	}

	function warnInvalid(msg) {
		frappe.msgprint({
			title: __("Not valid"),
			message: msg,
			indicator: "orange",
		});
		$("#pvb-result").html(
			"<span class='text-danger'>" + frappe.utils.escape_html(msg) + "</span>"
		);
	}

	$("#pvb-new-patient").on("click", function (e) {
		e.preventDefault();
		frappe.set_route("patient-registration");
	});

	$("#pvb-book").on("click", function () {
		var patient = patient_control.get_value();
		if (!patient) {
			frappe.msgprint(__("Select a patient"));
			return;
		}
		var bookDate = $("#pvb-date").val();
		var bookTime = String($("#pvb-time").val() || "").trim() || nowTimeStr();
		var todayStr = nowDateStr();
		if (!bookDate) {
			warnInvalid(__("Date is not valid"));
			return;
		}
		if (bookDate < todayStr) {
			warnInvalid(__("Date is not valid — cannot book a date in the past"));
			return;
		}
		var timeMins = parseBookTime(bookTime);
		if (timeMins == null) {
			warnInvalid(__("Time is not valid — use HH:MM"));
			return;
		}
		if (bookDate === todayStr) {
			var nowMins = parseBookTime(nowTimeStr());
			if (nowMins != null && timeMins < nowMins) {
				warnInvalid(__("Time is not valid — cannot book a time earlier than now"));
				return;
			}
		}
		frappe.call({
			method: "qy_vision_hospital.api.clinic_desk.book_vision_appointment",
			args: {
				patient: patient,
				appointment_date: $("#pvb-date").val(),
				appointment_time: bookTime,
				notes: $("#pvb-notes").val(),
			},
			freeze: true,
			callback: function (r) {
				if (r.message && r.message.success) {
					$("#pvb-result").html(
						"<span class='text-success'>" + __("Appointment booked:") + " " +
							frappe.utils.escape_html(r.message.appointment) +
							"</span>"
					);
					frappe.show_alert({ message: __("Appointment created"), indicator: "green" });
					frappe.set_route("nurse-station");
				} else {
					$("#pvb-result").html("<span class='text-danger'>" + __("Booking failed") + "</span>");
				}
			},
		});
	});
};
