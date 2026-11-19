(function () {
	const PAGE = "patient-registration";
	const PATIENT = "Patient";

	function set_patient_list_compact_mode() {
		const route = (frappe.get_route && frappe.get_route()) || [];
		const is_patient_list = route[0] === "List" && route[1] === PATIENT;
		document.body.classList.toggle("clinic-patient-list-compact", is_patient_list);
		if (document.getElementById("clinic-patient-list-compact-style")) {
			return;
		}
		const style = document.createElement("style");
		style.id = "clinic-patient-list-compact-style";
		style.textContent = `
			body.clinic-patient-list-compact .page-head .page-actions .btn:not(.btn-primary):not(.btn-danger) {
				display: none !important;
			}
			body.clinic-patient-list-compact .page-head .page-actions .btn-group:not(:has(.btn-primary, .btn-danger)),
			body.clinic-patient-list-compact .page-head .page-actions .dropdown:not(:has(.btn-primary, .btn-danger)) {
				display: none !important;
			}
			body.clinic-patient-list-compact .filter-section,
			body.clinic-patient-list-compact .list-filter-area,
			body.clinic-patient-list-compact .list-filters,
			body.clinic-patient-list-compact .filter-selector,
			body.clinic-patient-list-compact .standard-filter-section {
				display: none !important;
			}
		`;
		document.head.appendChild(style);
	}

	function is_new_patient_route(route) {
		if (!route || !route.length) {
			return false;
		}
		const head = String(route[0] || "");
		if (head.toLowerCase() === "patient") {
			return String(route[1] || "")
				.toLowerCase()
				.startsWith("new-");
		}
		if (head === "Form" && route[1] === PATIENT) {
			const name = String(route[2] || "").toLowerCase();
			return !name || name.startsWith("new-");
		}
		return false;
	}

	function show_registration_page() {
		if (frappe.views && frappe.views.pageview) {
			frappe.views.pageview.show(PAGE);
		}
	}

	function go_registration() {
		frappe.set_route(PAGE);
	}

	function go_new_patient() {
		go_registration();
	}

	function apply_listview_settings() {
		set_patient_list_compact_mode();
		frappe.listview_settings[PATIENT] = {
			primary_action: go_new_patient,
			onload(listview) {
				listview.page.set_primary_action(__("Add Patient"), go_new_patient, "add");
				const $btn = listview.page.add_inner_button(__("Xóa bệnh nhân"), function () {
					const selected = listview.get_checked_items(true);
					const names = (selected || []).map(function (row) {
						return row.name || row;
					});
					window.clinicWipePatients(names, function () {
						listview.refresh();
					});
				});
				$btn.addClass("btn-danger");
			},
		};
	}

	function patch_list_make_new_doc() {
		const ListView = frappe.views && frappe.views.ListView;
		if (!ListView || !ListView.prototype || ListView.prototype._patient_reg_patched) {
			return;
		}
		ListView.prototype._patient_reg_patched = true;
		const original = ListView.prototype.make_new_doc;
		ListView.prototype.make_new_doc = function () {
			if (this.doctype === PATIENT) {
				go_new_patient();
				return;
			}
			return original.apply(this, arguments);
		};
	}

	function patch_router() {
		const router = frappe.router;
		if (!router || router._patient_reg_render_patched) {
			return;
		}
		router._patient_reg_render_patched = true;

		const originalRender = router.render_page.bind(router);
		router.render_page = function () {
			const route = this.current_route || frappe.get_route() || [];
			if (is_new_patient_route(route)) {
				show_registration_page();
				return;
			}
			return originalRender();
		};
	}

	function patch_sidebar_registration_link() {
		$(document).off("click.clinic_reg_sidebar");
		$(document).on("click.clinic_reg_sidebar", ".body-sidebar a, .sidebar-item-container a, .shortcut-widget-box a", function (e) {
			const text = ($(this).text() || "").replace(/\s+/g, " ").trim();
			if (text !== "Đăng ký bệnh nhân") {
				return;
			}
			e.preventDefault();
			e.stopImmediatePropagation();
			go_registration();
			return false;
		});
	}

	function count_label(key) {
		const labels = {
			"Eye Prescription": "đơn kính",
			"Visual Acuity": "kết quả thị lực",
			"Vision Measurement": "lần đo",
			"Patient Appointment": "lịch hẹn",
			"Patient Encounter": "lượt khám",
			File: "tệp đính kèm",
			Customer: "khách hàng",
			Contact: "liên hệ",
			Address: "địa chỉ",
			User: "tài khoản User",
			Media: "ảnh trên media",
		};
		return labels[key] || key;
	}

	function warning_html(preview) {
		const rows = (preview.patients || [])
			.map(function (item) {
				if (item.missing) {
					return "<li><b>" + frappe.utils.escape_html(item.name) + "</b> — không tìm thấy</li>";
				}
				const bits = Object.keys(item.counts || {}).map(function (key) {
					return item.counts[key] + " " + count_label(key);
				});
				const extra = bits.length ? " (" + bits.join(", ") + ")" : "";
				const face = item.enroll_id ? ", Face ID #" + item.enroll_id : "";
				return (
					"<li><b>" +
					frappe.utils.escape_html(item.patient_name || item.name) +
					"</b> — " +
					frappe.utils.escape_html(item.name) +
					extra +
					face +
					"</li>"
				);
			})
			.join("");
		return (
			'<div class="text-danger" style="margin-bottom:12px;font-weight:600;">' +
			"Thao tác này xóa vĩnh viễn hồ sơ và toàn bộ dữ liệu liên quan. Không hoàn tác được." +
			"</div>" +
			"<p>Sẽ xóa:</p><ul>" +
			rows +
			"</ul>" +
			"<p>Bao gồm lịch hẹn, kết quả đo thị lực, đơn kính, ảnh khuôn mặt trên media, Face ID, Customer, Contact, Address và tài khoản User.</p>"
		);
	}

	window.clinicWipePatients = function (names, after) {
		const list = (names || []).filter(Boolean);
		if (!list.length) {
			frappe.msgprint({
				title: "Xóa bệnh nhân",
				indicator: "orange",
				message: "Hãy chọn ít nhất một bệnh nhân trên danh sách, rồi bấm «Xóa bệnh nhân».",
			});
			return;
		}
		frappe.call({
			method: "smart_hospital.api.patient_wipe.preview_patient_wipe",
			args: { patients: list },
			freeze: true,
			freeze_message: "Đang kiểm tra dữ liệu liên quan…",
			callback(r) {
				const preview = (r && r.message) || {};
				const dialog = new frappe.ui.Dialog({
					title: "Cảnh báo — xóa bệnh nhân",
					indicator: "red",
					fields: [{ fieldtype: "HTML", fieldname: "warn", options: warning_html(preview) }],
					primary_action_label: "Tiếp tục",
					primary_action() {
						dialog.hide();
						const who = list.length === 1
							? (preview.patients && preview.patients[0] && preview.patients[0].patient_name) || list[0]
							: list.length + " bệnh nhân";
						const confirmDlg = new frappe.ui.Dialog({
							title: "Xác nhận xóa",
							indicator: "red",
							fields: [
								{
									fieldtype: "HTML",
									options:
										"<p>Xác nhận xóa vĩnh viễn <b>" +
										frappe.utils.escape_html(String(who)) +
										"</b> và mọi dữ liệu liên quan?</p>",
								},
							],
							primary_action_label: "Xóa vĩnh viễn",
							primary_action() {
								confirmDlg.hide();
								frappe.call({
									method: "smart_hospital.api.patient_wipe.wipe_patient",
									args: { patients: list },
									freeze: true,
									freeze_message: "Đang xóa toàn bộ dữ liệu bệnh nhân…",
									callback(res) {
										const msg = (res && res.message) || {};
										const n = msg.count || 0;
										frappe.show_alert({
											message: "Đã xóa " + n + " bệnh nhân và dữ liệu liên quan.",
											indicator: "green",
										});
										if (typeof after === "function") {
											after(msg);
										}
									},
								});
							},
						});
						confirmDlg.show();
					},
				});
				dialog.show();
			},
		});
	};

	function init_patient_registration_routing() {
		set_patient_list_compact_mode();
		apply_listview_settings();
		patch_list_make_new_doc();
		patch_router();
		patch_sidebar_registration_link();
	}

	init_patient_registration_routing();
	$(document).on("app-ready", init_patient_registration_routing);
	if (frappe.router && frappe.router.on && !frappe.router._patientListCompactPatched) {
		frappe.router._patientListCompactPatched = true;
		frappe.router.on("change", set_patient_list_compact_mode);
	}
})();
