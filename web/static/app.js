const state = {
  mode: "merge",
  files: []
};

const modeConfig = {
  merge: {
    title: "LivePhoto 合并",
    hint: "上传同名 JPG/JPEG 与 MP4/MOV 文件，后端会合并成 Motion Photo。",
    accept: ".jpg,.jpeg,.mp4,.mov",
    button: "开始合并"
  },
  split: {
    title: "华为 LivePhoto 拆分",
    hint: "上传华为内嵌 LivePhoto JPG/JPEG，后端会拆分出 JPG 与 MP4。",
    accept: ".jpg,.jpeg",
    button: "开始拆分"
  },
  flyme: {
    title: "Flyme LivePhoto 修复",
    hint: "上传 Flyme LivePhoto JPG/JPEG，后端会补写兼容 Google/Microsoft Photos 的元数据。",
    accept: ".jpg,.jpeg",
    button: "开始修复"
  }
};

const tabs = document.querySelectorAll(".tab");
const modeTitle = document.querySelector("#modeTitle");
const dropHint = document.querySelector("#dropHint");
const dropZone = document.querySelector("#dropZone");
const fileInput = document.querySelector("#fileInput");
const browseButton = document.querySelector("#browseButton");
const clearButton = document.querySelector("#clearButton");
const processButton = document.querySelector("#processButton");
const downloadButton = document.querySelector("#downloadButton");
const fileList = document.querySelector("#fileList");
const fileCount = document.querySelector("#fileCount");
const statusText = document.querySelector("#statusText");
const zipText = document.querySelector("#zipText");
const logOutput = document.querySelector("#logOutput");
const optionRows = document.querySelectorAll("[data-option]");

function formatBytes(size) {
  if (size < 1024 * 1024) {
    return `${(size / 1024).toFixed(1)} KB`;
  }
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

function setMode(mode) {
  state.mode = mode;
  const config = modeConfig[mode];
  tabs.forEach((tab) => tab.classList.toggle("is-active", tab.dataset.mode === mode));
  modeTitle.textContent = config.title;
  dropHint.textContent = config.hint;
  fileInput.accept = config.accept;
  processButton.textContent = config.button;
  downloadButton.classList.add("is-hidden");
  zipText.textContent = "";
  logOutput.textContent = "";
  optionRows.forEach((row) => {
    row.classList.toggle("is-hidden", row.dataset.option !== activeOptionName(mode));
  });
}

function activeOptionName(mode) {
  if (mode === "merge") return "copy_static";
  if (mode === "split") return "copy_non_live";
  return "copy_unchanged";
}

function setFiles(files) {
  state.files = Array.from(files || []);
  renderFiles();
}

function renderFiles() {
  fileList.innerHTML = "";
  downloadButton.classList.add("is-hidden");
  if (!state.files.length) {
    fileCount.textContent = "未选择文件";
    processButton.disabled = true;
    statusText.textContent = "等待文件";
    return;
  }

  fileCount.textContent = `已选择 ${state.files.length} 个文件`;
  processButton.disabled = false;
  statusText.textContent = "准备就绪";
  for (const file of state.files) {
    const item = document.createElement("li");
    const name = document.createElement("span");
    const size = document.createElement("small");
    name.textContent = file.name;
    size.textContent = formatBytes(file.size);
    item.append(name, size);
    fileList.append(item);
  }
}

function buildFormData() {
  const form = new FormData();
  form.append("mode", state.mode);
  form.append("copy_static", document.querySelector("#copyStatic").checked ? "true" : "false");
  form.append("copy_non_live", document.querySelector("#copyNonLive").checked ? "true" : "false");
  form.append("copy_unchanged", document.querySelector("#copyUnchanged").checked ? "true" : "false");
  for (const file of state.files) {
    form.append("files", file, file.name);
  }
  return form;
}

async function processFiles() {
  if (!state.files.length) return;

  processButton.disabled = true;
  downloadButton.classList.add("is-hidden");
  statusText.textContent = "处理中";
  zipText.textContent = "";
  logOutput.textContent = "Uploading and processing files...";

  try {
    const response = await fetch("/api/process", {
      method: "POST",
      body: buildFormData()
    });
    const result = await response.json();
    if (!response.ok || !result.ok) {
      throw new Error(result.error || "处理失败");
    }

    statusText.textContent = "处理完成";
    zipText.textContent = `ZIP: ${formatBytes(result.zip.size)} / ${result.zip.file_count} 个文件`;
    logOutput.textContent = [
      JSON.stringify(result.summary, null, 2),
      "",
      ...result.log
    ].join("\n");
    downloadButton.href = result.download_url;
    downloadButton.classList.remove("is-hidden");
  } catch (error) {
    statusText.textContent = "处理失败";
    logOutput.textContent = error.message;
  } finally {
    processButton.disabled = state.files.length === 0;
  }
}

tabs.forEach((tab) => {
  tab.addEventListener("click", () => setMode(tab.dataset.mode));
});

browseButton.addEventListener("click", () => fileInput.click());
fileInput.addEventListener("change", () => setFiles(fileInput.files));
clearButton.addEventListener("click", () => {
  fileInput.value = "";
  setFiles([]);
  logOutput.textContent = "";
  zipText.textContent = "";
});
processButton.addEventListener("click", processFiles);

dropZone.addEventListener("dragover", (event) => {
  event.preventDefault();
  dropZone.classList.add("is-dragging");
});

dropZone.addEventListener("dragleave", () => {
  dropZone.classList.remove("is-dragging");
});

dropZone.addEventListener("drop", (event) => {
  event.preventDefault();
  dropZone.classList.remove("is-dragging");
  setFiles(event.dataTransfer.files);
});

setMode("merge");
renderFiles();
