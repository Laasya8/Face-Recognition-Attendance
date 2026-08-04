/* Enrollment page: capture N webcam snapshots, review them, submit.
   Page parameters (person id, min/max image counts) come from data-*
   attributes on #enroll-root — the CSP forbids inline scripts. */
"use strict";

document.addEventListener("DOMContentLoaded", () => {
  const root = document.getElementById("enroll-root");
  const personId = root.dataset.personId;
  const minImages = parseInt(root.dataset.minImages, 10);
  const maxImages = parseInt(root.dataset.maxImages, 10);

  const video = document.getElementById("enroll-video");
  const startButton = document.getElementById("start-camera");
  const captureButton = document.getElementById("capture-frame");
  const submitButton = document.getElementById("submit-enrollment");
  const shotsContainer = document.getElementById("shots");
  const counter = document.getElementById("shot-counter");

  const webcam = new Webcam(video, 960);
  const shots = []; // data: URLs

  function refresh() {
    counter.textContent = `${shots.length} / ${maxImages}`;
    captureButton.disabled = !webcam.running || shots.length >= maxImages;
    submitButton.disabled =
      shots.length < minImages || shots.length > maxImages;

    shotsContainer.innerHTML = "";
    shots.forEach((dataUrl, index) => {
      const wrapper = document.createElement("div");
      wrapper.className = "position-relative";
      const img = document.createElement("img");
      img.src = dataUrl;
      img.className = "rounded border";
      img.style.width = "96px";
      img.style.height = "72px";
      img.style.objectFit = "cover";
      const remove = document.createElement("button");
      remove.type = "button";
      remove.className =
        "btn-close position-absolute top-0 end-0 bg-white rounded-circle";
      remove.setAttribute("aria-label", "Remove snapshot");
      remove.addEventListener("click", () => {
        shots.splice(index, 1);
        refresh();
      });
      wrapper.append(img, remove);
      shotsContainer.appendChild(wrapper);
    });
  }

  startButton.addEventListener("click", async () => {
    try {
      await webcam.start();
      startButton.disabled = true;
      refresh();
    } catch (error) {
      showAlert("enroll-alerts", `Camera unavailable: ${error.message}`);
    }
  });

  captureButton.addEventListener("click", () => {
    shots.push(webcam.captureDataUrl());
    refresh();
  });

  submitButton.addEventListener("click", async () => {
    submitButton.disabled = true;
    submitButton.textContent = "Enrolling…";
    try {
      await API.post(`/api/v1/persons/${personId}/enroll`, { images: shots });
      webcam.stop();
      window.location.href = "/persons";
    } catch (error) {
      const problems = (error.data.error && error.data.error.problems) || [];
      const detail = problems.length ? ` — ${problems.join("; ")}` : "";
      showAlert("enroll-alerts", error.message + detail);
      submitButton.textContent = "Submit enrollment";
      refresh();
    }
  });

  window.addEventListener("beforeunload", () => webcam.stop());
  refresh();
});
