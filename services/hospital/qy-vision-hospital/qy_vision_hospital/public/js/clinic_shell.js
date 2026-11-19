(function () {
	// Hide Desk while the custom VisionCare page is being initialized on a hard
	// refresh, so the legacy workspace/sidebar cannot flash on clinic routes.
	const clinicPagePath = /\/desk\/visioncare(?:\/|$)/i.test(window.location.pathname || "")
		|| /^#\/?visioncare(?:\/|$)/i.test(window.location.hash || "");
	if (clinicPagePath && document.documentElement) {
		document.documentElement.classList.add("qy-clinic-booting");
		if (!document.getElementById("qy-clinic-boot-style")) {
			const style = document.createElement("style");
			style.id = "qy-clinic-boot-style";
			style.textContent = `
				html.qy-clinic-booting { min-height: 100%; background: #F5F8FA !important; }
				html.qy-clinic-booting body { visibility: hidden !important; }
			`;
			document.head.appendChild(style);
		}
	}

	// Frappe's language picker uses every Language record, even when disabled.
	// The clinic UI supports Vietnamese and English only.
	if (frappe.boot && frappe.boot.lang_dict) {
		frappe.boot.lang_dict = Object.fromEntries(
			Object.entries(frappe.boot.lang_dict).filter(([, code]) => code === "vi" || code === "en")
		);
		frappe.languages = null;
	}

	const FALLBACK_HOME = "visioncare";
	const SMART_HOSPITAL_APP = "qy_vision_hospital";
	const APP_VERSION_CHECK_INTERVAL_MS = 30000;
	const BOOKING_PAGE_CACHE_VERSION = "fresh-booking-1";
	const CLINIC_WORKSPACES = [];
	const WORKSPACE_ICONS = {
		Nurse: "users-round",
		Doctor: "stethoscope",
		"Clinic Admin": "settings",
	};
	const LEGACY_WORKSPACE_ROUTES = new Set([
		"clinic-admin",
		"nurse",
		"doctor",
		"bác-sĩ",
		"điều-dưỡng",
		"quản-trị-phòng-khám",
	]);
	const LEGACY_PAGE_VIEWS = {
		"clinic-patients": "patients",
		"nurse-station": "queue",
		"doctor-review": "reviews",
		"patient-registration": "registration",
	};
	const ROLE_HOME_PRIORITY = [
		"Healthcare Administrator",
		"System Manager",
		"Physician",
		"Nursing User",
	];

	const ENTITY_WORKSPACE = {
		"nurse-station": "Nurse",
		"patient-registration": "Nurse",
		"clinic-patients": "Nurse",
		"patient-vision-booking": "Nurse",
		Patient: "Nurse",
		"Patient Appointment": "Nurse",
		"doctor-review": "Doctor",
		"Visual Acuity": "Doctor",
		"Eye Prescription": "Doctor",
		// Shared pages keep the current role sidebar (nurse or doctor).
		"Vision Measurement": "Clinic Admin",
		"Connection Settings": "Clinic Admin",
		"face-service-test": "Clinic Admin",
	};

	function shellConfig() {
		return (frappe.boot && frappe.boot.clinic_shell) || { enabled: false };
	}

	function isEnabled() {
		return !!shellConfig().enabled;
	}

	function homePage() {
		const cfg = shellConfig();
		const roles = (frappe.boot && frappe.boot.user && frappe.boot.user.roles) || [];
		const roleSet = new Set(roles);
		for (const role of ROLE_HOME_PRIORITY) {
			if (roleSet.has(role) && cfg.role_home_page && cfg.role_home_page[role]) {
				return cfg.role_home_page[role];
			}
		}
		for (const role of roles) {
			if (cfg.role_home_page && cfg.role_home_page[role]) {
				return cfg.role_home_page[role];
			}
		}
		return FALLBACK_HOME;
	}

	function isClinicAdministrator() {
		const user = (frappe.boot && frappe.boot.user) || {};
		if (user.name === "Administrator" || (frappe.session && frappe.session.user === "Administrator")) {
			return true;
		}
		const roles = user.roles || [];
		return roles.includes("Healthcare Administrator") || roles.includes("System Manager");
	}

	function slug(value) {
		return String(value || "")
			.toLowerCase()
			.replace(/ /g, "-");
	}

	function clinicEntityFromRoute(route) {
		if (!route || !route.length) {
			return null;
		}
		const head = route[0];
		if (ENTITY_WORKSPACE[head]) {
			return head;
		}
		if ((head === "List" || head === "Form" || head === "Tree") && route[1] && ENTITY_WORKSPACE[route[1]]) {
			return route[1];
		}
		if (head === "Workspaces" && CLINIC_WORKSPACES.includes(route[route.length - 1])) {
			return route[route.length - 1];
		}
		const headSlug = slug(head);
		for (const name of Object.keys(ENTITY_WORKSPACE)) {
			if (slug(name) === headSlug) {
				return name;
			}
		}
		return null;
	}

	function redirectLegacyWorkspaceRoute(route) {
		if (!route || !route.length) return false;
		const first = slug(route[0]);
		const workspace = LEGACY_WORKSPACE_ROUTES.has(first)
			|| (first === "private" && route[1] && LEGACY_WORKSPACE_ROUTES.has(slug(route[1])));
		if (workspace) {
			frappe.set_route("visioncare");
			return true;
		}
		const view = LEGACY_PAGE_VIEWS[first];
		if (view) {
			frappe.set_route("visioncare", view);
			return true;
		}
		return false;
	}

	function isAllowedDoctypeSlug(doctypeSlug) {
		const cfg = shellConfig();
		return (cfg.allowed_doctype_slugs || []).includes(doctypeSlug);
	}

	function isAllowedRoute(route) {
		if (!route || !route.length) {
			return true;
		}
		const cfg = shellConfig();
		const head = route[0];
		const headSlug = slug(head);

		if (cfg.allowed_pages && (cfg.allowed_pages.includes(head) || cfg.allowed_pages.includes(headSlug))) {
			return true;
		}
		if (cfg.allowed_workspaces && cfg.allowed_workspaces.includes(head)) {
			return true;
		}
		if (cfg.allowed_workspace_slugs && cfg.allowed_workspace_slugs.includes(headSlug)) {
			return true;
		}
		if (headSlug === "private" && route[1]) {
			return (cfg.allowed_workspace_slugs || []).includes(slug(route[1]));
		}
		if (cfg.allowed_doctype_slugs && cfg.allowed_doctype_slugs.includes(headSlug)) {
			return isAllowedDoctypeSlug(headSlug);
		}

		if (head === "List" && route[1]) {
			return isAllowedDoctypeSlug(slug(route[1]));
		}
		if (head === "Form" && route[1]) {
			return isAllowedDoctypeSlug(slug(route[1]));
		}
		if (head === "Workspaces" && route[route.length - 1]) {
			const ws = route[route.length - 1];
			return (
				(cfg.allowed_workspaces || []).includes(ws) ||
				(cfg.allowed_workspace_slugs || []).includes(slug(ws))
			);
		}

		if (["desk", "app", "desktop", "login", "workspace"].includes(headSlug)) {
			return true;
		}

		return false;
	}

	function isBlockedRoute(route) {
		if (!route || !route.length) {
			return false;
		}
		const cfg = shellConfig();
		const headSlug = slug(route[0]);

		if ((cfg.blocked_workspace_slugs || []).includes(headSlug)) {
			return true;
		}
		if ((cfg.blocked_pages || []).includes(route[0]) || (cfg.blocked_pages || []).includes(headSlug)) {
			return true;
		}
		return false;
	}

	function isDesktopLanding(route) {
		if (!route || !route.length) {
			return true;
		}
		const headSlug = slug(route[0]);
		return ["desk", "app", "desktop", "workspace", "workspaces"].includes(headSlug) && route.length <= 1;
	}

	function lucideIconHtml(iconName, size) {
		if (!frappe.utils || !frappe.utils.icon) {
			return "";
		}
		return `<div class="icon-container">${frappe.utils.icon(iconName, size || "sm")}</div>`;
	}

	function patchAlphabetDesktopIcons() {
		if (!frappe.utils || !frappe.utils.desktop_icon || frappe.utils._clinic_icon_patched) {
			return;
		}
		frappe.utils._clinic_icon_patched = true;
		const original = frappe.utils.desktop_icon.bind(frappe.utils);
		frappe.utils.desktop_icon = function (label, color, size) {
			const lucide = WORKSPACE_ICONS[label];
			const letter = String(label || "")
				.charAt(0)
				.toUpperCase();
			if (lucide && !/^[A-Z]$/.test(letter)) {
				return lucideIconHtml(lucide, size);
			}
			if (lucide && CLINIC_WORKSPACES.includes(label)) {
				return lucideIconHtml(lucide, size);
			}
			return original(label, color, size);
		};
	}

	function fixClinicHeaderIcon() {
		const sidebar = frappe.app && frappe.app.sidebar;
		if (!sidebar) {
			return;
		}
		const title = sidebar.sidebar_title;
		const lucide = WORKSPACE_ICONS[title];
		if (!lucide) {
			return;
		}
		const $logo = $(".sidebar-header .header-logo");
		if (!$logo.length) {
			return;
		}
		$logo.html(lucideIconHtml(lucide, "md"));
	}

	function pinSmartHospitalApp() {
		const app = ((frappe.boot && frappe.boot.app_data) || []).find(
			(row) => row.app_name === SMART_HOSPITAL_APP
		);
		if (app) {
			frappe.current_app = app;
		}
	}

	function restrictClinicAppNavigation() {
		if (!isEnabled() || !frappe.boot) {
			return;
		}
		const smartHospital = (frappe.boot.app_data || []).find(
			(app) => app.app_name === SMART_HOSPITAL_APP
		);
		if (!smartHospital) {
			return;
		}

		// The Frappe app switcher is built from app_data; keep only Smart Hospital.
		frappe.boot.app_data = [smartHospital];
		// Keep the clinic workspaces inside Smart Hospital while removing other apps' icons.
		frappe.boot.desktop_icons = (frappe.boot.desktop_icons || []).filter(
			(icon) => CLINIC_WORKSPACES.includes(icon.label)
		);
		frappe.current_app = smartHospital;
	}

	function hideAppSwitcher() {
		if (!isEnabled() || document.getElementById("smart-hospital-hide-app-switcher")) {
			return;
		}
		const style = document.createElement("style");
		style.id = "smart-hospital-hide-app-switcher";
		style.textContent = `
			#st-icon-rail, .app-switcher, .apps-nav, .desk-app-switcher {
				display: none !important;
			}
		`;
		document.head.appendChild(style);
	}

	function keepAccountAndLanguageOnly() {
		if (document.getElementById("clinic-toolbar-minimal-style")) {
			return;
		}
		const style = document.createElement("style");
		style.id = "clinic-toolbar-minimal-style";
		style.textContent = `
			#st-top-toolbar {
				justify-content: flex-end !important;
			}
			#st-top-toolbar .st-tb-right {
				margin-left: auto !important;
				padding-right: 16px;
			}
			#st-top-toolbar .st-tb-right > :not(#st-lang-wrapper):not(#st-user-btn) {
				display: none !important;
			}
		`;
		document.head.appendChild(style);
	}

	function pinClinicChrome() {
		const route = frappe.get_route() || [];
		const entity = clinicEntityFromRoute(route);
		if (!entity) {
			return;
		}
		pinSmartHospitalApp();
		if (!frappe.app || !frappe.app.sidebar || !frappe.app.sidebar.setup) {
			return;
		}
		const current = frappe.app.sidebar.sidebar_title;
		// Keep administrators on their four-item Clinic Admin sidebar while
		// opening any clinical task. Switching to Nurse/Doctor here exposes a
		// different set of links and makes the navigation appear to change.
		const target = isClinicAdministrator()
			? "Clinic Admin"
			: (CLINIC_WORKSPACES.includes(current) && current) ||
			  ENTITY_WORKSPACE[entity] ||
			  CLINIC_WORKSPACES[0];
		if (current !== target) {
			frappe.app.sidebar.setup(target);
		}
		fixClinicHeaderIcon();
	}

	function redirectHome() {
		frappe.set_route(homePage());
	}

	function startAppVersionWatcher() {
		if (window._smartHospitalVersionWatcherStarted) {
			return;
		}
		window._smartHospitalVersionWatcherStarted = true;
		let currentVersion = null;
		const checkVersion = function () {
			frappe.call({
				method: "qy_vision_hospital.api.clinic_shell.get_app_version",
				callback: function (r) {
					const nextVersion = r.message && r.message.version;
					if (!nextVersion) {
						return;
					}
					if (currentVersion && currentVersion !== nextVersion) {
						if (typeof cur_frm === "undefined" || !cur_frm || !cur_frm.is_dirty()) {
							window.location.reload();
						}
						return;
					}
					currentVersion = nextVersion;
				},
			});
		};
		checkVersion();
		window.setInterval(checkVersion, APP_VERSION_CHECK_INTERVAL_MS);
	}

	function startDataUpdateBridge() {
		if (window._smartHospitalDataUpdateBridgeStarted || !frappe.realtime) {
			return;
		}
		window._smartHospitalDataUpdateBridgeStarted = true;
		const clinicDocTypes = new Set([
			"Patient",
			"Patient Appointment",
			"Vision Measurement",
			"Visual Acuity",
			"Eye Prescription",
			"Connection Settings",
		]);
		let refreshTimer = null;
		const handleDataUpdate = function (doc) {
			$(document).trigger("smart-hospital-data-updated", [doc || {}]);
			const doctype = doc && (doc.doctype || doc.doc_type);
			if (!clinicDocTypes.has(doctype)) {
				return;
			}
			window.clearTimeout(refreshTimer);
			refreshTimer = window.setTimeout(function () {
				if (typeof cur_frm !== "undefined" && cur_frm && cur_frm.is_dirty()) {
					return;
				}
				if (document.visibilityState === "visible") {
					window.location.reload();
				}
			}, 500);
		};
		frappe.realtime.on("doc_update", handleDataUpdate);
		frappe.realtime.on("smart_hospital_data_updated", handleDataUpdate);
	}

	function hideSolvronixSetupPanel() {
		// Always target the guide itself. During initial workspace rendering its
		// ancestors temporarily contain only the guide text too; selecting one of
		// those ancestors can hide the entire Desk page before the workspace loads.
		const setupGuide = document.getElementById("st-setup-guide");
		if (setupGuide) {
			setupGuide.style.display = "none";
			return;
		}

		const panel = Array.from(document.querySelectorAll("body *"))
			.filter((el) => {
				const text = el.textContent.trim();
				return (
					!el.closest(".page-body, .page-wrapper, .page-content, .layout-main") &&
					text.includes("Solvronix Desk Setup") &&
					text.includes("Open Theme Studio") &&
					text.length < 1000
				);
			})
			.sort((a, b) => a.textContent.trim().length - b.textContent.trim().length)[0];
		if (!panel) {
			return;
		}
		panel.style.display = "none";
	}

	function guardRoute() {
		if (redirectLegacyWorkspaceRoute(frappe.get_route() || [])) return;
		patchSidebarResolver();
		pinClinicChrome();
		if (!isEnabled()) {
			return;
		}
		const route = frappe.get_route() || [];
		// After login → /desk, send nurse/doctor to their clinical home page.
		if (isDesktopLanding(route)) {
			redirectHome();
			return;
		}
		if (isBlockedRoute(route) || !isAllowedRoute(route)) {
			redirectHome();
		}
	}

	function patchSidebarResolver() {
		const sidebar = frappe.app && frappe.app.sidebar;
		if (!sidebar) {
			return false;
		}
		if (sidebar._clinic_shell_sidebar_patched) {
			return true;
		}
		sidebar._clinic_shell_sidebar_patched = true;
		const original = sidebar.set_workspace_sidebar.bind(sidebar);
		sidebar.set_workspace_sidebar = function (router) {
			original(router);
			const entity = clinicEntityFromRoute(frappe.get_route() || []);
			if (isEnabled() && isClinicAdministrator() && entity) {
				if (this.sidebar_title !== "Clinic Admin") {
					this.setup("Clinic Admin");
				}
			} else {
				pinClinicChrome();
			}
		};
		return true;
	}

	function patchRouter() {
		if (!frappe.router || frappe.router._clinic_shell_patched) {
			return;
		}
		frappe.router._clinic_shell_patched = true;

		const originalConvert = frappe.router.convert_to_standard_route.bind(frappe.router);
		frappe.router.convert_to_standard_route = async function (route) {
			if (isEnabled() && route && route.length) {
				const first = slug(route[0]);
				const workspace = LEGACY_WORKSPACE_ROUTES.has(first)
					|| (first === "private" && route[1] && LEGACY_WORKSPACE_ROUTES.has(slug(route[1])));
				if (workspace) {
					frappe.route_flags.replace_route = true;
					return ["visioncare"];
				}
				if (LEGACY_PAGE_VIEWS[first]) {
					frappe.route_flags.replace_route = true;
					return ["visioncare", LEGACY_PAGE_VIEWS[first]];
				}
				const headSlug = slug(route[0]);
				if (
					(shellConfig().blocked_workspace_slugs || []).includes(headSlug) ||
					(shellConfig().blocked_pages || []).includes(route[0]) ||
					(shellConfig().blocked_pages || []).includes(headSlug)
				) {
					frappe.route_flags.replace_route = true;
					return [homePage()];
				}
			}
			return originalConvert(route);
		};

		frappe.router.on("change", guardRoute);
	}

	function initClinicShell() {
		try {
			if (localStorage.getItem("smart-hospital-booking-cache-version") !== BOOKING_PAGE_CACHE_VERSION) {
				localStorage.removeItem("_page:patient-vision-booking");
				localStorage.setItem("smart-hospital-booking-cache-version", BOOKING_PAGE_CACHE_VERSION);
			}
		} catch (e) {
			// Private browsing may disable localStorage; Page loading still works.
		}
		restrictClinicAppNavigation();
		hideAppSwitcher();
		keepAccountAndLanguageOnly();
		patchAlphabetDesktopIcons();
		patchRouter();
		patchSidebarResolver();
		hideSolvronixSetupPanel();
		window.setTimeout(hideSolvronixSetupPanel, 300);
		window.setTimeout(hideSolvronixSetupPanel, 1000);
		startAppVersionWatcher();
		startDataUpdateBridge();
		pinClinicChrome();
		if (isEnabled()) {
			guardRoute();
		}
	}

	initClinicShell();
	$(document).on("app-ready", initClinicShell);
})();
