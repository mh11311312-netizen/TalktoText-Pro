// Front-end logic for the whole app. No framework, just vanilla JS. Each page
// calls its init function from an inline <script> at the bottom of its template.

// --- Dark mode ---
// Kept in localStorage so it sticks across pages. base.html applies it on
// <html> before paint; this just handles the toggle and the button label.

function applyThemeLabel() {
  const btn = document.getElementById("themeToggle");
  if (!btn) return;
  const isDark = document.documentElement.getAttribute("data-theme") === "dark";
  btn.textContent = isDark ? "☀️ Light mode" : "🌙 Dark mode";
}

// Set the correct button label when the page loads.
document.addEventListener("DOMContentLoaded", applyThemeLabel);

// Toggle the theme when the button is clicked, and remember the choice.
document.addEventListener("click", function (e) {
  if (e.target && e.target.id === "themeToggle") {
    const isDark = document.documentElement.getAttribute("data-theme") === "dark";
    if (isDark) {
      document.documentElement.removeAttribute("data-theme");
      try { localStorage.setItem("ttp-theme", "light"); } catch (err) {}
    } else {
      document.documentElement.setAttribute("data-theme", "dark");
      try { localStorage.setItem("ttp-theme", "dark"); } catch (err) {}
    }
    applyThemeLabel();
  }
});


// --- New Meeting page: upload / record + progress polling ---
function initNewMeetingPage() {
  let recordedBlob = null;      // holds audio recorded in the browser
  let mediaRecorder = null;
  let chunks = [];

  const fileInput = document.getElementById("fileInput");
  const fileName = document.getElementById("fileName");
  const recordBtn = document.getElementById("recordBtn");
  const recordStatus = document.getElementById("recordStatus");
  const processBtn = document.getElementById("processBtn");

  // Show the chosen file's name.
  fileInput.addEventListener("change", () => {
    recordedBlob = null; // choosing a file cancels any recording
    fileName.textContent = fileInput.files.length
      ? "Selected: " + fileInput.files[0].name : "";
  });

  // --- Live recording using the browser microphone ---
  recordBtn.addEventListener("click", async () => {
    if (mediaRecorder && mediaRecorder.state === "recording") {
      mediaRecorder.stop();
      recordBtn.textContent = "● Start recording";
      recordBtn.classList.remove("recording");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaRecorder = new MediaRecorder(stream);
      chunks = [];
      mediaRecorder.ondataavailable = (e) => chunks.push(e.data);
      mediaRecorder.onstop = () => {
        recordedBlob = new Blob(chunks, { type: "audio/webm" });
        recordStatus.textContent = "✅ Recording ready (" +
          Math.round(recordedBlob.size / 1024) + " KB)";
        stream.getTracks().forEach((t) => t.stop());
      };
      mediaRecorder.start();
      recordBtn.textContent = "■ Stop recording";
      recordBtn.classList.add("recording");
      recordStatus.textContent = "🔴 Recording...";
    } catch (err) {
      alert("Could not access microphone: " + err.message);
    }
  });

  // --- Send the audio to the server and track progress ---
  processBtn.addEventListener("click", async () => {
    const form = new FormData();
    if (fileInput.files.length) {
      form.append("audio", fileInput.files[0]);
    } else if (recordedBlob) {
      form.append("audio", recordedBlob, "recording.webm");
    } else {
      alert("Please upload a file or record audio first.");
      return;
    }
    form.append("title", document.getElementById("title").value || "Untitled Meeting");
    form.append("language", document.getElementById("language").value);
    form.append("output_language", document.getElementById("output_language").value);

    // Show the progress area and disable the button.
    document.getElementById("progressArea").classList.remove("hidden");
    processBtn.disabled = true;
    processBtn.textContent = "Processing...";

    try {
      const res = await fetch("/upload", { method: "POST", body: form });
      const data = await res.json();
      if (data.error) { throw new Error(data.error); }
      pollStatus(data.job_id);
    } catch (err) {
      alert("Upload failed: " + err.message);
      processBtn.disabled = false;
      processBtn.textContent = "✨ Generate Meeting Notes";
    }
  });

  // Ask the server every second how the job is going.
  function pollStatus(jobId) {
    const bar = document.getElementById("progressBar");
    const msg = document.getElementById("progressMessage");

    const timer = setInterval(async () => {
      const res = await fetch("/status/" + jobId);
      const job = await res.json();

      bar.style.width = (job.progress || 5) + "%";
      msg.textContent = job.message || "Working...";
      highlightStep(job.message || "");

      if (job.status === "done") {
        clearInterval(timer);
        window.location.href = "/results/" + job.meeting_id;
      } else if (job.status === "error") {
        clearInterval(timer);
        msg.textContent = "❌ " + job.message;
        processBtn.disabled = false;
        processBtn.textContent = "✨ Generate Meeting Notes";
      }
    }, 1000);
  }

  // Light up the matching step label based on the status message.
  function highlightStep(message) {
    const map = { Transcrib: "transcribe", Translat: "translate",
                  Clean: "optimize", Optimiz: "optimize", Generat: "generate" };
    document.querySelectorAll(".steps span").forEach((s) => s.classList.remove("active"));
    for (const key in map) {
      if (message.includes(key)) {
        const el = document.querySelector(`.steps span[data-step="${map[key]}"]`);
        if (el) el.classList.add("active");
      }
    }
  }
}


// --- Results page: charts, chat, action items, email, translate, listen ---
function initResultsPage() {
  const meetingId = document.getElementById("meetingData").dataset.id;

  // --- Analytics chart (counts of points/decisions/actions) ---
  const cd = document.getElementById("chartData").dataset;
  const ctx = document.getElementById("statsChart");
  if (ctx && window.Chart) {
    new Chart(ctx, {
      type: "bar",
      data: {
        labels: ["Key Points", "Decisions", "Action Items"],
        datasets: [{
          label: "Count",
          data: [Number(cd.keypoints), Number(cd.decisions), Number(cd.actions)],
          backgroundColor: ["#5c7cfa", "#2f9e44", "#f08c00"],
          borderRadius: 6,
        }],
      },
      options: {
        plugins: { legend: { display: false } },
        scales: { y: { beginAtZero: true, ticks: { precision: 0 } } },
      },
    });
  }

  // --- Speaker talk-time chart (only when diarization data exists) ---
  const talkEl = document.getElementById("talkTimeChart");
  const talkData = readJson("talkTimeData");
  if (talkEl && window.Chart && talkData && Object.keys(talkData).length) {
    new Chart(talkEl, {
      type: "doughnut",
      data: {
        labels: Object.keys(talkData),
        datasets: [{
          data: Object.values(talkData),
          backgroundColor: ["#5c7cfa", "#2f9e44", "#f08c00", "#e64980", "#15aabf", "#7048e8"],
        }],
      },
      options: { plugins: { legend: { position: "bottom" } } },
    });
  }

  // --- Sentiment timeline chart (mood over the meeting) ---
  const tlEl = document.getElementById("timelineChart");
  const tlData = readJson("timelineData");
  if (tlEl && window.Chart && Array.isArray(tlData) && tlData.length) {
    new Chart(tlEl, {
      type: "line",
      data: {
        labels: tlData.map((t) => t.part || ""),
        datasets: [{
          label: "Mood (-5 to +5)",
          data: tlData.map((t) => t.score),
          borderColor: "#5c7cfa",
          backgroundColor: "rgba(92,124,250,0.15)",
          fill: true,
          tension: 0.35,
        }],
      },
      options: { scales: { y: { min: -5, max: 5 } } },
    });
  }

  // --- "Listen to Notes" button (plays AI voice summary) ---
  const listenBtn = document.getElementById("listenBtn");
  if (listenBtn) {
    listenBtn.addEventListener("click", async () => {
      const audio = document.getElementById("notesAudio");
      listenBtn.textContent = "⏳ Generating audio...";
      try {
        const res = await fetch("/listen/" + meetingId);
        if (!res.ok) throw new Error("Could not generate audio.");
        const blob = await res.blob();
        audio.src = URL.createObjectURL(blob);
        audio.classList.remove("hidden");
        audio.play();
        listenBtn.textContent = "🔊 Listen to Notes";
      } catch (err) {
        alert("Error: " + err.message);
        listenBtn.textContent = "🔊 Listen to Notes";
      }
    });
  }

  // --- Action item checkboxes (save done/not-done) ---
  document.querySelectorAll(".ai-check").forEach((box) => {
    box.addEventListener("change", () => {
      const items = [];
      document.querySelectorAll(".action-item").forEach((row) => {
        items.push({
          task: row.querySelector(".ai-task").textContent.trim(),
          meta: row.querySelector(".ai-meta").textContent.trim(),
          done: row.querySelector(".ai-check").checked,
        });
      });
      fetch("/action-items/" + meetingId, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action_items: items }),
      });
    });
  });

  // --- Chat with the meeting ---
  const chatBox = document.getElementById("chatBox");
  const chatInput = document.getElementById("chatInput");
  const chatSend = document.getElementById("chatSend");
  let chatHistory = [];

  function addMsg(text, who) {
    const div = document.createElement("div");
    div.className = "chat-msg " + who;
    div.textContent = text;
    chatBox.appendChild(div);
    chatBox.scrollTop = chatBox.scrollHeight;
  }

  async function sendChat() {
    const q = chatInput.value.trim();
    if (!q) return;
    addMsg(q, "user");
    chatInput.value = "";
    addMsg("Thinking...", "bot");
    const thinking = chatBox.lastChild;

    try {
      const res = await fetch("/chat/" + meetingId, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: q, history: chatHistory }),
      });
      const data = await res.json();
      thinking.textContent = data.answer || data.error || "No answer.";
      chatHistory.push({ role: "user", content: q });
      chatHistory.push({ role: "assistant", content: data.answer || "" });
    } catch (err) {
      thinking.textContent = "Error: " + err.message;
    }
  }
  chatSend.addEventListener("click", sendChat);
  chatInput.addEventListener("keypress", (e) => { if (e.key === "Enter") sendChat(); });

  // --- Follow-up email draft ---
  document.getElementById("emailBtn").addEventListener("click", async () => {
    const modal = document.getElementById("emailModal");
    const textArea = document.getElementById("emailText");
    modal.classList.remove("hidden");
    textArea.value = "Drafting email...";
    try {
      const res = await fetch("/email/" + meetingId, { method: "POST" });
      const data = await res.json();
      textArea.value = data.email || data.error || "Could not draft email.";
    } catch (err) {
      textArea.value = "Error: " + err.message;
    }
  });

  // --- Regenerate notes in another language ---
  document.getElementById("translateBtn").addEventListener("click", async () => {
    const lang = document.getElementById("notesLang").value;
    const btn = document.getElementById("translateBtn");
    btn.textContent = "Working...";
    try {
      const res = await fetch("/translate-notes/" + meetingId, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ language: lang }),
      });
      const data = await res.json();
      if (data.notes) {
        // Update the summary, key points and decisions on the page.
        document.getElementById("summaryText").textContent = data.notes.summary;
        fillList("keyPointsList", data.notes.key_points);
        fillList("decisionsList", data.notes.decisions);
      } else {
        alert(data.error || "Could not regenerate.");
      }
    } catch (err) {
      alert("Error: " + err.message);
    }
    btn.textContent = "🌐 Regenerate";
  });

  function fillList(id, items) {
    const ul = document.getElementById(id);
    ul.innerHTML = "";
    (items || []).forEach((it) => {
      const li = document.createElement("li");
      li.textContent = it;
      ul.appendChild(li);
    });
  }
}

// Small helper: read a <script type="application/json"> block by id.
function readJson(id) {
  const el = document.getElementById(id);
  if (!el) return null;
  try { return JSON.parse(el.textContent); } catch (e) { return null; }
}


// --- Insights dashboard charts ---
function initInsightsPage() {
  const data = readJson("insightsData");
  if (!data) return;

  // Pie chart of sentiment across all meetings.
  const pie = document.getElementById("sentimentPie");
  if (pie && window.Chart) {
    new Chart(pie, {
      type: "pie",
      data: {
        labels: Object.keys(data.sentiment),
        datasets: [{
          data: Object.values(data.sentiment),
          backgroundColor: ["#2f9e44", "#f08c00", "#e03131"], // pos/neutral/neg
        }],
      },
      options: { plugins: { legend: { position: "bottom" } } },
    });
  }

  // Line chart of meetings over time.
  const trend = document.getElementById("trendChart");
  if (trend && window.Chart && Array.isArray(data.trend)) {
    new Chart(trend, {
      type: "line",
      data: {
        labels: data.trend.map((t) => t[0]),
        datasets: [{
          label: "Meetings",
          data: data.trend.map((t) => t[1]),
          borderColor: "#5c7cfa",
          backgroundColor: "rgba(92,124,250,0.15)",
          fill: true,
          tension: 0.3,
        }],
      },
      options: { scales: { y: { beginAtZero: true, ticks: { precision: 0 } } } },
    });
  }
}


// --- AI assistant page (answers across all meetings) ---
function initAssistantPage() {
  const box = document.getElementById("assistantBox");
  const input = document.getElementById("assistantInput");
  const send = document.getElementById("assistantSend");

  function addMsg(text, who) {
    const div = document.createElement("div");
    div.className = "chat-msg " + who;
    div.textContent = text;
    box.appendChild(div);
    box.scrollTop = box.scrollHeight;
  }

  async function ask() {
    const q = input.value.trim();
    if (!q) return;
    addMsg(q, "user");
    input.value = "";
    addMsg("Thinking across your meetings...", "bot");
    const thinking = box.lastChild;
    try {
      const res = await fetch("/assistant/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: q }),
      });
      const data = await res.json();
      thinking.textContent = data.answer || data.error || "No answer.";
    } catch (err) {
      thinking.textContent = "Error: " + err.message;
    }
  }
  send.addEventListener("click", ask);
  input.addEventListener("keypress", (e) => { if (e.key === "Enter") ask(); });
}


// Email modal helpers (called from inline buttons in results.html)
function closeEmail() { document.getElementById("emailModal").classList.add("hidden"); }
function copyEmail() {
  const t = document.getElementById("emailText");
  t.select();
  document.execCommand("copy");
  alert("Email copied to clipboard!");
}
