/* Shared fetch wrapper: JSON posts with the CSRF token from base.html.
   API errors become exceptions carrying the server's error envelope. */
"use strict";

const API = {
  csrfToken() {
    return document.querySelector('meta[name="csrf-token"]').content;
  },

  async post(path, body) {
    const response = await fetch(path, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": this.csrfToken(),
      },
      body: JSON.stringify(body || {}),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const message =
        (data.error && data.error.message) || `Request failed (HTTP ${response.status})`;
      const error = new Error(message);
      error.status = response.status;
      error.data = data;
      throw error;
    }
    return data;
  },

  async put(path, body) {
    const response = await fetch(path, {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": this.csrfToken(),
      },
      body: JSON.stringify(body || {}),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const message =
        (data.error && data.error.message) || `Request failed (HTTP ${response.status})`;
      const error = new Error(message);
      error.status = response.status;
      error.data = data;
      throw error;
    }
    return data;
  },

  async delete(path) {
    const response = await fetch(path, {
      method: "DELETE",
      headers: {
        "X-CSRFToken": this.csrfToken(),
      },
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const message =
        (data.error && data.error.message) || `Request failed (HTTP ${response.status})`;
      const error = new Error(message);
      error.status = response.status;
      error.data = data;
      throw error;
    }
    return data;
  },
};

/* Show a modern floating Bootstrap Toast. Kind can be 'danger', 'success', 'warning', 'info' etc. */
function showAlert(containerId, message, kind = "danger") {
  const toastEl = document.getElementById("live-toast");
  if (!toastEl) {
    // Fallback if toast element is not on the page (e.g. login guest page)
    alert(message);
    return;
  }
  
  // Map 'error' or other labels if needed, default Bootstrap classes are bg-danger, bg-success etc.
  let bgClass = kind;
  if (kind === "error") bgClass = "danger";
  
  toastEl.className = `toast align-items-center border-0 text-white bg-${bgClass}`;
  
  const body = toastEl.querySelector(".toast-body");
  if (body) body.textContent = message;
  
  const toast = bootstrap.Toast.getOrCreateInstance(toastEl, { delay: 4000 });
  toast.show();
}
