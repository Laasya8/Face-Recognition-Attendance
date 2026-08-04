/* Webcam helper shared by the enrollment and kiosk pages.
   Owns the getUserMedia stream and JPEG frame capture via a canvas. */
"use strict";

class Webcam {
  constructor(videoElement, captureWidth = 640) {
    this.video = videoElement;
    this.captureWidth = captureWidth;
    this.stream = null;
    this.canvas = document.createElement("canvas");
  }

  async start() {
    this.stream = await navigator.mediaDevices.getUserMedia({
      video: { width: { ideal: 1280 }, height: { ideal: 720 }, facingMode: "user" },
      audio: false,
    });
    this.video.srcObject = this.stream;
    await this.video.play();
  }

  stop() {
    if (this.stream) {
      this.stream.getTracks().forEach((track) => track.stop());
      this.stream = null;
      this.video.srcObject = null;
    }
  }

  get running() {
    return this.stream !== null;
  }

  /* Returns a data: URL JPEG of the current frame, downscaled to
     captureWidth to keep request payloads small. */
  captureDataUrl(quality = 0.9) {
    const scale = Math.min(1, this.captureWidth / this.video.videoWidth);
    this.canvas.width = Math.round(this.video.videoWidth * scale);
    this.canvas.height = Math.round(this.video.videoHeight * scale);
    const context = this.canvas.getContext("2d");
    context.drawImage(this.video, 0, 0, this.canvas.width, this.canvas.height);
    return this.canvas.toDataURL("image/jpeg", quality);
  }
}
