frappe.pages["doctor-review"].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Duyệt kết quả"),
		single_column: true,
	});

	$(wrapper).find(".layout-main-section").html(`
		<style>
			.dr-wrap { padding: 16px; max-width: 1000px; margin: auto; font-family: system-ui, sans-serif; }
			.dr-table-wrap { width: 100%; overflow-x: auto; -webkit-overflow-scrolling: touch; }
			.dr-actions { display: flex; flex-wrap: wrap; gap: 8px; }
			.dr-actions .btn { min-height: 40px; }
			@media (max-width: 640px) { .dr-wrap { padding: 12px; } .dr-actions .btn { width: 100%; } #dr-form .btn { min-height: 44px; margin-bottom: 8px; } }
		</style>
		<div class="dr-wrap">
			<button class="btn btn-primary btn-sm" id="dr-refresh">${__("Refresh")}</button>
			<div id="dr-list" style="margin-top:16px">${__("Loading…")}</div>
			<div id="dr-form" style="display:none;margin-top:24px;padding:16px;border:1px solid var(--border-color);border-radius:8px;background:var(--fg-color)">
				<h3>${__("Prescription")}</h3>
				<p id="dr-meta"></p>
				<textarea id="dr-conclusion" rows="5" class="form-control" placeholder="${__("Conclusion / prescription…")}"></textarea>
				<div style="margin-top:12px">
					<button class="btn btn-primary btn-sm" id="dr-save">${__("Duyệt và lưu kết luận")}</button>
					<button class="btn btn-default btn-sm" id="dr-open-va">${__("Open Visual Acuity")}</button>
				</div>
			</div>
		</div>
	`);

	var current = null;

	function esc(s) {
		return frappe.utils.escape_html(String(s == null ? "" : s));
	}

	function load() {
		$("#dr-list").html("<p class='text-muted'>" + __("Loading…") + "</p>");
		frappe.call({
			method: "qy_vision_hospital.api.clinic_desk.list_pending_reviews",
			callback: function (r) {
				var items = (r.message && r.message.items) || [];
				if (!items.length) {
					$("#dr-list").html("<p class='text-muted'>" + __("No visual acuity results yet.") + "</p>");
					return;
				}
				var html = "<div class='dr-table-wrap'><table class='table table-bordered'><thead><tr>" +
					"<th>" + __("Patient") + "</th><th>R</th><th>L</th><th>" + __("Both") + "</th><th>" + __("Status") + "</th><th></th></tr></thead><tbody>";
				items.forEach(function (it) {
					html += "<tr><td>" + esc(it.patient_name || it.patient || "") + "</td>" +
						"<td>" + esc(it.right_score) + "</td>" +
						"<td>" + esc(it.left_score) + "</td>" +
						"<td>" + esc(it.both_score) + "</td>" +
						"<td>" + (it.reviewed ? __("Reviewed") : __("Pending")) + "</td>" +
						"<td><div class='dr-actions'><button class='btn btn-xs btn-default dr-open-result' " +
						"data-va='" + esc(it.name) + "'>" + __("View result") + "</button> " +
						"<button class='btn btn-xs btn-primary dr-pick' " +
						"data-va='" + esc(it.name) + "' " +
						"data-vm='" + esc(it.vision_measurement) + "' " +
						"data-patient='" + esc(it.patient) + "' " +
						"data-name='" + esc(it.patient_name || "") + "'>" +
						__("Review") + "</button></div></td></tr>";
				});
				html += "</tbody></table></div>";
				$("#dr-list").html(html);
			},
			error: function (error) {
				console.error("DOCTOR REVIEW LOAD ERROR", error);
				$("#dr-list").html("<p class='text-danger'>" + __("Unable to load review results.") + "</p>");
			},
		});
	}

	$(wrapper).on("click", "#dr-refresh", load);
	$(document).off("smart-hospital-data-updated.doctor-review");
	$(document).on("smart-hospital-data-updated.doctor-review", function (_event, doc) {
		var doctype = doc && (doc.doctype || doc.doc_type);
		if (["Visual Acuity", "Eye Prescription", "Vision Measurement"].includes(doctype)) {
			load();
		}
	});
	var refreshTimer = setInterval(load, 15000);
	$(wrapper).one("remove", function () {
		clearInterval(refreshTimer);
		$(document).off("smart-hospital-data-updated.doctor-review");
	});
	$(wrapper).on("click", ".dr-pick", function () {
		current = {
			va: $(this).data("va"),
			vm: $(this).data("vm"),
			patient: $(this).data("patient"),
			name: $(this).data("name"),
		};
		$("#dr-meta").text(
			(current.name || current.patient || "") +
				" — VA " +
				(current.va || "") +
				" / VM " +
				(current.vm || "")
		);
		$("#dr-conclusion").val("");
		$("#dr-form").show().get(0).scrollIntoView({ behavior: "smooth", block: "start" });
	});
	$(wrapper).on("click", ".dr-open-result", function () {
		const visualAcuity = $(this).data("va");
		if (visualAcuity) {
			frappe.set_route("Form", "Visual Acuity", visualAcuity);
		}
	});
	$(wrapper).on("click", "#dr-open-va", function () {
		if (current && current.va) {
			frappe.set_route("Form", "Visual Acuity", current.va);
		}
	});
	$(wrapper).on("click", "#dr-save", function () {
		if (!current || !current.patient || !current.vm) {
			frappe.msgprint(__("Select a result first"));
			return;
		}
		var conclusion = String($("#dr-conclusion").val() || "").trim();
		if (!conclusion) {
			frappe.msgprint(__("Vui lòng nhập kết luận trước khi duyệt."));
			return;
		}
		frappe.call({
			method: "qy_vision_hospital.api.clinic_desk.save_eye_prescription",
			args: {
				patient: current.patient,
				vision_measurement: current.vm,
				conclusion: conclusion,
			},
			freeze: true,
			callback: function (r) {
				if (r.message && r.message.success) {
					frappe.show_alert({ message: __("Saved {0}", [r.message.eye_prescription]), indicator: "green" });
					load();
				}
			},
		});
	});

	load();
};
