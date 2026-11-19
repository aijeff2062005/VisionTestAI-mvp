frappe.pages["nurse-station"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Hàng chờ đo"), single_column: true });
	const esc = (value) => frappe.utils.escape_html(String(value == null ? "" : value));
	let refreshTimer;

	$(page.body).html(`
		<style>
			.qy-queue{padding:20px;max-width:1280px;margin:auto;background:var(--fg-color);border:1px solid var(--border-color);border-radius:10px}
			.qy-queue-head{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:16px}
			.qy-queue-head h2{margin:0}.qy-queue-head p{margin:5px 0 0;color:var(--text-muted)}
			.qy-queue-table-wrap{overflow:auto}.qy-queue table{min-width:850px;margin:0}
			.qy-queue th:first-child,.qy-queue td:first-child{text-align:center;width:60px}
			.qy-queue .actions{display:flex;gap:6px}.qy-queue-empty{text-align:center;padding:34px;color:var(--text-muted)}
			.qy-status{display:inline-block;border-radius:999px;padding:3px 10px;font-size:12px;font-weight:600}
			.qy-status-waiting{background:#fff3cd;color:#805b00}.qy-status-running{background:#dbeafe;color:#1d4ed8}.qy-status-done{background:#dcfce7;color:#166534}
			.qy-waiting-label{display:inline-flex;align-items:center;gap:5px;padding:6px 9px;border:1px solid #e2e8f0;border-radius:7px;background:#f1f5f9;color:#64748b;font-size:12px;font-weight:600;white-space:nowrap}
			@media(max-width:640px){.qy-queue{padding:12px}.qy-queue-head{align-items:flex-start;flex-direction:column}}
		</style>
		<div class="qy-queue">
			<div class="qy-queue-head">
				<div><h2>${__("Hàng chờ đo")}</h2><p>${__("Bệnh nhân được tiếp nhận từ XML, sắp xếp theo thời điểm nhận.")}</p></div>
				<div><button class="btn btn-default" data-action="patients">${__("Danh sách bệnh nhân")}</button> <button class="btn btn-primary" data-action="add">${__("+ Thêm bệnh nhân đo")}</button> <button class="btn btn-default" data-action="refresh">${__("Làm mới")}</button></div>
			</div>
			<div class="qy-queue-table-wrap" id="qy-queue-list"><div class="qy-queue-empty">${__("Đang tải...")}</div></div>
		</div>`);

	async function load() {
		try {
			const response = await frappe.call({ method: "qy_vision_hospital.api.xml_intake.list_measurement_queue" });
			const rows = (response.message && response.message.requests) || [];
			if (!rows.length) {
				$(page.body).find("#qy-queue-list").html(`<div class="qy-queue-empty">${__("Chưa có bệnh nhân trong hàng chờ đo.")}</div>`);
				return;
			}
			const body = rows.map((item, index) => {
				const waiting = item.status === "Chờ đo";
				const running = item.status === "Đang đo";
				const badge = waiting ? "qy-status-waiting" : running ? "qy-status-running" : "qy-status-done";
				const received = item.received_at ? frappe.datetime.str_to_user(item.received_at) : "—";
				const action = waiting
					? `${item.can_start ? `<button class="btn btn-primary btn-xs" data-action="start" data-id="${esc(item.name)}">${__("Bắt đầu đo")}</button>` : `<span class="qy-waiting-label">◷ ${__("Chờ đến lượt")}</span>`} <button class="btn btn-danger btn-xs" data-action="remove" data-id="${esc(item.name)}">${__("Bỏ lượt")}</button>`
					: running
						? `<button class="btn btn-warning btn-xs" data-action="stop" data-id="${esc(item.name)}">${__("Dừng đo")}</button>`
						: (item.visual_acuity_result ? `<a class="btn btn-default btn-xs" href="#Form/Visual%20Acuity/${encodeURIComponent(item.visual_acuity_result)}">${__("Xem kết quả")}</a>` : `<span class="text-muted">${__("Hoàn tất")}</span>`);
				return `<tr><td>${index + 1}</td><td>${esc(received)}</td><td><a href="#Form/Patient/${encodeURIComponent(item.patient)}">${esc(item.patient_name || item.patient)}</a></td><td>${esc(item.his_patient_id)}</td><td>••••${esc(item.cccd_last4)}</td><td><span class="qy-status ${badge}">${esc(item.status)}</span></td><td>${action}</td></tr>`;
			}).join("");
			$(page.body).find("#qy-queue-list").html(`<table class="table table-bordered"><thead><tr><th>${__("STT")}</th><th>${__("Thời điểm nhận")}</th><th>${__("Bệnh nhân")}</th><th>${__("Mã HIS")}</th><th>${__("CCCD")}</th><th>${__("Trạng thái")}</th><th>${__("Thao tác")}</th></tr></thead><tbody>${body}</tbody></table>`);
		} catch (error) {
			$(page.body).find("#qy-queue-list").html(`<div class="qy-queue-empty text-danger">${esc(error.message || __("Không tải được hàng chờ đo."))}</div>`);
		}
	}

	$(page.body).on("click", "[data-action]", async function () {
		const action = this.dataset.action;
		if (action === "refresh") return load();
		if (action === "patients") return frappe.set_route("List", "Patient");
		if (action === "add") {
			const dialog = new frappe.ui.Dialog({
				title: __("Thêm bệnh nhân đo vào hàng chờ hôm nay"),
				fields: [{ fieldname: "patient", label: __("Bệnh nhân"), fieldtype: "Link", options: "Patient", reqd: 1 }],
				primary_action_label: __("Thêm vào hàng chờ"),
				primary_action: async (values) => {
					try {
						await frappe.call({ method: "qy_vision_hospital.api.xml_intake.add_patient_to_measurement_queue", args: values, freeze: true });
						dialog.hide(); await load();
					} catch (error) { frappe.msgprint(error.message || __("Không thêm được bệnh nhân.")); }
				},
			});
			dialog.show(); return;
		}
		const request = this.dataset.id;
		if (action === "remove") return frappe.confirm(__("Bỏ lượt chờ đo hôm nay? Hồ sơ bệnh nhân vẫn được giữ."), async () => {
			await act("qy_vision_hospital.api.xml_intake.cancel_queue_request", { request });
		});
		if (action === "stop") {
			return frappe.confirm(__("Dừng phiên đo hiện tại? Yêu cầu sẽ quay lại trạng thái Chờ đo."), async () => {
				await act("qy_vision_hospital.api.xml_intake.stop_queue_measurement", { request });
			});
		}
		if (action === "start") await act("qy_vision_hospital.api.xml_intake.start_queue_measurement", { request });
	});

	async function act(method, args) {
		try {
			const result = await frappe.call({ method, args, freeze: true });
			if (result.message && result.message.success) frappe.show_alert({ message: __("Đã gửi lệnh đo phiên {0}", [result.message.vision_measurement || ""]), indicator: "green" });
			await load();
		} catch (error) {
			frappe.msgprint(error.message || __("Không thực hiện được thao tác."));
			await load();
		}
	}

	$(document).off("smart-hospital-data-updated.qy-xml-queue");
	$(document).on("smart-hospital-data-updated.qy-xml-queue", function (_event, doc) {
		if (["Patient", "QY Measurement Request", "Visual Acuity"].includes(doc && (doc.doctype || doc.doc_type))) load();
	});
	refreshTimer = setInterval(load, 5000);
	$(wrapper).one("remove", function () {
		clearInterval(refreshTimer);
		$(document).off("smart-hospital-data-updated.qy-xml-queue");
	});
	load();
};
