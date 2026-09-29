const $ = (id) => document.getElementById(id);
const SCAM_LABEL = {
  digital_arrest: "Digital arrest", kyc_bank: "Bank / KYC", courier_parcel: "Courier / customs",
  task_job: "Task / job scam", investment: "Investment scam", electricity_bill: "Electricity bill",
  lottery_prize: "Lottery / prize",
};
const TACTIC_LABEL = {
  authority: "Fake authority", urgency: "Urgency", fear: "Fear / threats", secrecy: "Secrecy / isolation",
  payment_request: "Payment demand", credential_request: "OTP / PIN request", reward_lure: "Reward lure",
};
const MOVE_LABEL = {
  mishear: "Mishear", hold_on: "Hold on beta", long_story: "Long story", tech_confusion: "Tech confusion",
  fake_compliance: "Fake compliance", ask_details: "Ask their details", bad_connection: "Bad connection",
};
const INTEL_LABEL = {
  upi_ids: "UPI ID", phones: "Phone", accounts: "Bank account", ifsc: "IFSC",
  amounts: "Amount demanded", authorities: "Claimed to be", officer_names: "Name used",
};

let ws = null, recog = null, micOn = false, speaking = false;
let lastCallId = null, wasted = 0, wastedTimer = null, engaged = false;
let prevTactics = {}, prevIntel = new Set();

/* ---------- call lifecycle ---------- */

$("btn-call").onclick = () => {
  if (ws) return;
  ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/call`);
  ws.onopen = () => ws.send(JSON.stringify({ type: "start" }));
  ws.onmessage = (e) => handle(JSON.parse(e.data));
  ws.onclose = () => { ws = null; setIdle(); };
};

$("btn-end").onclick = () => ws && ws.send(JSON.stringify({ type: "end" }));

$("typer").onsubmit = (e) => {
  e.preventDefault();
  const text = $("typed").value.trim();
  if (text) sendCaller(text);
  $("typed").value = "";
};

function sendCaller(text) {
  if (!ws || ws.readyState !== 1) return;
  addMsg("caller", text);
  ws.send(JSON.stringify({ type: "caller", text }));
}

function handle(m) {
  if (m.type === "started") {
    $("transcript").innerHTML = "";
    prevTactics = {}; prevIntel = new Set(); wasted = 0; engaged = false;
    $("mode").textContent = `voice: ${m.persona_mode}`;
    ["btn-mic", "btn-end", "typed", "btn-send"].forEach((id) => ($(id).disabled = false));
    $("btn-call").disabled = true;
    lastCallId = m.call_id;
    render(m);
    startMic();
  } else if (m.type === "dadi") {
    addMsg("dadi", m.text, m.move, m.source);
    render(m);
    speak(m.text);
  } else if (m.type === "ended") {
    stopMic();
    clearInterval(wastedTimer);
    if (m.saved) {
      addSystem(`Scammer hung up after ${fmt(m.wasted_s)} with Dadi. Call saved to the scam network.`);
      $("btn-report").disabled = false;
    } else {
      addSystem("Call ended.");
    }
    ws.close();
    refreshGlobal();
  }
}

function setIdle() {
  stopMic();
  clearInterval(wastedTimer);
  ["btn-mic", "btn-end", "typed", "btn-send"].forEach((id) => ($(id).disabled = true));
  $("btn-call").disabled = false;
  setState("idle");
}

/* ---------- rendering ---------- */

function setState(state) {
  const pill = $("state-pill");
  pill.className = `pill ${state}`;
  pill.textContent = {
    idle: "idle", screening: "screening the caller…", engaged: "SCAM: Dadi is on the case",
    handoff: "looks genuine: handing to you", ended: "call ended",
  }[state] || state;
}

function render(m) {
  setState(m.state);
  const p = m.scam_prob || 0;
  $("gauge-num").textContent = `${Math.round(p * 100)}%`;
  const fill = $("gauge-fill");
  fill.style.strokeDashoffset = 267 * (1 - p);
  fill.style.stroke = p >= 0.8 ? "var(--danger)" : p >= 0.5 ? "var(--accent)" : "var(--ok)";
  $("scam-type").textContent = m.state === "handoff" ? "Genuine caller"
    : m.scam_type ? SCAM_LABEL[m.scam_type] : "Listening…";

  const types = Object.entries(m.type_probs || {}).slice(0, 4);
  $("type-bars").innerHTML = p >= 0.5 ? types.map(([k, v]) => bar(SCAM_LABEL[k] || k, v, k === m.scam_type)).join("") : "";

  const tac = m.tactics_seen || {};
  $("tactics").innerHTML = Object.keys(tac).length
    ? Object.entries(tac).sort((a, b) => b[1] - a[1]).map(([k, v]) =>
        `<span class="chip ${v !== prevTactics[k] ? "flash" : ""}">${TACTIC_LABEL[k] || k}<b>×${v}</b></span>`).join("")
    : '<span class="muted">none yet</span>';
  prevTactics = { ...tac };

  const rows = [];
  for (const [kind, vals] of Object.entries(m.intel || {})) {
    for (const v of vals) {
      const key = `${kind}:${v}`;
      rows.push(`<div class="intel-row ${prevIntel.has(key) ? "" : "flash"}"><small>${INTEL_LABEL[kind]}</small><code>${esc(v)}</code></div>`);
      prevIntel.add(key);
    }
  }
  $("intel").innerHTML = rows.join("") || '<span class="muted">nothing yet</span>';

  renderBrain(m.bandit, m.move);

  if (m.state === "engaged" && !engaged) {
    engaged = true;
    wasted = m.wasted_s || 0;
    clearInterval(wastedTimer);
    wastedTimer = setInterval(() => { wasted += 1; $("wasted").textContent = fmt(wasted); }, 1000);
  }
  if (typeof m.wasted_s === "number" && engaged) wasted = Math.max(wasted, m.wasted_s);
  $("wasted").textContent = fmt(wasted);
}

function renderBrain(stats, active) {
  if (!stats) return;
  $("brain").innerHTML = Object.entries(stats)
    .sort((a, b) => b[1].mean - a[1].mean)
    .map(([k, s]) => bar(MOVE_LABEL[k] || k, s.mean, k === active, `n=${s.n}`)).join("");
}

function bar(label, v, active, right) {
  return `<div class="bar ${active ? "active" : ""}"><span>${label}</span>
    <div class="track"><i style="width:${Math.round(v * 100)}%"></i></div>
    <span>${right ?? Math.round(v * 100) + "%"}</span></div>`;
}

function addMsg(role, text, move, source) {
  const box = $("transcript");
  box.querySelector(".empty")?.remove();
  box.querySelector(".interim")?.remove();
  const div = document.createElement("div");
  div.className = `msg ${role}`;
  const meta = role === "dadi" && move
    ? `<span class="meta">move: <b>${MOVE_LABEL[move] || move}</b>${source ? ` · ${source}` : ""}</span>` : "";
  div.innerHTML = `${role === "caller" ? highlight(esc(text)) : esc(text)}${meta}`;
  box.appendChild(div);
  box.scrollTop = box.scrollHeight;
}

function addSystem(text) {
  const div = document.createElement("div");
  div.className = "empty";
  div.style.margin = "8px auto";
  div.textContent = text;
  $("transcript").appendChild(div);
  $("transcript").scrollTop = $("transcript").scrollHeight;
}

function showInterim(text) {
  const box = $("transcript");
  let el = box.querySelector(".interim");
  if (!el) {
    el = document.createElement("div");
    el.className = "msg caller interim";
    box.appendChild(el);
  }
  el.textContent = text;
  box.scrollTop = box.scrollHeight;
}

function highlight(html) {
  return html.replace(/\b(upi|otp|pin|cvv|anydesk|teamviewer|arrest|warrant|cbi|police|customs|aadhaar|account|transfer|kyc|block|urgent|jaldi)\b/gi,
    '<span class="hl">$1</span>');
}

const esc = (s) => s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmt = (s) => `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;

/* ---------- speech in (scammer) ---------- */

const SR = window.SpeechRecognition || window.webkitSpeechRecognition;

function startMic() {
  if (!SR) {
    $("btn-mic").textContent = "🎙️ Not supported (use Chrome)";
    $("btn-mic").disabled = true;
    return;
  }
  micOn = true;
  $("btn-mic").textContent = "🎙️ Listening";
  $("btn-mic").classList.add("live");
  listen();
}

function stopMic() {
  micOn = false;
  $("btn-mic").textContent = "🎙️ Mic off";
  $("btn-mic").classList.remove("live");
  if (recog) { recog.onend = null; recog.abort(); recog = null; }
}

function listen() {
  if (!micOn || speaking || recog) return;
  recog = new SR();
  recog.lang = $("lang").value;
  recog.interimResults = true;
  recog.continuous = true;
  recog.onresult = (e) => {
    let interim = "";
    for (let i = e.resultIndex; i < e.results.length; i++) {
      const r = e.results[i];
      if (r.isFinal) sendCaller(r[0].transcript.trim());
      else interim += r[0].transcript;
    }
    if (interim) showInterim(interim);
  };
  recog.onend = () => { recog = null; if (micOn && !speaking) setTimeout(listen, 150); };
  recog.onerror = () => {};
  recog.start();
}

$("btn-mic").onclick = () => (micOn ? stopMic() : startMic());
$("lang").onchange = () => { if (recog) { recog.onend = null; recog.abort(); recog = null; listen(); } };

/* ---------- speech out (Dadi) ---------- */

let voice = null;
function pickVoice() {
  const vs = speechSynthesis.getVoices();
  voice = vs.find((v) => v.lang === "hi-IN") || vs.find((v) => v.lang === "en-IN") || vs.find((v) => /female/i.test(v.name)) || vs[0];
}
speechSynthesis.onvoiceschanged = pickVoice;
pickVoice();

function speak(text) {
  if (!("speechSynthesis" in window)) return;
  speaking = true;
  if (recog) { recog.onend = null; recog.abort(); recog = null; }   // don't transcribe Dadi herself
  const u = new SpeechSynthesisUtterance(text);
  if (voice) { u.voice = voice; u.lang = voice.lang; }
  u.rate = 0.88;
  u.pitch = 1.05;
  $("avatar").classList.add("talking");
  const done = () => { speaking = false; $("avatar").classList.remove("talking"); listen(); };
  u.onend = done;
  u.onerror = done;
  speechSynthesis.cancel();
  speechSynthesis.speak(u);
}

/* ---------- report ---------- */

let reportText = "";
$("btn-report").onclick = async () => {
  if (!lastCallId) return;
  const r = await fetch(`/api/report/${lastCallId}`);
  reportText = r.ok ? await r.text() : "No saved scam call yet: Dadi only saves calls she engaged.";
  $("report-text").textContent = reportText;
  $("report-dlg").showModal();
};
$("btn-close").onclick = () => $("report-dlg").close();
$("btn-copy").onclick = () => navigator.clipboard.writeText(reportText);
$("btn-download").onclick = () => {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([reportText], { type: "text/markdown" }));
  a.download = `dadi-report-${lastCallId}.md`;
  a.click();
};

/* ---------- global stats + network graph ---------- */

async function refreshGlobal() {
  const [status, graph] = await Promise.all([fetch("/api/status").then((r) => r.json()), fetch("/api/graph").then((r) => r.json())]);
  $("tot-wasted").textContent = `${Math.round(status.wasted_s / 60)}m`;
  $("tot-calls").textContent = status.calls;
  $("tot-ids").textContent = status.identifiers;
  $("mode").textContent ||= `voice: ${status.persona_mode}`;
  if (!ws) renderBrain(status.bandit);
  drawGraph(graph);
}

function drawGraph(data) {
  const svg = d3.select("#graph");
  svg.selectAll("*").remove();
  const { width, height } = svg.node().getBoundingClientRect();
  const color = { call: "#ffb547", UPI: "#ff5d5d", Phone: "#6aa8ff", Account: "#c77dff", IFSC: "#3ddc97" };
  const nodes = data.nodes.map((d) => ({ ...d }));
  const links = data.links.map((d) => ({ ...d }));
  const sim = d3.forceSimulation(nodes)
    .force("link", d3.forceLink(links).id((d) => d.id).distance(45))
    .force("charge", d3.forceManyBody().strength(-110))
    .force("center", d3.forceCenter(width / 2, height / 2))
    .force("x", d3.forceX(width / 2).strength(0.03))
    .force("y", d3.forceY(height / 2).strength(0.06));
  const link = svg.append("g").attr("stroke", "#3a4150").selectAll("line").data(links).join("line");
  const node = svg.append("g").selectAll("circle").data(nodes).join("circle")
    .attr("r", (d) => (d.type === "call" ? 7 : 5))
    .attr("fill", (d) => (d.type === "call" ? (d.seed ? "#7a5a2a" : color.call) : color[d.kind]))
    .attr("stroke", (d) => (d.id === lastCallId ? "#fff" : "none")).attr("stroke-width", 2)
    .call(d3.drag()
      .on("start", (e, d) => { if (!e.active) sim.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; })
      .on("drag", (e, d) => { d.fx = e.x; d.fy = e.y; })
      .on("end", (e, d) => { if (!e.active) sim.alphaTarget(0); d.fx = null; d.fy = null; }));
  node.append("title").text((d) => d.type === "call"
    ? `${d.id}${d.seed ? " (simulated)" : ""} · ${SCAM_LABEL[d.scam_type] || "?"} · ${fmt(d.wasted_s)}`
    : `${d.kind}: ${d.value}`);
  sim.on("tick", () => {
    link.attr("x1", (d) => d.source.x).attr("y1", (d) => d.source.y).attr("x2", (d) => d.target.x).attr("y2", (d) => d.target.y);
    node.attr("cx", (d) => (d.x = Math.max(8, Math.min(width - 8, d.x)))).attr("cy", (d) => (d.y = Math.max(8, Math.min(height - 8, d.y))));
  });
  const legend = Object.entries(color).map(([k, c]) => `<span class="ring"><span style="color:${c}">●</span> ${k === "call" ? "Scam call" : k}</span>`).join("");
  $("rings").innerHTML = legend + data.rings.slice(0, 4).map((r) =>
    `<span class="ring"><b>${r.ring_id}</b> ${r.n_calls} calls · ${r.shared_identifiers.slice(0, 2).map(esc).join(", ")}</span>`).join("");
}

refreshGlobal();
