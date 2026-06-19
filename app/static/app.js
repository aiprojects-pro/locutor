"use strict";

const STATE_LABELS = {
  pending: "En cola…",
  processing: "Generando audio…",
  done: "Listo",
  error: "Error",
};

function renderRow(wrap, data) {
  wrap.dataset.status = data.status;
  wrap.querySelector(".result-name").textContent = data.source_name;
  const state = wrap.querySelector(".result-state");
  state.textContent = data.error ? data.error : STATE_LABELS[data.status] || data.status;
  state.style.color = data.status === "error" ? "var(--error)" : "var(--muted)";
  wrap.querySelector(".bar > span").style.width = Math.round(data.progress * 100) + "%";

  const dl = wrap.querySelector(".btn-download");
  let audio = wrap.querySelector("audio");
  if (data.download_url) {
    dl.href = data.download_url;
    dl.hidden = false;
    if (!audio) {
      audio = document.createElement("audio");
      audio.controls = true;
      audio.preload = "none";
      wrap.appendChild(audio);
    }
    if (audio.getAttribute("src") !== data.download_url) audio.src = data.download_url;
  } else {
    dl.hidden = true;
    if (audio) audio.remove();
  }
}

function createRow(data) {
  const wrap = document.createElement("div");
  wrap.className = "result-row-wrap";
  wrap.dataset.jobId = data.id;
  wrap.innerHTML =
    '<div class="result-row">' +
    '<span class="result-name"></span>' +
    '<span class="result-state"></span>' +
    '<a class="btn-download" hidden>Descargar</a>' +
    "</div>" +
    '<div class="bar"><span></span></div>';
  renderRow(wrap, data);
  return wrap;
}

async function pollJob(jobId, wrap) {
  try {
    const res = await fetch(`/jobs/${jobId}`, { headers: { Accept: "application/json" } });
    if (!res.ok) return;
    const data = await res.json();
    renderRow(wrap, data);
    if (data.status === "pending" || data.status === "processing") {
      setTimeout(() => pollJob(jobId, wrap), 1000);
    }
  } catch (_e) {
    setTimeout(() => pollJob(jobId, wrap), 2500);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("upload-form");
  const dropzone = document.getElementById("dropzone");
  const fileInput = document.getElementById("files");
  const dzFiles = document.getElementById("dz-files");
  const resultPanel = document.getElementById("result");
  const resultsList = document.getElementById("results-list");
  const btn = document.getElementById("submit-btn");
  const errBox = document.getElementById("form-error");

  // Reanudar trabajos en curso ya presentes.
  resultsList.querySelectorAll(".result-row-wrap").forEach((wrap) => {
    const s = wrap.dataset.status;
    if (s === "pending" || s === "processing") pollJob(wrap.dataset.jobId, wrap);
  });

  function showFiles() {
    dzFiles.innerHTML = "";
    [...fileInput.files].forEach((f) => {
      const chip = document.createElement("div");
      chip.className = "file-chip";
      chip.innerHTML = '<span class="ico">📄</span>';
      chip.appendChild(document.createTextNode(f.name));
      dzFiles.appendChild(chip);
    });
  }
  fileInput.addEventListener("change", showFiles);

  // Arrastrar y soltar.
  ["dragenter", "dragover"].forEach((ev) =>
    dropzone.addEventListener(ev, (e) => { e.preventDefault(); dropzone.classList.add("drag"); })
  );
  ["dragleave", "drop"].forEach((ev) =>
    dropzone.addEventListener(ev, (e) => { e.preventDefault(); dropzone.classList.remove("drag"); })
  );
  dropzone.addEventListener("drop", (e) => {
    if (e.dataTransfer && e.dataTransfer.files.length) {
      fileInput.files = e.dataTransfer.files;
      showFiles();
    }
  });

  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    errBox.hidden = true;
    if (!fileInput.files.length) {
      errBox.textContent = "Selecciona al menos un documento.";
      errBox.hidden = false;
      return;
    }
    btn.disabled = true;
    btn.textContent = "Subiendo…";
    try {
      const res = await fetch("/upload", {
        method: "POST",
        body: new FormData(form),
        headers: { Accept: "application/json" },
      });
      const json = await res.json();
      if (!res.ok) {
        errBox.textContent = json.detail || "No se pudo procesar la solicitud.";
        errBox.hidden = false;
        return;
      }
      resultPanel.hidden = false;
      const wrap = createRow(json);
      resultsList.prepend(wrap);
      pollJob(json.id, wrap);
      form.reset();
      dzFiles.innerHTML = "";
    } catch (_e) {
      errBox.textContent = "Error de red. Inténtalo de nuevo.";
      errBox.hidden = false;
    } finally {
      btn.disabled = false;
      btn.textContent = "Generar audio";
    }
  });
});
