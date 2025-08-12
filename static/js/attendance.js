// attendance.js
const video = document.getElementById("video");
const startBtn = document.getElementById("startBtn");
const stopBtn = document.getElementById("stopBtn");
const log = document.getElementById("log");
const recognizedEl = document.getElementById("recognized");

let stream = null;
let intervalHandle = null;

async function initCamera() {
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      video: { width: 640 },
    });
    video.srcObject = stream;
  } catch (e) {
    log.innerHTML = `<div class="alert alert-danger">Camera error: ${e.message}</div>`;
  }
}

function captureFrame() {
  const canvas = document.createElement("canvas");
  canvas.width = video.videoWidth || 640;
  canvas.height = video.videoHeight || 480;
  const ctx = canvas.getContext("2d");
  ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
  return canvas.toDataURL("image/jpeg", 0.7);
}

async function sendFrame() {
  const dataUrl = captureFrame();
  const form = new URLSearchParams();
  form.append("image", dataUrl);

  try {
    const res = await fetch("/api/process_frame", {
      method: "POST",
      body: form,
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
    });
    const json = await res.json();
    const time = new Date().toLocaleTimeString();
    if (json.status === "recognized") {
      const markedText = json.marked ? " (marked)" : " (already)";
      log.innerHTML =
        `<div class="alert alert-success"> ${time} — ${
          json.name
        } ${markedText} <small class="text-muted">conf:${json.confidence.toFixed(
          1
        )}</small></div>` + log.innerHTML;
      recognizedEl.innerHTML = `<h5 class="mt-2">${
        json.name
      }</h5><p class="text-muted">ID: ${
        json.user_id
      } — conf ${json.confidence.toFixed(1)}</p>`;
    } else if (json.status === "unknown") {
      log.innerHTML =
        `<div class="alert alert-warning"> ${time} — Unknown (conf ${json.confidence.toFixed(
          1
        )})</div>` + log.innerHTML;
    } else if (json.status === "no_face") {
      // optional: show minimal UI
    } else {
      log.innerHTML =
        `<div class="alert alert-danger"> ${time} — Error: ${
          json.message || "server error"
        }</div>` + log.innerHTML;
    }
  } catch (e) {
    console.error(e);
  }
}

startBtn.addEventListener("click", async () => {
  if (!stream) await initCamera();
  intervalHandle = setInterval(sendFrame, 3000);
  startBtn.disabled = true;
  stopBtn.disabled = false;
  log.innerHTML =
    `<div class="alert alert-info">Started scanning (every 3s)</div>` +
    log.innerHTML;
});

stopBtn.addEventListener("click", () => {
  if (intervalHandle) {
    clearInterval(intervalHandle);
    intervalHandle = null;
  }
  startBtn.disabled = false;
  stopBtn.disabled = true;
  log.innerHTML =
    `<div class="alert alert-secondary">Stopped scanning</div>` + log.innerHTML;
});

initCamera();
