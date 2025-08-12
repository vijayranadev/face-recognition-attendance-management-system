// static/js/register.js (final version)
// Registration flow with auto-training after single or auto capture

const video = document.getElementById("video");
const captureBtn = document.getElementById("captureBtn");
const autoBtn = document.getElementById("autoBtn");
const trainBtn = document.getElementById("trainBtn");
const status = document.getElementById("status");

let stream = null;
let busy = false;

async function initCamera() {
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      video: { width: 640 },
    });
    video.srcObject = stream;
  } catch (e) {
    showStatus(`Camera error: ${e.message}`, "danger");
  }
}

function setBusy(v) {
  busy = v;
  captureBtn.disabled = v;
  autoBtn.disabled = v;
  trainBtn.disabled = v;
}

function showStatus(message, type = "info", spinner = false) {
  const icon = spinner
    ? `<span class="spinner-border spinner-border-sm me-2"></span>`
    : "";
  status.innerHTML = `<div class="alert alert-${type}">${icon}${message}</div>`;
}

function captureFrame() {
  const canvas = document.createElement("canvas");
  canvas.width = video.videoWidth || 640;
  canvas.height = video.videoHeight || 480;
  const ctx = canvas.getContext("2d");
  ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
  return canvas.toDataURL("image/jpeg", 0.8);
}

async function sendImage(dataUrl) {
  const user_id = document.getElementById("user_id").value.trim();
  const user_name = document.getElementById("user_name").value.trim();
  if (!user_id || !user_name) {
    alert("Enter user id and name.");
    return null;
  }
  const form = new URLSearchParams();
  form.append("user_id", user_id);
  form.append("user_name", user_name);
  form.append("image", dataUrl);

  const res = await fetch("/api/save_image", {
    method: "POST",
    body: form,
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
  });
  return res.json();
}

async function triggerTrain(auto = false) {
  showStatus("Training model — please wait...", "info", true);
  try {
    const res = await fetch("/api/train", { method: "POST" });
    const data = await res.json();
    if (data.status === "success") {
      showStatus(`Training complete! ${auto ? "(Auto)" : ""}`, "success");
    } else {
      showStatus(data.message || "Training failed", "danger");
    }
  } catch (e) {
    showStatus(`Training error: ${e.message}`, "danger");
  } finally {
    setBusy(false);
  }
}

// Single Capture
captureBtn.addEventListener("click", async (e) => {
  e.preventDefault();
  if (busy) return;
  setBusy(true);
  showStatus("Capturing image...", "info", true);

  const data = captureFrame();
  const res = await sendImage(data);

  if (res && res.status === "success") {
    showStatus(res.message, "success");
    await triggerTrain(false); // Auto-train after single capture
  } else {
    showStatus(res ? res.message : "Error saving image", "danger");
    setBusy(false);
  }
});

// Auto Capture 30 images
autoBtn.addEventListener("click", async (e) => {
  e.preventDefault();
  if (busy) return;

  const user_id = document.getElementById("user_id").value.trim();
  const user_name = document.getElementById("user_name").value.trim();
  if (!user_id || !user_name) {
    alert("Enter ID & name.");
    return;
  }

  setBusy(true);
  showStatus("Auto-capturing 30 images... Move head slowly.", "info", true);

  let successCount = 0;
  for (let i = 0; i < 30; i++) {
    const data = captureFrame();
    const res = await sendImage(data);
    if (res && res.status === "success") {
      successCount++;
      showStatus(`Captured ${i + 1}/30`, "info", true);
    } else {
      showStatus(res ? res.message : "Capture error", "danger");
      setBusy(false);
      return;
    }
    await new Promise((r) => setTimeout(r, 300)); // delay
  }

  showStatus(
    `Auto-capture complete (${successCount}/30). Training...`,
    "success",
    true
  );
  await triggerTrain(true); // Auto-train after auto capture
});

// Manual Train Button
trainBtn.addEventListener("click", async (e) => {
  e.preventDefault();
  if (busy) return;
  setBusy(true);
  await triggerTrain(false);
});

initCamera();
