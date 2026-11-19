frappe.pages["clinic-patients"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Danh sách bệnh nhân"), single_column: true });
	const state = { search: "", status: "", start: 0, pageLength: 100, timer: null, request: 0 };
	const esc = (value) => frappe.utils.escape_html(String(value || ""));
	const render = (data) => {
		const searchInput = page.body.find("#patient-search");
		const restoreSearchFocus = searchInput.is(":focus");
		const searchCursor = searchInput.length ? searchInput[0].selectionStart : null;
		const rows = data.rows || [];
		const body = rows.length
			? rows.map((patient, index) => `<tr>
				<td>${state.start + index + 1}</td>
				<td><a href="#Form/Patient/${encodeURIComponent(patient.name)}">${esc(patient.custom_his_patient_id || patient.name)}</a></td>
				<td>${esc(patient.patient_name)}</td>
				<td>${patient.custom_cccd_last4 ? `••••${esc(patient.custom_cccd_last4)}` : esc(patient.uid)}</td>
				<td>${esc(patient.mobile)}</td>
				<td>${esc(patient.email)}</td>
			</tr>`).join("")
			: `<tr><td colspan="6" class="text-muted text-center">${__("Không tìm thấy bệnh nhân")}</td></tr>`;
		$(page.body).html(`
			<style>
				.clinic-patients-page{padding:20px;background:var(--fg-color);border:1px solid var(--border-color);border-radius:10px}
				.clinic-patients-heading,.clinic-patients-toolbar,.clinic-patients-footer{display:flex;align-items:center;justify-content:space-between;gap:12px}
				.clinic-patients-heading{margin-bottom:18px}.clinic-patients-heading h2{margin:0 0 5px}.clinic-patients-heading p{margin:0;color:var(--text-muted)}
				.clinic-patients-toolbar{margin-bottom:14px}.clinic-patients-toolbar input{max-width:560px}.clinic-patients-toolbar select{max-width:220px}
				.clinic-patients-table-wrap{overflow:auto}.clinic-patients-page table{min-width:760px;margin:0}.clinic-patients-page th:first-child,.clinic-patients-page td:first-child{text-align:center;width:64px}
				.clinic-patients-footer{margin-top:14px;color:var(--text-muted)}.clinic-patients-footer>div{display:flex;gap:8px}
				@media(max-width:640px){.clinic-patients-page{padding:14px}.clinic-patients-heading{align-items:flex-start}.clinic-patients-toolbar{align-items:stretch;flex-direction:column}.clinic-patients-toolbar input,.clinic-patients-toolbar select{max-width:none}}
			</style>
			<div class="clinic-patients-page">
				<div class="clinic-patients-heading">
					<div><h2>${__("Danh sách bệnh nhân")}</h2><p>${__("Tìm theo tên, mã HIS, CCCD, số điện thoại hoặc email")}</p></div>
					<button class="btn btn-primary" data-action="new">${__("Thêm bệnh nhân")}</button>
				</div>
				<div class="clinic-patients-toolbar">
					<input class="form-control" id="patient-search" type="search" value="${esc(state.search)}" placeholder="${__("Tìm bệnh nhân...")}">
					<select class="form-control" id="patient-status" aria-label="${__("Lọc theo trạng thái")}">
						<option value="">${__("Tất cả trạng thái")}</option>
						<option value="Active" ${state.status === "Active" ? "selected" : ""}>${__("Đang hoạt động")}</option>
						<option value="Disabled" ${state.status === "Disabled" ? "selected" : ""}>${__("Đã ngừng hoạt động")}</option>
					</select>
				</div>
				<div class="clinic-patients-table-wrap"><table class="table table-bordered">
					<thead><tr><th>${__("STT")}</th><th>${__("Mã bệnh nhân")}</th><th>${__("Họ tên")}</th><th>${__("CCCD / 4 số cuối")}</th><th>${__("Số điện thoại")}</th><th>Email</th></tr></thead>
					<tbody>${body}</tbody>
				</table></div>
				<div class="clinic-patients-footer">
					<span>${rows.length ? `${state.start + 1}–${state.start + rows.length}` : "0"}</span>
					<div><button class="btn btn-default" data-action="previous" ${state.start === 0 ? "disabled" : ""}>${__("Trước")}</button>
					<button class="btn btn-default" data-action="next" ${data.has_more ? "" : "disabled"}>${__("Tiếp")}</button></div>
				</div>
			</div>`);
		if (restoreSearchFocus) {
			const nextSearch = page.body.find("#patient-search")[0];
			nextSearch.focus();
			if (searchCursor !== null) nextSearch.setSelectionRange(searchCursor, searchCursor);
		}
	};
	const load = async () => {
		const request = ++state.request;
		try {
			const result = await frappe.call({
				method: "qy_vision_hospital.api.patient_list.list_patients",
				args: { search: state.search, status: state.status, start: state.start, page_length: state.pageLength },
			});
			if (request === state.request) render(result.message || { rows: [], has_more: false });
		} catch (error) {
			if (request === state.request) frappe.msgprint(error.message || __("Không tải được danh sách bệnh nhân."));
		}
	};
	$(page.body).on("input", "#patient-search", function () {
		state.search = this.value;
		state.start = 0;
		clearTimeout(state.timer);
		state.timer = setTimeout(load, 250);
	});
	$(page.body).on("change", "#patient-status", function () {
		state.status = this.value;
		state.start = 0;
		load();
	});
	$(page.body).on("click", "[data-action]", function () {
		switch (this.dataset.action) {
			case "new": frappe.set_route("patient-registration"); break;
			case "previous": state.start = Math.max(0, state.start - state.pageLength); load(); break;
			case "next": state.start += state.pageLength; load(); break;
		}
	});
	load();
};
