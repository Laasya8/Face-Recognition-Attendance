/* Kiosk page: continuous capture loop against /api/v1/recognize.
   One frame in flight at a time; the interval only fires when idle.
   UI updates are delegated to window.kioskUI (defined in kiosk.html). */
"use strict";

const CAPTURE_INTERVAL_MS = 1000;

document.addEventListener("DOMContentLoaded", () => {
  const root = document.getElementById("kiosk-root");
  if (!root) return; // no open session
  const sessionId = parseInt(root.dataset.sessionId, 10);

  const video        = document.getElementById("kiosk-video");
  const toggleButton = document.getElementById("kiosk-toggle");

  const webcam = new Webcam(video, 640);
  let timer = null;
  let busy  = false;

  // Thin wrapper: call kioskUI if available, otherwise fall back gracefully
  const ui = window.kioskUI || {
    onStart:   () => {},
    onStop:    () => {},
    onNoFace:  () => {},
    onMatch:   () => {},
    onReview:  () => {},
    onUnknown: () => {},
    onError:   () => {},
  };

  async function tick() {
    if (busy || !webcam.running) return;
    busy = true;
    try {
      const result = await API.post("/api/v1/recognize", {
        image:      webcam.captureDataUrl(0.85),
        session_id: sessionId,
      });

      const results         = result.results || [];
      const acceptedResults = results.filter(r => r.outcome === "accepted");
      const reviewResults   = results.filter(r => r.outcome === "below_threshold");

      if (result.outcome === "no_face" || results.length === 0) {
        ui.onNoFace();
        return;
      }

      if (acceptedResults.length > 0) {
        // Show the first accepted result; call onMatch for each new mark
        const primary = acceptedResults[0];
        const isNew   = primary.attendance && primary.attendance.created;
        ui.onMatch(primary.person, primary.attendance ? primary.attendance.status : "present", isNew);

        // Also add marks for the rest
        acceptedResults.slice(1).forEach(r => {
          if (r.attendance && r.attendance.created) {
            ui.onMatch(r.person, r.attendance.status, true);
          }
        });
      } else if (reviewResults.length > 0) {
        ui.onReview();
      } else {
        ui.onUnknown();
      }
    } catch (error) {
      ui.onError(error.message);
      if (error.status === 409) stop(); // session was closed under us
    } finally {
      busy = false;
    }
  }

  async function start() {
    try {
      await webcam.start();
    } catch (error) {
      ui.onError("Camera unavailable: " + error.message);
      return;
    }
    timer = setInterval(tick, CAPTURE_INTERVAL_MS);
    toggleButton.innerHTML = `
      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="me-1" viewBox="0 0 16 16">
        <path d="M5.5 3.5A1.5 1.5 0 0 1 7 5v6a1.5 1.5 0 0 1-3 0V5a1.5 1.5 0 0 1 1.5-1.5m5 0A1.5 1.5 0 0 1 12 5v6a1.5 1.5 0 0 1-3 0V5a1.5 1.5 0 0 1 1.5-1.5"/>
      </svg>
      Stop Kiosk`;
    toggleButton.className = "btn btn-outline-danger w-100 fw-semibold d-flex align-items-center justify-content-center gap-2";
    ui.onStart();
  }

  function stop() {
    if (timer) clearInterval(timer);
    timer = null;
    webcam.stop();
    toggleButton.innerHTML = `
      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="me-1" viewBox="0 0 16 16">
        <path d="M16 8A8 8 0 1 1 0 8a8 8 0 0 1 16 0M6.79 5.093A.5.5 0 0 0 6 5.5v5a.5.5 0 0 0 .79.407l3.5-2.5a.5.5 0 0 0 0-.814z"/>
      </svg>
      Start Kiosk`;
    toggleButton.className = "btn btn-primary w-100 fw-semibold d-flex align-items-center justify-content-center gap-2";
    ui.onStop();
  }

  toggleButton.addEventListener("click", () => {
    if (webcam.running) stop();
    else start();
  });

  window.addEventListener("beforeunload", stop);
});
