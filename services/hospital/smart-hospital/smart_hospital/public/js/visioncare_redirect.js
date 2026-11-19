$(function () {
    // Frappe caches standard Page scripts in localStorage, so invalidate the
    // previously broken VisionCare bundle once when this fixed version ships.
    try {
        const pageScriptVersion = "20261015-visioncare-23";
        if (localStorage.getItem("visioncare-page-script-version") !== pageScriptVersion) {
            localStorage.removeItem("_page:visioncare");
            localStorage.setItem("visioncare-page-script-version", pageScriptVersion);
        }
    } catch (error) {
        console.warn("Could not refresh cached VisionCare page script", error);
    }

    // Let Frappe restore the session and finish resolving its initial Desk route
    // before redirecting. A full navigation clears any pending Not Permitted
    // dialog from the setup wizard route.
    setTimeout(() => {
        const user = (frappe.boot && frappe.boot.user && frappe.boot.user.name) || "Guest";
        if (user === "Guest") {
            window.location.replace("/login?redirect-to=%2Fdesk%2Fvisioncare");
            return;
        }

        const clinicRoles = new Set(["Nursing User", "Physician", "Healthcare Administrator", "System Manager"]);
        const roles = new Set((frappe.boot && frappe.boot.user && frappe.boot.user.roles) || []);
        if (![...clinicRoles].some(role => roles.has(role))) {
            document.body.classList.add("visioncare-ready");
            return;
        }
        const route = frappe.get_route() || [];
        if (route.includes("visioncare")) return;
        window.location.replace("/desk/visioncare");
    }, 500);
});
