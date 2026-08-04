/* Sessions page: create, close, and delete sessions through the API. */
"use strict";

document.addEventListener("DOMContentLoaded", () => {
  // --- Create session ---
  const form = document.getElementById("create-session-form");
  if (form) {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const fields = new FormData(form);
      const body = { name: fields.get("name") };
      const lateAfter = fields.get("late_after_minutes");
      if (lateAfter !== null && lateAfter !== "") {
        body.late_after_minutes = parseInt(lateAfter, 10);
      }
      const dept = fields.get("department");
      if (dept) body.department = dept;
      const year = fields.get("year");
      if (year) body.year = parseInt(year, 10);
      try {
        await API.post("/api/v1/sessions", body);
        showAlert("sessions-alerts", "Session created successfully!", "success");
        setTimeout(() => window.location.reload(), 800);
      } catch (error) {
        showAlert("sessions-alerts", error.message);
      }
    });
  }

  // --- Close session ---
  document.querySelectorAll("[data-close-session]").forEach((button) => {
    button.addEventListener("click", async () => {
      button.disabled = true;
      try {
        await API.post(`/api/v1/sessions/${button.dataset.closeSession}/close`);
        showAlert("sessions-alerts", "Session closed.", "success");
        setTimeout(() => window.location.reload(), 800);
      } catch (error) {
        showAlert("sessions-alerts", error.message);
        button.disabled = false;
      }
    });
  });

  // --- Restart session ---
  document.querySelectorAll("[data-restart-session]").forEach((button) => {
    button.addEventListener("click", async () => {
      button.disabled = true;
      try {
        const data = await API.post(`/api/v1/sessions/${button.dataset.restartSession}/restart`);
        const action = data.action === "reopened" ? "Session reopened!" : "New session created for today!";
        showAlert("sessions-alerts", action, "success");
        setTimeout(() => window.location.reload(), 900);
      } catch (error) {
        showAlert("sessions-alerts", error.message);
        button.disabled = false;
      }
    });
  });

  // --- Delete session (with confirmation modal) ---
  let pendingDeleteId = null;
  const deleteModal = document.getElementById("deleteSessionModal");
  const confirmBtn = document.getElementById("confirm-delete-session");

  if (deleteModal && confirmBtn) {
    const bsModal = new bootstrap.Modal(deleteModal);

    document.querySelectorAll("[data-delete-session]").forEach((button) => {
      button.addEventListener("click", () => {
        pendingDeleteId = button.dataset.deleteSession;
        bsModal.show();
      });
    });

    confirmBtn.addEventListener("click", async () => {
      if (!pendingDeleteId) return;
      confirmBtn.disabled = true;
      confirmBtn.innerHTML = `
        <span class="spinner-border spinner-border-sm me-1" role="status"></span>
        Deleting...
      `;
      try {
        await API.delete(`/api/v1/sessions/${pendingDeleteId}`);
        bsModal.hide();
        // Animate the row removal
        const row = document.getElementById(`session-row-${pendingDeleteId}`);
        if (row) {
          row.style.transition = "opacity 0.3s ease, transform 0.3s ease";
          row.style.opacity = "0";
          row.style.transform = "translateX(20px)";
          setTimeout(() => row.remove(), 300);
        }
        showAlert("sessions-alerts", "Session deleted successfully.", "success");
        // Reload after a moment to update the count badge
        setTimeout(() => window.location.reload(), 1200);
      } catch (error) {
        bsModal.hide();
        showAlert("sessions-alerts", error.message);
      } finally {
        confirmBtn.disabled = false;
        confirmBtn.innerHTML = "Delete Session";
        pendingDeleteId = null;
      }
    });
  }
});
