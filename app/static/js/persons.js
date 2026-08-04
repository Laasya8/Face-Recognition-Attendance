/* Persons/Students page: creation form posts to API, and delete buttons trigger API deletion. */
"use strict";

document.addEventListener("DOMContentLoaded", () => {
  // 1. Create Student Form Handler
  const form = document.getElementById("create-person-form");
  if (form) {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const fields = new FormData(form);
      const body = {
        code: fields.get("code"),
        full_name: fields.get("full_name"),
      };
      
      const department = fields.get("department");
      if (department) body.department = department;
      
      const year = fields.get("year");
      if (year) body.year = parseInt(year);
      
      const email = fields.get("email");
      if (email) body.email = email;

      try {
        await API.post("/api/v1/persons", body);
        window.location.reload();
      } catch (error) {
        showAlert("persons-alerts", error.message);
      }
    });
  }

  // 2. Delete Student Buttons Handler
  document.querySelectorAll(".delete-person-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const personId = btn.getAttribute("data-person-id");
      const name = btn.getAttribute("data-person-name");
      
      if (confirm(`Are you sure you want to delete student "${name}"? This action will permanently remove their registration, attendance records, and face embeddings.`)) {
        try {
          await API.delete(`/api/v1/persons/${personId}`);
          window.location.reload();
        } catch (error) {
          showAlert("persons-alerts", error.message);
        }
      }
    });
  });
});
