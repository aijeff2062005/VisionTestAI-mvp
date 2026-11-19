// Copyright (c) 2026, a and contributors
// For license information, please see license.txt

frappe.ui.form.on("Visual Acuity", {
	refresh(frm) {
		const eyeLabels = {
			right: __("Right eye"),
			left: __("Left eye"),
			both: __("Both eyes"),
		};
		const localizeEyeCells = () => {
			const grid = frm.fields_dict.letters && frm.fields_dict.letters.grid;
			if (!grid || !grid.wrapper) return;
			grid.wrapper.querySelectorAll("select option").forEach((option) => {
				const value = option.value.toLowerCase();
				if (eyeLabels[value]) option.textContent = eyeLabels[value];
			});
			const walker = document.createTreeWalker(grid.wrapper, NodeFilter.SHOW_TEXT);
			const replacements = [];
			let node;
			while ((node = walker.nextNode())) {
				const value = node.nodeValue.trim().toLowerCase();
				if (eyeLabels[value]) replacements.push([node, eyeLabels[value]]);
			}
			replacements.forEach(([textNode, label]) => { textNode.nodeValue = label; });
		};
		if (frm.__visualAcuityEyeObserver) frm.__visualAcuityEyeObserver.disconnect();
		const gridWrapper = frm.fields_dict.letters?.grid?.wrapper;
		if (gridWrapper && window.MutationObserver) {
			frm.__visualAcuityEyeObserver = new MutationObserver(localizeEyeCells);
			frm.__visualAcuityEyeObserver.observe(gridWrapper, { childList: true, subtree: true });
		}
		setTimeout(localizeEyeCells, 0);

		const field = frm.fields_dict.measurement_summary;
		if (!field || !field.$wrapper) return;

		const escape = (value) => frappe.utils.escape_html(String(value ?? ""));
		let raw = {};
		try {
			raw = frm.doc.result_payload ? JSON.parse(frm.doc.result_payload) : {};
		} catch (error) {
			raw = {};
		}

		const acuity = raw.acuity || {};
		const eye = (key, label) => {
			const item = acuity[key] || {};
			const score = item.vn_over_10 || item.snellen_approx || item.decimal || "—";
			const correct = item.correct != null && item.total != null
				? `${item.correct}/${item.total}`
				: "—";
			return `<div class="col-sm-4">
				<div class="text-muted small">${label}</div>
			<div><strong>${__("VN/10")}:</strong> ${escape(score)}</div>
			<div><strong>${__("LogMAR")}:</strong> ${escape(item.logmar ?? "—")}</div>
			<div><strong>${__("Correct")}:</strong> ${escape(correct)}</div>
			</div>`;
		};

		const protocol = raw.protocol || {};
		const completed = raw.completed_at || raw.completed || "—";
		const trials = Array.isArray(raw.raw_trials) ? raw.raw_trials.length : 0;
		const json = escape(frm.doc.result_payload || "{}");

		field.$wrapper.html(`
			<div class="frappe-card" style="padding:14px;margin-bottom:12px">
				<div class="row">
					${eye("right", __("Right eye"))}
					${eye("left", __("Left eye"))}
					${eye("both", __("Both eyes"))}
				</div>
				<hr style="margin:12px 0">
				<div class="row text-muted small">
					<div class="col-sm-4"><strong>${__("Measurement distance")}:</strong> ${escape(protocol.distance_m ?? "—")} m</div>
					<div class="col-sm-4"><strong>${__("Number of trials")}:</strong> ${escape(trials)}</div>
					<div class="col-sm-4"><strong>${__("Completed at")}:</strong> ${escape(completed)}</div>
				</div>
			</div>
			<details>
				<summary style="cursor:pointer">${__("Technical data (JSON)")}</summary>
				<pre style="white-space:pre-wrap;margin-top:8px;max-height:360px;overflow:auto">${json}</pre>
			</details>
		`);
	},
});
