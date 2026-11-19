frappe.pages.visioncare = frappe.pages.visioncare || {};

frappe.pages.visioncare.on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: "VisionCare Hospital", single_column: true });
	const root = $(page.body);
	const esc = (value) => frappe.utils.escape_html(String(value == null ? "" : value));
	const labels = {
		dashboard: "Tổng quan",
		patients: "Danh sách bệnh nhân",
		patient_detail: "Hồ sơ bệnh nhân",
		queue: "Hàng chờ đo",
		history: "Lịch sử đo",
		approvals: "Duyệt kết quả",
		results: "Chi tiết kết quả",
		registration: "Đăng ký bệnh nhân",
		settings: "Cài đặt phòng khám",
		users: "Quản lý người dùng",
	};
	const pageRoutes = { dashboard: null, patients: "patients", patient_detail: "patient-detail", queue: "queue", history: "history", approvals: "approvals", results: "results", registration: "registration", settings: "settings", users: "users" };
	const routeView = Object.fromEntries(Object.entries(pageRoutes).filter(([, segment]) => segment).map(([view, segment]) => [segment, view]));
	const currentRoute = frappe.get_route();
	const initialView = routeView[currentRoute[1]] || "dashboard";
	const state = { view: initialView, patients: [], queue: [], history: [], reviews: [], users: [], selectedPatient: initialView === "patient_detail" ? (currentRoute[2] || "") : "", selectedResult: initialView === "results" ? (currentRoute[2] || "") : "", resultDetail: null, patientProfile: null, canDeletePatients: false, isDoctor: false, isAdmin: false, branding: { clinic_name: "VisionCare Hospital", logo_url: "", primary_color: "#0B8F87" }, brandingLoaded: false };

	root.html(`
		<div id="app" class="app">
			<aside id="sidebar" class="sidebar">
				<div class="brand"><div class="logo" id="brand-logo">◉</div><div class="brandtxt"><h1 id="brand-name">VisionCare Hospital</h1><p>Quân y</p></div></div>
				<div class="navtitle">Điều hành</div>
				<nav class="nav">
					<button data-page="dashboard">⌂ <span>Tổng quan</span></button>
					<button data-page="patients">♙ <span>Danh sách bệnh nhân</span></button>
					<button data-page="queue">▦ <span>Hàng chờ đo</span></button>
					<button class="doctor-nav" data-page="history">◷ <span>Lịch sử đo</span></button>
					<button class="doctor-nav" data-page="approvals">✓ <span>Duyệt kết quả</span></button>
				</nav>
				<div class="navtitle">Hệ thống</div>
				<nav class="nav">
					<button class="admin-nav" data-page="settings">⚙ <span>Cài đặt phòng khám</span></button>
					<button class="admin-nav" data-page="users">♧ <span>Quản lý người dùng</span></button>
				</nav>
				<div class="spacer"></div>
				<div class="help"><b>Hỗ trợ nhanh</b><p>Hỗ trợ hàng chờ XML HIS và kết nối trạm đo Quân y.</p><button class="btn btn-soft btn-sm" data-act="support" style="width:100%">Trung tâm hỗ trợ</button></div>
				<div class="profile"><div class="avatar" id="avatar">QY</div><div class="meta"><b id="username">Đang tải…</b><span id="role">Nhân viên phòng khám</span></div></div>
				<button id="logout" class="btn btn-secondary" style="margin-top:12px;width:100%">Đăng xuất</button>
			</aside>
			<main class="main">
				<header class="top"><div class="breadcrumb"><button class="iconbtn mobile-toggle" id="menu">☰</button><span id="breadcrumb-brand">VisionCare</span><span>/</span><strong id="crumb">Tổng quan</strong></div><div class="top-actions"><button class="iconbtn" type="button" aria-label="Tìm kiếm">⌕</button><button class="iconbtn" type="button" aria-label="Thông báo">♧</button><div class="avatar top-avatar" id="top-avatar">QY</div><span id="date"></span></div></header>
				<div id="toast" class="toast" hidden></div>
				<section id="view" class="content"></section>
			</main>
			<div id="modal"></div>
		</div>`);
	document.body.classList.add("visioncare-fullscreen");

	const api = async (method, args = {}) => {
		const response = await frappe.call({ method, args });
		return response.message;
	};
	const applyBranding = (branding = state.branding) => {
		const name = branding.clinic_name || "VisionCare Hospital";
		const color = /^#[0-9A-Fa-f]{6}$/.test(branding.primary_color || "") ? branding.primary_color : "#0B8F87";
		root.find("#brand-name, #breadcrumb-brand").text(name);
		root.find("#brand-logo").html(branding.logo_url ? `<img src="${esc(branding.logo_url)}" alt="${esc(name)}">` : "◉");
		root.find("#app").css({ "--primary": color, "--primary-dark": `color-mix(in srgb, ${color} 78%, #123B45)`, "--primary-soft": `color-mix(in srgb, ${color} 10%, white)`, "--brand-shadow": `color-mix(in srgb, ${color} 24%, transparent)` });
	};
	const notify = (message) => {
		const toast = root.find("#toast");
		toast.text(message).prop("hidden", false);
		setTimeout(() => toast.prop("hidden", true), 2800);
	};
	let queuePickerSearchTimer;
	let queuePickerSelected = "";
	async function loadQueuePickerPatients(search = "") {
		const list = root.find("#queue-picker-results");
		if (!list.length) return;
		list.html('<div class="queue-picker-empty">Đang tìm bệnh nhân…</div>');
		try {
			const response = await api("qy_vision_hospital.api.patient_list.list_patients", { search, page_length: 100 });
			const rows = response?.rows || [];
			list.html(rows.length ? rows.map((patient) => {
				const selected = patient.name === queuePickerSelected;
				const identity = patient.custom_his_patient_id || patient.name;
				return `<button type="button" class="queue-picker-row${selected ? " selected" : ""}" data-act="queue-picker-select" data-id="${esc(patient.name)}"><span><strong>${esc(patient.patient_name || patient.name)}</strong><small>${esc(identity)}${patient.custom_cccd_last4 ? ` · ••••${esc(patient.custom_cccd_last4)}` : ""}</small></span><span class="queue-picker-check">${selected ? "✓ Đã chọn" : "Chọn"}</span></button>`;
			}).join("") : '<div class="queue-picker-empty">Không tìm thấy bệnh nhân phù hợp.</div>');
		} catch (error) {
			list.html(`<div class="queue-picker-empty text-danger">${esc(error.message || "Không tải được danh sách bệnh nhân.")}</div>`);
		}
	}
	function showQueuePatientPicker() {
		queuePickerSelected = "";
		root.find("#modal").html(`<div class="dialog queue-picker"><div class="drawer-head"><div><h3>Thêm bệnh nhân đo</h3><p>Chọn hồ sơ có sẵn để thêm lượt chờ hôm nay.</p></div><button class="btn btn-secondary btn-sm" type="button" data-act="close-modal">Đóng</button></div><input class="input" id="queue-picker-search" placeholder="Tìm theo tên, mã hồ sơ hoặc mã HIS" autocomplete="off"><div id="queue-picker-results" class="queue-picker-results"></div><div class="foot"><button class="btn btn-secondary" type="button" data-act="close-modal">Hủy</button><button class="btn" id="queue-picker-confirm" type="button" data-act="queue-picker-confirm" disabled>Thêm vào hàng chờ</button></div><p class="queue-picker-register">Chưa có hồ sơ? <button type="button" data-act="queue-picker-register">Đăng ký bệnh nhân</button> trước rồi quay lại đây.</p></div>`);
		loadQueuePickerPatients();
	}
	const head = (title, subtitle = "", actions = "") => `<div class="head"><div><h1>${title}</h1><p>${subtitle}</p></div><div class="actions">${actions}</div></div>`;
	const table = (headers, rows, empty = "Chưa có dữ liệu.", numbered = true) => `<div class="card table-card tablebox"><div class="table-wrap"><table class="table"><thead><tr>${numbered ? "<th>STT</th>" : ""}${headers.map((item) => `<th>${item}</th>`).join("")}</tr></thead><tbody>${rows || `<tr><td colspan="${headers.length + (numbered ? 1 : 0)}">${empty}</td></tr>`}</tbody></table></div></div>`;

	async function loadData() {
		const [queue, patients, reviews, history] = await Promise.all([
			api("qy_vision_hospital.api.xml_intake.list_measurement_queue", { limit: 300 }),
			api("qy_vision_hospital.api.patient_list.list_patients", { page_length: 300 }),
			state.isDoctor || state.isAdmin ? api("qy_vision_hospital.api.clinic_desk.list_pending_reviews", { limit: 100 }) : Promise.resolve({ items: [] }),
			state.isDoctor || state.isAdmin ? api("qy_vision_hospital.api.clinic_desk.list_measurement_history", { limit: 100 }) : Promise.resolve([]),
		]);
		state.queue = queue?.requests || [];
		state.patients = patients?.rows || [];
		state.reviews = (reviews?.items || reviews?.rows || reviews?.results || []).filter((item) => !item.reviewed);
		state.history = history || [];
	}

	function queueRows(items) {
		return items.map((item, index) => {
			const action = item.status === "Chờ đo"
				? `${item.can_start ? `<button class="btn btn-sm" data-act="start" data-id="${esc(item.name)}">Bắt đầu đo</button>` : `<span class="queue-waiting-label">◷ <span>Chờ đến lượt</span></span>`} <button class="btn btn-danger btn-sm" data-act="remove-queue" data-id="${esc(item.name)}">Bỏ lượt</button>`
				: item.status === "Đang đo"
					? `<button class="btn btn-danger btn-sm" data-act="stop" data-id="${esc(item.name)}">Dừng đo</button>`
				: item.visual_acuity_result ? `<button type="button" class="btn btn-secondary btn-sm" data-act="open-result" data-id="${esc(item.visual_acuity_result)}">Xem kết quả</button>` : "Hoàn tất";
			const statusClass = item.status === "Hoàn tất" ? "green" : item.status === "Đang đo" ? "blue" : "amber";
			return `<tr data-status="${esc(item.status)}"><td>${index + 1}</td><td>${esc(item.received_at || "—")}</td><td>${esc(item.patient_name || item.patient || "—")}</td><td>${esc(item.his_patient_id || "—")}</td><td>••••${esc(item.cccd_last4 || "—")}</td><td><span class="status ${statusClass}">${esc(item.status || "Chờ đo")}</span></td><td>${action}</td></tr>`;
		}).join("");
	}

	function renderDashboard() {
		const waiting = state.queue.filter((item) => item.status === "Chờ đo").length;
		const measuring = state.queue.filter((item) => item.status === "Đang đo").length;
		const recent = state.queue.slice(0, 5);
		const days = Array.from({ length: 7 }, (_, index) => {
			const date = new Date();
			date.setDate(date.getDate() - 6 + index);
			const key = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
			return { key, label: `${String(date.getDate()).padStart(2, "0")}/${String(date.getMonth() + 1).padStart(2, "0")}`, count: state.history.filter((item) => (item.creation || "").slice(0, 10) === key).length };
		});
		const maxDay = Math.max(1, ...days.map((item) => item.count));
		const resultCounts = [0, 0, 0];
		const cutoff = new Date();
		cutoff.setDate(cutoff.getDate() - 30);
		state.history.filter((item) => new Date(item.creation) >= cutoff).forEach((item) => {
			const scores = [item.right_score, item.left_score].map((value) => Number.parseFloat(String(value || "").replace(",", "."))).filter(Number.isFinite);
			if (scores.length) resultCounts[Math.min(...scores) >= 8 ? 0 : Math.min(...scores) >= 5 ? 1 : 2] += 1;
		});
		const resultTotal = resultCounts.reduce((sum, value) => sum + value, 0);
		const firstStop = resultTotal ? resultCounts[0] / resultTotal * 100 : 0;
		const secondStop = resultTotal ? (resultCounts[0] + resultCounts[1]) / resultTotal * 100 : 0;
		const chartSegments = `conic-gradient(var(--primary) 0 ${firstStop}%, #54B8D0 ${firstStop}% ${secondStop}%, #F5C266 ${secondStop}% 100%)`;
		return `<div class="note registration-note">VisionCare Hospital · Quản lý hoạt động đo thị lực Quân y</div>
			${head("Tổng quan phòng khám", "Thông tin tiếp nhận và đo thị lực trong ngày hôm nay.", `<button class="btn btn-soft" data-act="refresh">↻ Làm mới</button><button class="btn" data-page="registration">＋ Bệnh nhân mới</button>`)}
			<div class="cards">${[["Tổng bệnh nhân", state.patients.length], ["Bệnh nhân chờ đo", waiting], ...(state.isDoctor || state.isAdmin ? [["Kết quả chờ duyệt", state.reviews.length]] : []), ["Đang đo", measuring]].map(([title, value]) => `<div class="card metric"><div class="metric-top"><span class="label">${title}</span><span class="metric-icon">◉</span></div><div class="value">${value}</div><div class="sub">Cập nhật theo dữ liệu hệ thống</div></div>`).join("")}</div>
			<div class="section-title"><h3>Lối tắt nghiệp vụ</h3></div><div class="card quick"><div class="quick-grid">${state.isDoctor || state.isAdmin ? '<button class="quick-item" data-page="approvals">Duyệt kết quả <span>→</span></button>' : ""}<button class="quick-item" data-page="registration">Đăng ký bệnh nhân <span>→</span></button><button class="quick-item" data-page="queue">Hàng chờ XML HIS <span>→</span></button>${state.isDoctor || state.isAdmin ? '<button class="quick-item" data-page="history">Lịch sử đo <span>→</span></button>' : ""}</div></div>
			<div class="section-title"><h3>Hàng chờ đo</h3><button class="btn btn-secondary" data-page="queue">Xem hàng chờ →</button></div>
			${table(["Thời điểm nhận", "Bệnh nhân", "Mã HIS", "CCCD", "Trạng thái", "Thao tác"], queueRows(recent), "Chưa có bệnh nhân trong hàng chờ đo.")}
			<div class="section-title"><h3>Hoạt động 7 ngày gần đây</h3></div><div class="charts"><div class="card chart-card"><div class="chart-head"><h3>Lượt đo hoàn thành theo ngày</h3><span class="status blue">7 ngày · ${days.reduce((sum, item) => sum + item.count, 0)} lượt</span></div><div class="bar-chart dashboard-bars">${days.map((item) => `<div class="bar" style="height:${item.count ? Math.max(8, item.count / maxDay * 100) : 2}%" title="${item.label}: ${item.count} lượt"><b>${item.count}</b><span>${item.label}</span></div>`).join("")}</div><p class="chart-description">Thống kê số lượt đo đã ghi nhận trong hệ thống trong 7 ngày gần đây.</p></div><div class="card chart-card"><div class="chart-head"><h3>Phân bố kết quả đo</h3><span style="font-size:12px;color:var(--muted)">30 ngày gần đây</span></div><div class="donut-wrap"><div class="donut" style="background:${chartSegments}"></div><div class="donut-center"><b>${resultTotal}</b><span>lượt đo</span></div></div><div class="chart-legend"><div><i style="background:var(--primary)"></i><span>Thị lực ≥ 8/10</span><strong>${resultCounts[0]}</strong></div><div><i style="background:#54B8D0"></i><span>Thị lực 5–7/10</span><strong>${resultCounts[1]}</strong></div><div><i style="background:#F5C266"></i><span>Thị lực &lt; 5/10</span><strong>${resultCounts[2]}</strong></div></div><p class="chart-description">Phân nhóm theo mắt có kết quả thấp hơn trong mỗi lượt đo.</p></div></div>`;
	}

	function renderPatients() {
		const rows = state.patients.map((patient) => {
			const hisId = patient.custom_his_patient_id || patient.name || "—";
			const last4 = patient.custom_cccd_last4 || "";
			const deleteAction = state.canDeletePatients ? `<button class="btn btn-danger btn-sm" data-act="delete-patient" data-id="${esc(patient.name)}" data-name="${esc(patient.patient_name || patient.name)}">Xóa</button>` : "—";
			return `<tr><td>${esc(hisId)}</td><td><button type="button" class="patient-link" data-act="view-patient" data-id="${esc(patient.name)}">${esc(patient.patient_name || patient.name || "—")}</button></td><td>${last4 ? `••••${esc(last4)}` : "—"}</td><td>${esc(patient.mobile || "—")}</td><td>${esc(patient.email || "—")}</td><td>${deleteAction}</td></tr>`;
		}).join("");
		return `${head("Danh sách bệnh nhân", "Tra cứu hồ sơ.", `<button class="btn" data-page="registration">＋ Đăng ký bệnh nhân</button>`)}<div class="toolbar patient-toolbar"><input class="input" id="patient-search" placeholder="Tìm họ tên" value="${esc(state.patientSearch || "")}"></div>${table(["Mã hồ sơ", "Họ tên", "CCCD", "Điện thoại", "Email", "Thao tác"], rows, "Chưa có bệnh nhân.", false)}`;
	}

	function renderPatientDetail() {
		const profile = state.patientProfile?.patient;
		if (!profile) return `${head("Hồ sơ bệnh nhân", "Đang tải thông tin…", `<button class="btn btn-secondary" data-act="back-patients">← Danh sách bệnh nhân</button>`)}<div class="card profile-loading">Đang tải hồ sơ bệnh nhân…</div>`;
		const results = state.patientProfile.results || [];
		const name = profile.patient_name || profile.name || "Bệnh nhân";
		const hisId = profile.custom_his_patient_id || "Chưa có mã HIS";
		const last4 = profile.custom_cccd_last4 ? `••••${profile.custom_cccd_last4}` : "Chưa cập nhật";
		const statusClass = profile.status === "Disabled" ? "gray" : "green";
		const resultRows = results.map((result) => `<tr><td>${esc(result.creation || "—")}</td><td>${esc(result.vision_measurement || "—")}</td><td>${esc(result.right_score || "—")}</td><td>${esc(result.left_score || "—")}</td><td>${esc(result.both_score || "—")}</td><td><button type="button" class="btn btn-secondary btn-sm" data-act="open-result" data-id="${esc(result.name)}">Xem kết quả</button></td></tr>`).join("");
		return `<div class="profile-toolbar"><button class="btn btn-secondary" data-act="back-patients">← Danh sách bệnh nhân</button></div>
			<section class="card patient-hero"><div class="patient-initial">${esc(name.slice(0, 1).toUpperCase())}</div><div class="patient-hero-copy"><span class="eyebrow">HỒ SƠ BỆNH NHÂN</span><h1>${esc(name)}</h1><div class="patient-hero-meta"><span>Mã hồ sơ · ${esc(profile.name)}</span><span class="status ${statusClass}">${esc(profile.status || "Active")}</span></div></div></section>
			<div class="profile-section-heading"><div><h2>Thông tin cá nhân</h2><p>Thông tin lưu trên site Quân y. CCCD chỉ hiển thị 4 số cuối.</p></div></div>
			<section class="profile-info-grid"><article class="card profile-info-card"><span>Mã HIS</span><strong>${esc(hisId)}</strong></article><article class="card profile-info-card"><span>CCCD</span><strong>${esc(last4)}</strong></article><article class="card profile-info-card"><span>Số điện thoại</span><strong>${esc(profile.mobile || "Chưa cập nhật")}</strong></article><article class="card profile-info-card"><span>Email</span><strong>${esc(profile.email || "Chưa cập nhật")}</strong></article><article class="card profile-info-card"><span>Giới tính</span><strong>${esc(profile.sex || "Chưa cập nhật")}</strong></article><article class="card profile-info-card"><span>Ngày tạo hồ sơ</span><strong>${esc(profile.creation || "—")}</strong></article></section>
			<div class="profile-section-heading"><div><h2>Lịch sử đo thị lực</h2><p>${results.length} kết quả gần đây</p></div></div>
			${table(["Thời gian", "Mã phiên đo", "Mắt phải", "Mắt trái", "Hai mắt", ""], resultRows, "Bệnh nhân chưa có kết quả đo.", false)}`;
	}

	function renderQueue() {
		const waiting = state.queue.filter((item) => item.status === "Chờ đo").length;
		const measuring = state.queue.filter((item) => item.status === "Đang đo").length;
		const complete = state.queue.filter((item) => item.status === "Hoàn tất").length;
		const rows = queueRows(state.queue);
		return `<div class="note schedule-note">Hàng chờ được tính riêng theo ngày; hồ sơ bệnh nhân và lịch sử đo vẫn được lưu.</div>${head("Hàng chờ đo", "Điều phối lượt đo trong ngày hôm nay.", `<button class="btn" data-act="add-queue">＋ Thêm bệnh nhân đo</button><button class="btn btn-secondary" data-act="refresh">↻ Làm mới</button>`)}
			<div class="cards schedule-metrics">${[["Tổng lượt trong hàng chờ", state.queue.length], ["Chờ đo", waiting], ["Đang đo", measuring], ["Hoàn tất", complete]].map(([title, value]) => `<div class="card metric"><div class="metric-top"><span class="label">${title}</span></div><div class="value">${value}</div></div>`).join("")}</div>
			<div class="toolbar queue-toolbar"><input class="input" id="queue-search" placeholder="Tìm tên, mã HIS, CCCD"><select id="queue-status"><option value="">Tất cả trạng thái</option><option>Chờ đo</option><option>Đang đo</option><option>Hoàn tất</option></select></div>
			<div id="queue-table">${table(["Thời điểm nhận", "Bệnh nhân", "Mã HIS", "CCCD", "Trạng thái", "Thao tác"], rows, "Chưa có bệnh nhân trong hàng chờ đo.")}</div>`;
	}

	function renderHistory() {
		const rows = state.history.map((result) => `<tr><td>${esc(result.creation || "—")}</td><td>${esc(result.patient_name || result.patient || "—")}</td><td>${esc(result.vision_measurement || result.name || "—")}</td><td>${esc(result.right_score || "—")}</td><td>${esc(result.left_score || "—")}</td><td>${esc(result.both_score || "—")}</td><td><button type="button" class="btn btn-secondary btn-sm" data-act="open-result" data-id="${esc(result.name)}">Xem kết quả</button></td></tr>`).join("");
		return `${head("Lịch sử đo thị lực", "Danh sách các lượt đo đã được ghi nhận trên site Quân y.")}<div class="toolbar"><input class="input" id="history-search" placeholder="Tìm theo bệnh nhân hoặc mã phiên đo"></div>${table(["Thời gian đo", "Bệnh nhân", "Mã phiên đo", "Mắt phải", "Mắt trái", "Hai mắt", "Kết quả"], rows, "Chưa có kết quả đo.")}`;
	}

	function renderApprovals() {
		const rows = state.reviews.map((result) => `<tr><td>${esc(result.creation || "—")}</td><td><b>${esc(result.patient_name || result.patient || "—")}</b></td><td>${esc(result.name || result.visual_acuity || "—")}</td><td>${esc(result.right_score || "—")}</td><td>${esc(result.left_score || "—")}</td><td><span class="status amber">Chờ duyệt</span></td><td><button type="button" class="btn btn-secondary btn-sm" data-act="open-result" data-id="${esc(result.name || result.visual_acuity || "")}">Xem kết quả</button></td></tr>`).join("");
		return `${head("Duyệt kết quả đo thị lực", "Bác sĩ kiểm tra kết quả, xem chi tiết và lưu kết luận.")}<div class="toolbar"><input class="input" id="approval-search" placeholder="Tìm theo tên bệnh nhân hoặc mã phiên"><select id="approval-status"><option value="">Tất cả trạng thái</option><option value="waiting">Chờ duyệt</option></select></div>${table(["Thời gian", "Bệnh nhân", "Mã phiên đo", "Mắt phải", "Mắt trái", "Trạng thái", "Thao tác"], rows, "Không có kết quả chờ duyệt.")}`;
	}

	function renderResults() {
		const result = state.resultDetail;
		if (!result) return `${head("Chi tiết kết quả đo", "Đang tải kết quả…")}`;
		const letters = result.letters || [];
		const letterRows = letters.map((row) => `<tr><td>${esc(row.letter_index || "—")}</td><td>${esc(row.eye || "—")}</td><td>${esc(row.logmar || "—")}</td><td>${esc(row.vn_over_10 || "—")}</td><td>${esc(row.expected || "—")}</td><td>${esc(row.actual || "—")}</td><td>${row.matched ? "Đúng" : "Chưa khớp"}</td></tr>`).join("");
		const reviewForm = result.prescription
			? `<div class="note"><b>Kết luận đã lưu:</b><br>${esc(result.prescription.conclusion || "—")}</div>`
			: `<form id="result-review-form"><input type="hidden" name="patient" value="${esc(result.patient || "")}"><input type="hidden" name="vision_measurement" value="${esc(result.vision_measurement || "")}"><div class="field"><label>Kết luận / chỉ định *</label><textarea class="textarea" name="conclusion" rows="5" required placeholder="Nhập kết luận hoặc chỉ định"></textarea></div><div class="registration-actions"><button class="btn" type="submit">Lưu duyệt kết quả</button></div></form>`;
		return `${head("Chi tiết kết quả đo", `Bệnh nhân: ${esc(result.patient_name || "")}`, `<button class="btn btn-secondary" data-page="approvals">← Danh sách duyệt</button><button class="btn btn-secondary" data-page="history">Lịch sử đo</button>`)}
			<div class="result-layout"><div class="card patient-summary"><h3>${esc(result.patient_name || "Bệnh nhân")}</h3><div class="kv"><span>Mã hồ sơ</span><b>${esc(result.patient || "—")}</b></div><div class="kv"><span>Mã đo</span><b>${esc(result.vision_measurement || "—")}</b></div><div class="kv"><span>Thời gian</span><b>${esc(result.creation || "—")}</b></div><div class="kv"><span>Trạng thái</span><b>${result.prescription ? "Đã duyệt" : "Chờ duyệt"}</b></div></div>
			<div class="card panel"><h3>Kết quả thị lực</h3><div class="eye-cards"><div class="eye-card"><span>Mắt phải</span><b>${esc(result.right_score || "—")}</b></div><div class="eye-card"><span>Mắt trái</span><b>${esc(result.left_score || "—")}</b></div><div class="eye-card"><span>Hai mắt</span><b>${esc(result.both_score || "—")}</b></div></div>
			${letters.length ? `<div class="section-title"><h3>Các ký tự đã kiểm tra</h3><span class="status blue">${letters.length} lượt</span></div>${table(["#", "Mắt", "logMAR", "VN/10", "Dự kiến", "Thực tế", "Kết quả"], letterRows, "", false)}` : ""}${reviewForm}</div></div>`;
	}

	function renderRegistration() {
		return `<div class="note registration-note">Bệnh nhân do HIS chuyển XML sẽ được đưa vào hàng chờ đo tự động.</div>${head("Đăng ký bệnh nhân", "Nhập thông tin tiếp nhận của Quân y. CCCD chỉ lưu 4 số cuối.")}<form id="patient-form" class="card form-card registration-card"><div class="form-grid"><div class="field"><label>Họ và tên *</label><input class="input" name="full_name" required maxlength="140"></div><div class="field"><label>4 số cuối CCCD *</label><input class="input" name="cccd_last4" required inputmode="numeric" pattern="[0-9]{4}" maxlength="4"></div><div class="field"><label>Số điện thoại</label><input class="input" name="mobile" inputmode="numeric"></div><div class="field"><label>Email</label><input class="input" type="email" name="email"></div></div><div class="foot"><button class="btn" type="submit">Lưu bệnh nhân</button><button class="btn btn-secondary" type="button" data-page="patients">Hủy</button></div></form>`;
	}

	function renderSettings() {
		const station = state.settings?.station_id || "station-01";
		const branding = state.branding || {};
		const logoPreview = branding.logo_url ? `<img src="${esc(branding.logo_url)}" alt="Logo xem trước">` : `<span>${esc((branding.clinic_name || "V").slice(0, 1).toUpperCase())}</span>`;
		const palettes = [["#0B8F87", "Xanh ngọc"], ["#2477B8", "Xanh bệnh viện"], ["#168B69", "Xanh lá dịu"], ["#1499B8", "Xanh trời"]];
		return `<div class="note registration-note">Tùy chỉnh tên, logo và màu giao diện riêng cho site Quân y.</div>${head("Cài đặt phòng khám", "Quản lý nhận diện và cấu hình trạm đo.")}
			<form id="branding-form"><section class="card branding-card">
				<div class="settings-section-heading"><span class="metric-icon">▣</span><div><h2>Thông tin nhận diện</h2><p>Thiết lập thông tin và hình ảnh thương hiệu của phòng khám.</p></div></div>
				<div class="branding-form-grid"><div class="branding-fields">
					<div class="field"><label for="clinic-name-input">Tên bệnh viện</label><input id="clinic-name-input" class="input" name="clinic_name" maxlength="100" required value="${esc(branding.clinic_name || "VisionCare Hospital")}"></div>
					<div class="field"><label>Logo phòng khám</label><div class="logo-picker"><div class="logo-preview" id="logo-preview">${logoPreview}</div><div class="logo-picker-actions"><label class="btn btn-secondary" for="brand-logo-file">Tải ảnh lên</label><input id="brand-logo-file" type="file" accept="image/png,image/jpeg,image/webp" hidden><button class="btn btn-secondary" type="button" data-act="remove-logo">Gỡ logo</button><small>JPG, PNG hoặc WEBP · tối đa 700 KB</small></div></div></div>
					<div class="field"><label for="brand-color-input">Màu giao diện</label><div class="color-picker-row"><input id="brand-color-input" name="primary_color" type="color" value="${esc(branding.primary_color || "#0B8F87")}"><strong id="brand-color-label">${esc(branding.primary_color || "#0B8F87")}</strong></div><div class="palette-list">${palettes.map(([color, label]) => `<button type="button" class="palette-swatch ${color.toLowerCase() === (branding.primary_color || "#0B8F87").toLowerCase() ? "selected" : ""}" data-color="${color}" title="${label}" aria-label="${label}" style="--swatch:${color}"><span></span>${label}</button>`).join("")}</div></div>
				</div><aside class="branding-live"><div class="preview-heading"><span class="settings-kicker">XEM TRƯỚC GIAO DIỆN</span><p>Thay đổi sẽ hiển thị như thế này sau khi lưu.</p></div>
					<div class="brand-live-card"><div class="logo-preview live-logo" id="live-logo">${logoPreview}</div><div><b id="live-name">${esc(branding.clinic_name || "VisionCare Hospital")}</b><span>Quân y</span></div><span class="preview-menu">☰</span></div>
					<div class="preview-content"><span class="preview-nav-active">⌂　Tổng quan</span><span>♙　Bệnh nhân</span><button class="live-button" type="button">＋　Thêm bệnh nhân đo</button></div>
					<button class="btn" type="submit" data-act="save-branding">Lưu thay đổi</button>
				</aside></div></section></form>
			<div class="section-title settings-section-title"><div><h3>Kết nối trạm đo</h3><p>Kiểm tra mã trạm cần dùng để kết nối với Jetson.</p></div></div>
			<div class="settings-grid"><section class="card settings-card"><div class="settings-device-title"><span class="metric-icon">⌁</span><div><span class="settings-kicker">CẤU HÌNH THIẾT BỊ</span><h2>Trạng thái trạm đo</h2></div></div><div class="settings-configured"><span class="configured-mark">✓</span><div><b>Đã cấu hình</b><span>Mã trạm đang được thiết lập trên site Quân y.</span></div></div><div class="settings-value"><span>Mã trạm</span><strong>${esc(station)}</strong></div></section>
			<section class="card settings-card settings-help"><div class="settings-device-title"><span class="metric-icon">◇</span><div><span class="settings-kicker">JETSON</span><h2>Ghép nối thiết bị</h2></div></div><p>Mã trạm trong cấu hình Jetson cần trùng với mã đang hiển thị ở đây.</p><div class="settings-code"><code>visiontestai_station_id = ${esc(station)}</code><button type="button" class="btn btn-secondary btn-sm" data-act="copy-station">Sao chép</button></div></section></div>`;
	}

	function renderUsers() {
		const rows = state.users.map((user) => `<tr><td><b>${esc(user.full_name || user.name)}</b></td><td>${esc(user.name)}</td><td><span class="status ${user.enabled ? "green" : "gray"}">${user.enabled ? "Đang hoạt động" : "Đã khóa"}</span></td><td>${esc((user.roles || []).join(", ") || "—")}</td><td>${esc(user.user_type || "System User")}</td></tr>`).join("");
		return `${head("Quản lý người dùng", "Tài khoản nhân viên có quyền truy cập site Quân y.", `<button class="btn" data-act="new-user">＋ Thêm người dùng</button>`)}<div class="note registration-note">Tài khoản được tạo riêng trên site QY; không dùng tài khoản hay API của Trưng Vương.</div>${table(["Họ tên", "Email / Tên đăng nhập", "Trạng thái", "Vai trò", "Loại tài khoản"], rows, "Chưa có tài khoản nhân viên.", false)}`;
	}

	function render() {
		applyBranding();
		const activePage = state.view === "patient_detail" ? "patients" : state.view;
		root.find("[data-page]").removeClass("active").filter(`[data-page="${activePage}"]`).addClass("active");
		root.find("#crumb").text(labels[state.view] || labels.dashboard);
		const views = { dashboard: renderDashboard, patients: renderPatients, patient_detail: renderPatientDetail, queue: renderQueue, history: renderHistory, approvals: renderApprovals, results: renderResults, registration: renderRegistration, settings: renderSettings, users: renderUsers };
		root.find("#view").html((views[state.view] || renderDashboard)());
		document.body.classList.add("visioncare-ready");
		document.documentElement.classList.remove("qy-clinic-booting");
	}

	async function loadAdminView() {
		if (state.view === "users") state.users = await api("qy_vision_hospital.api.clinic_roles.list_clinic_users") || [];
		if (state.view === "patient_detail" && state.selectedPatient) state.patientProfile = await api("qy_vision_hospital.api.patient_list.get_patient_profile", { patient: state.selectedPatient }) || null;
		if (state.view === "results") {
			if (!state.isDoctor && !state.isAdmin) throw new Error("Bạn không có quyền xem kết quả đo.");
			if (!state.selectedResult) throw new Error("Thiếu mã kết quả trong đường dẫn.");
			state.resultDetail = await api("qy_vision_hospital.api.clinic_desk.visual_acuity_detail", { visual_acuity: state.selectedResult });
		}
		if (state.view === "settings" || !state.brandingLoaded) {
			const settings = await api("qy_vision_hospital.api.clinic_roles.get_clinic_settings") || {};
			state.settings = settings;
			state.branding = settings.branding || state.branding;
			state.brandingLoaded = true;
		}
	}
	async function refresh() {
		if ((["history", "approvals", "results"].includes(state.view) && !state.isDoctor && !state.isAdmin) || (["settings", "users"].includes(state.view) && !state.isAdmin)) {
			state.view = "dashboard";
			return frappe.set_route("visioncare");
		}
		try { if (["dashboard", "patients", "queue", "history", "approvals"].includes(state.view)) await loadData(); await loadAdminView(); render(); }
		catch (error) { frappe.msgprint(esc(error.message || "Không tải được dữ liệu.")); }
	}

	root.on("click", "[data-page]", function () {
		const view = this.dataset.page;
		if (!Object.prototype.hasOwnProperty.call(pageRoutes, view)) return;
		if ((["history", "approvals"].includes(view) && !state.isDoctor && !state.isAdmin) || (["settings", "users"].includes(view) && !state.isAdmin)) return;
		const segment = pageRoutes[view];
		if (view === state.view && (frappe.get_route()[1] || null) === (segment || null)) return;
		return segment ? frappe.set_route("visioncare", segment) : frappe.set_route("visioncare");
	});
	frappe.router.on("change", () => {
		const route = frappe.get_route();
		if (route[0] !== "visioncare") return;
		const nextView = routeView[route[1]] || "dashboard";
		if ((["history", "approvals"].includes(nextView) && !state.isDoctor && !state.isAdmin) || (["settings", "users"].includes(nextView) && !state.isAdmin)) {
			state.view = "dashboard";
			return frappe.set_route("visioncare");
		}
		state.view = nextView;
		if (nextView === "patient_detail") state.selectedPatient = route[2] || "";
		else if (nextView === "results") { state.selectedResult = route[2] || ""; state.resultDetail = null; }
		else if (nextView === "patients") state.selectedPatient = "";
		refresh();
	});
	root.on("input", "#clinic-name-input", function () { root.find("#live-name").text(this.value || "VisionCare Hospital"); });
	root.on("input", "#brand-color-input", function () {
		const color = this.value.toUpperCase();
		root.find("#brand-color-label").text(color);
		root.find(".palette-swatch").removeClass("selected");
		applyBranding({ ...state.branding, primary_color: color });
	});
	root.on("click", ".palette-swatch", function () {
		const color = this.dataset.color;
		root.find("#brand-color-input").val(color).trigger("input");
		root.find(".palette-swatch").removeClass("selected");
		$(this).addClass("selected");
	});
	root.on("change", "#brand-logo-file", function () {
		const file = this.files?.[0];
		if (!file) return;
		if (file.size > 700 * 1024) { frappe.msgprint("Logo phải nhỏ hơn 700 KB."); this.value = ""; return; }
		const reader = new FileReader();
		reader.onload = () => {
			const preview = `<img src="${esc(reader.result)}" alt="Logo xem trước">`;
			root.find("#logo-preview, #live-logo").html(preview);
		};
		reader.readAsDataURL(file);
	});
	root.on("click", "[data-act]", async function () {
		const action = this.dataset.act;
		if (action === "refresh") return refresh();
		if (action === "open-result") {
			const visualAcuity = this.dataset.id;
			if (visualAcuity) return frappe.set_route("visioncare", "results", visualAcuity);
			return frappe.msgprint("Không tìm thấy mã kết quả đo.");
		}
		if (action === "view-patient") {
			state.patientProfile = null;
			return frappe.set_route("visioncare", "patient-detail", this.dataset.id || "");
		}
		if (action === "back-patients") {
			state.patientProfile = null;
			return frappe.set_route("visioncare", "patients");
		}
		if (action === "delete-patient") {
			if (!state.canDeletePatients) return frappe.msgprint("Chỉ quản trị viên phòng khám mới được xóa bệnh nhân.");
			const patientId = this.dataset.id || "";
			const patientName = this.dataset.name || patientId;
			return frappe.confirm(`Bạn có chắc muốn xóa hồ sơ “${esc(patientName)}”? Nếu hồ sơ đã có dữ liệu đo liên quan, hệ thống sẽ giữ lại và báo lỗi.`, async () => {
				try {
					await api("qy_vision_hospital.api.patient_list.delete_patient", { patient: patientId });
					notify("Đã xóa hồ sơ bệnh nhân");
					state.selectedPatient = "";
					state.patientProfile = null;
					state.view = "patients";
					await refresh();
				} catch (error) { frappe.msgprint(esc(error.message || "Không xóa được hồ sơ bệnh nhân.")); }
			});
		}
		if (action === "support") return frappe.msgprint("Vui lòng liên hệ quản trị viên hoặc bộ phận kỹ thuật của đơn vị để được hỗ trợ.");
		if (action === "copy-station") {
			try { await navigator.clipboard.writeText(state.settings?.station_id || "station-01"); notify("Đã sao chép mã trạm"); }
			catch (_error) { frappe.msgprint("Trình duyệt chưa cho phép sao chép. Mã trạm: " + (state.settings?.station_id || "station-01")); }
			return;
		}
		if (action === "new-user") return showUserForm();
		if (action === "close-modal") return root.find("#modal").empty();
		if (action === "remove-logo") {
			root.find("#brand-logo-file").val("");
			const fallback = `<span>${esc((root.find("#clinic-name-input").val() || "V").slice(0, 1).toUpperCase())}</span>`;
			root.find("#logo-preview, #live-logo").html(fallback);
			state.branding.logo_url = "";
			return;
		}
		if (action === "start" || action === "stop") {
			const method = action === "start" ? "qy_vision_hospital.api.xml_intake.start_queue_measurement" : "qy_vision_hospital.api.xml_intake.stop_queue_measurement";
			try { await frappe.call({ method, args: { request: this.dataset.id }, freeze: true }); await refresh(); }
			catch (error) { frappe.msgprint(esc(error.message || "Không thực hiện được thao tác.")); }
		}
		if (action === "add-queue") return showQueuePatientPicker();
		if (action === "queue-picker-select") {
			queuePickerSelected = this.dataset.id || "";
			root.find("#queue-picker-confirm").prop("disabled", !queuePickerSelected);
			$(this).addClass("selected").siblings(".queue-picker-row").removeClass("selected").find(".queue-picker-check").text("Chọn");
			$(this).find(".queue-picker-check").text("✓ Đã chọn");
			return;
		}
		if (action === "queue-picker-confirm") {
			if (!queuePickerSelected) return;
			try {
				await api("qy_vision_hospital.api.xml_intake.add_patient_to_measurement_queue", { patient: queuePickerSelected });
				root.find("#modal").empty(); await refresh(); notify("Đã thêm lượt chờ đo hôm nay");
			} catch (error) { frappe.msgprint(esc(error.message || "Không thêm được bệnh nhân.")); }
			return;
		}
		if (action === "queue-picker-register") {
			root.find("#modal").empty(); state.view = "registration"; return render();
		}
		if (action === "remove-queue") {
			return frappe.confirm("Bỏ lượt chờ đo hôm nay? Hồ sơ bệnh nhân vẫn được giữ.", async () => {
				try { await api("qy_vision_hospital.api.xml_intake.cancel_queue_request", { request: this.dataset.id }); await refresh(); notify("Đã bỏ lượt khỏi hàng chờ hôm nay"); }
				catch (error) { frappe.msgprint(esc(error.message || "Không bỏ được lượt.")); }
			});
		}
	});
	root.on("submit", "#branding-form", async function (event) {
		event.preventDefault();
		const form = this;
		const submit = root.find('[data-act="save-branding"]');
		submit.prop("disabled", true).text("Đang lưu…");
		try {
			let logo_url = state.branding.logo_url || "";
			const file = form.querySelector("#brand-logo-file").files?.[0];
			if (file) {
				const data_url = await new Promise((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(reader.result); reader.onerror = reject; reader.readAsDataURL(file); });
				const uploaded = await api("qy_vision_hospital.api.clinic_roles.upload_clinic_logo", { file_name: file.name, content_base64: String(data_url).split(",")[1] });
				logo_url = uploaded.file_url;
			}
			const saved = await api("qy_vision_hospital.api.clinic_roles.save_clinic_branding", { clinic_name: form.elements.clinic_name.value, logo_url, primary_color: form.elements.primary_color.value });
			state.branding = saved.branding;
			state.brandingLoaded = true;
			applyBranding();
			notify("Đã lưu nhận diện phòng khám trên site QY");
			render();
		} catch (error) { frappe.msgprint(esc(error.message || "Không lưu được cài đặt.")); }
		finally { submit.prop("disabled", false).text("Lưu thay đổi"); }
	});
	function showUserForm() {
		root.find("#modal").html(`<div class="dialog"><div class="drawer-head"><h3>Thêm người dùng</h3><button class="btn btn-secondary btn-sm" type="button" data-act="close-modal">Đóng</button></div><form id="user-form"><div class="fields"><div class="field full"><label>Họ tên *</label><input class="input" name="first_name" required maxlength="140"></div><div class="field full"><label>Email đăng nhập *</label><input class="input" type="email" name="email" required></div><div class="field"><label>Mật khẩu tạm *</label><input class="input" type="password" name="password" required minlength="8" autocomplete="new-password"></div><div class="field"><label>Vai trò *</label><select class="input" name="role"><option value="Nursing User">Điều dưỡng</option><option value="Physician">Bác sĩ</option><option value="Healthcare Administrator">Quản trị phòng khám</option></select></div></div><div class="foot"><button class="btn btn-secondary" type="button" data-act="close-modal">Hủy</button><button class="btn" type="submit">Tạo tài khoản</button></div></form></div>`);
	}
	root.on("submit", "#user-form", async function (event) {
		event.preventDefault();
		const args = Object.fromEntries(new FormData(this));
		try { await api("qy_vision_hospital.api.clinic_roles.create_clinic_user", args); root.find("#modal").empty(); notify("Đã tạo tài khoản người dùng"); await loadAdminView(); render(); }
		catch (error) { frappe.msgprint(esc(error.message || "Không tạo được tài khoản.")); }
	});
	root.on("input", "#patient-search, #queue-search, #history-search, #approval-search", function () {
		const query = this.value.toLowerCase();
		if (this.id === "patient-search") state.patientSearch = this.value;
		root.find("#view tbody tr").each(function () { $(this).toggle(this.textContent.toLowerCase().includes(query)); });
	});
	root.on("input", "#queue-picker-search", function () {
		clearTimeout(queuePickerSearchTimer);
		const search = this.value.trim();
		queuePickerSearchTimer = setTimeout(() => loadQueuePickerPatients(search), 250);
	});
	root.on("change", "#queue-status", function () {
		const status = this.value;
		root.find("#view tbody tr").each(function () { $(this).toggle(!status || this.dataset.status === status); });
	});
	root.on("submit", "#result-review-form", async function (event) {
		event.preventDefault();
		const submit = $(this).find('[type="submit"]');
		submit.prop("disabled", true);
		try {
			const saved = await api("qy_vision_hospital.api.clinic_desk.save_eye_prescription", Object.fromEntries(new FormData(this)));
			if (!saved?.success) throw new Error(saved?.error || "Không lưu được kết luận.");
			frappe.show_alert({ message: "Đã duyệt kết quả", indicator: "green" });
			await refresh();
		} catch (error) {
			frappe.msgprint(esc(error.message || "Không lưu được kết luận."));
			submit.prop("disabled", false);
		}
	});
	root.on("submit", "#patient-form", async function (event) {
		event.preventDefault();
		const args = Object.fromEntries(new FormData(this));
		try {
			const result = await api("qy_vision_hospital.api.patient_list.register_patient", args);
			if (!result?.success) throw new Error(result?.error || "Không tạo được hồ sơ bệnh nhân.");
			notify("Đã đăng ký bệnh nhân");
			state.view = "patients";
			await refresh();
		} catch (error) { frappe.msgprint(esc(error.message || "Không đăng ký được bệnh nhân.")); }
	});
	root.find("#menu").on("click", () => root.find("#sidebar").toggleClass("open"));
	root.find("#logout").on("click", () => frappe.call({ method: "logout", callback: () => location.replace("/login") }));
	const bootUser = frappe.boot?.user || {};
	const user = bootUser.full_name || (frappe.session.user === "Administrator" ? "Administrator" : frappe.session.user);
	const userRoles = bootUser.roles || [];
	const isAdmin = frappe.session.user === "Administrator" || userRoles.includes("System Manager") || userRoles.includes("Healthcare Administrator");
	const isDoctor = userRoles.includes("Physician") || isAdmin;
	state.isAdmin = isAdmin;
	state.isDoctor = isDoctor;
	state.canDeletePatients = isAdmin;
	root.find(".admin-nav").toggle(isAdmin);
	root.find(".doctor-nav").toggle(isDoctor);
	const primaryRole = ["System Manager", "Healthcare Administrator", "Physician", "Nursing User"].find((role) => userRoles.includes(role));
	const roleLabels = { "System Manager": "Quản trị hệ thống", "Healthcare Administrator": "Quản trị phòng khám", Physician: "Bác sĩ", "Nursing User": "Điều dưỡng" };
	root.find("#role").text(roleLabels[primaryRole] || "Nhân viên phòng khám");
	root.find("#username").text(user);
	root.find("#avatar, #top-avatar").text((user || "QY").slice(0, 1).toUpperCase());
	root.find("#date").text(new Intl.DateTimeFormat("vi-VN", { dateStyle: "medium" }).format(new Date()));
	frappe.pages.visioncare._cleanup = () => {};
	refresh();
	const timer = setInterval(() => { if (state.view === "queue" || state.view === "dashboard") refresh(); }, 10000);
	$(wrapper).one("remove", () => clearInterval(timer));
};

frappe.pages.visioncare.on_page_show = function () {
	document.body.classList.add("visioncare-fullscreen", "visioncare-ready");
};
frappe.pages.visioncare.on_page_hide = function () {
	frappe.pages.visioncare._cleanup?.();
	document.body.classList.remove("visioncare-fullscreen", "visioncare-ready");
};
