/** @odoo-module **/

// Bootstrap 5's data-bs-toggle/data-bs-target attributes (set in portal_templates.xml)
// already wire the modal open/close behavior natively - no jQuery .modal() plugin
// call needed (Bootstrap 5 no longer registers itself onto jQuery).

document.addEventListener("DOMContentLoaded", () => {
    const uploadModal = document.getElementById("uploadModal");
    if (uploadModal) {
        uploadModal.addEventListener("show.bs.modal", () => {
            const form = document.getElementById("uploadForm");
            if (form) {
                form.reset();
            }
            const currentPath = document.querySelector('input[name="current_path"]')?.value || "";
            const uploadCurrentPath = document.getElementById("uploadCurrentPath");
            if (uploadCurrentPath) {
                uploadCurrentPath.value = currentPath;
            }
            const uploadPath = document.getElementById("uploadPath");
            if (uploadPath) {
                uploadPath.textContent = currentPath || "Root Directory";
            }
        });
    }
});
