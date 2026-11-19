$(function () {
    // The retired Solvronix Desk app can inject its setup banner after the
    // Desk has rendered. Remove it from the DOM and watch for later inserts.
    function removeLegacySetupPanel() {
        const setupGuide = document.getElementById("st-setup-guide");
        if (setupGuide) setupGuide.remove();
        const panel = Array.from(document.querySelectorAll("body *"))
            .filter((el) => {
                const text = (el.textContent || "").trim();
                return text.includes("Solvronix Desk Setup") &&
                    text.includes("Open Theme Studio") && text.length < 1000;
            })
            .sort((a, b) => a.textContent.trim().length - b.textContent.trim().length)[0];
        if (panel) panel.remove();
    }

    removeLegacySetupPanel();
    const setupPanelObserver = new MutationObserver(removeLegacySetupPanel);
    setupPanelObserver.observe(document.body, { childList: true, subtree: true });

    // Frappe caches standard Page scripts in localStorage, so invalidate the
    // previously broken VisionCare bundle once when this fixed version ships.
    try {
        const pageScriptVersion = "20261015-visioncare-25";
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
