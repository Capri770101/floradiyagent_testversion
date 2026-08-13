"use strict";

/* Flora H5 —— ChatResponse 的可视化 Renderer。
 * 严格按 engine/ui_protocol.py 的 6 种 ui 渲染：
 *   text / dialog_options / plan_card / shop_card / order_card / pay_jump
 * 与后端 /chat 同源（FastAPI 挂载于 /h5），无需跨域。
 */

const API = "/chat";
const RESET = "/chat/reset";

const messagesEl = document.getElementById("messages");
const inputEl = document.getElementById("input");
const sendBtn = document.getElementById("sendBtn");
const stageTag = document.getElementById("stageTag");
const resetBtn = document.getElementById("resetBtn");
const quickStart = document.getElementById("quickStart");

const userId = getUserId();
let sessionId = null;
let busy = false;

function getUserId() {
  let id = localStorage.getItem("flora_user_id");
  if (!id) {
    id = "u_" + Math.random().toString(36).slice(2, 10);
    localStorage.setItem("flora_user_id", id);
  }
  return id;
}

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
  );
}

/* 轻量 markdown：先转义，再把 \n 与 **加粗** 渲染出来（mock 回复带此格式）。 */
function renderText(s) {
  return esc(s)
    .replace(/\n/g, "<br>")
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
}

function scrollDown() {
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

/* ---------- 基础消息 ---------- */
function addUser(text) {
  const wrap = document.createElement("div");
  wrap.className = "msg user";
  wrap.innerHTML = '<div class="avatar">🙂</div><div class="bubble">' + esc(text) + "</div>";
  messagesEl.appendChild(wrap);
  scrollDown();
}

function addBot(text) {
  if (!text) return;
  const wrap = document.createElement("div");
  wrap.className = "msg bot";
  wrap.innerHTML = '<div class="avatar">🌸</div><div class="bubble">' + renderText(text) + "</div>";
  messagesEl.appendChild(wrap);
  scrollDown();
}

function addNote(text) {
  const n = document.createElement("div");
  n.className = "note";
  n.textContent = text;
  messagesEl.appendChild(n);
  scrollDown();
}

/* 生图结果轮询：提交后后端通常已同步生成（zhipu 等），轮询 /tasks/{id}
 * 拿到 result_url（本地 /generated/ 路径）后渲染图片卡片。
 * 兼容 dashscope 等异步 provider：轮询直到 status=done。 */
window.onImgError = function (img, taskId) {
  const card = img.closest(".img-card");
  if (card) {
    card.innerHTML =
      '<div class="img-fallback">图片加载失败，请在 /tasks/' +
      esc(taskId) +
      " 查看</div>";
  }
};

async function pollImageTask(taskId) {
  const wrap = document.createElement("div");
  wrap.className = "msg bot";
  wrap.innerHTML =
    '<div class="avatar">🌸</div><div class="bubble">' +
    '<div class="img-loading">🎨 AI 正在生成效果图，约 10–20 秒，请稍候…</div></div>';
  messagesEl.appendChild(wrap);
  scrollDown();
  let url = null;
  for (let i = 0; i < 40; i++) {
    try {
      const r = await fetch("/tasks/" + taskId);
      if (r.ok) {
        const d = await r.json();
        if (d.status === "done" && d.result_url) {
          url = d.result_url;
          break;
        }
      }
    } catch (e) {
      /* 网络抖动则重试 */
    }
    await new Promise((res) => setTimeout(res, 1500));
  }
  const bubble = wrap.querySelector(".bubble");
  if (url) {
    bubble.innerHTML =
      '<div class="img-card"><div class="img-title">🌸 AI 生成的效果图</div>' +
      '<img src="' +
      esc(url) +
      '" alt="效果图" onerror="onImgError(this,\'' +
      esc(taskId) +
      "')\"></div>";
  } else {
    bubble.innerHTML =
      '<div class="img-fallback">生图轮询超时，请稍后在 /tasks/' +
      esc(taskId) +
      " 查看</div>";
  }
  scrollDown();
}

function appendBotWidget(node) {
  const wrap = document.createElement("div");
  wrap.className = "msg bot";
  const avatar = document.createElement("div");
  avatar.className = "avatar";
  avatar.textContent = "🌸";
  const slot = document.createElement("div");
  slot.style.display = "flex";
  slot.style.flexDirection = "column";
  slot.style.gap = "8px";
  slot.appendChild(node);
  wrap.appendChild(avatar);
  wrap.appendChild(slot);
  messagesEl.appendChild(wrap);
  scrollDown();
}

function showTyping() {
  const t = document.createElement("div");
  t.className = "msg bot";
  t.id = "typing";
  t.innerHTML =
    '<div class="avatar">🌸</div><div class="bubble typing"><span></span><span></span><span></span></div>';
  messagesEl.appendChild(t);
  scrollDown();
}

function hideTyping() {
  const t = document.getElementById("typing");
  if (t) t.remove();
}

function setStage(stage) {
  if (stage) stageTag.textContent = "阶段：" + stage;
}

function hideQuickStart() {
  quickStart.style.display = "none";
}
function showQuickStart() {
  quickStart.style.display = "flex";
}

/* ---------- 卡片构件（返回 DOM 节点）---------- */
function planCard(p) {
  const card = document.createElement("div");
  card.className = "card";
  // 兼容两套字段命名：
  //  - 现有方案（商家）：price / effect_image_url / merchant_name / tags
  //  - DIY 方案：estimated_price（无 merchant、无现成图、风格在 style/substyle/scene）
  const price = p.price ?? p.estimated_price ?? "";
  const img = p.effect_image_url
    ? '<img src="' + esc(p.effect_image_url) + '" alt="" onerror="this.remove()">'
    : '<span class="ph">💐</span>';
  const merchant = p.merchant_name
    ? "🏪 " + esc(p.merchant_name)
    : (p.diy ? "🛠 DIY 定制" : "");
  const tagSource = p.tags || [p.style, p.substyle, p.scene].filter(Boolean);
  const tags = tagSource.map((t) => '<span class="tag">' + esc(t) + "</span>").join("");
  card.innerHTML =
    '<div class="card-img">' + img + "</div>" +
    '<div class="card-body">' +
    '<div class="card-title">' + esc(p.name) + "</div>" +
    (price !== "" ? '<div class="card-price">¥' + esc(price) + "</div>" : "") +
    '<div class="card-desc">' + esc(p.desc) + "</div>" +
    (merchant ? '<div class="card-meta">' + merchant + "</div>" : "") +
    (tags ? '<div class="card-meta">' + tags + "</div>" : "") +
    "</div>";
  const act = document.createElement("div");
  act.className = "card-actions";
  const btn = document.createElement("button");
  btn.className = "card-btn";
  btn.textContent = "确认此方案 →";
  btn.onclick = () => sendMessage("确认");
  act.appendChild(btn);
  card.appendChild(act);
  return card;
}

function shopCard(s) {
  const card = document.createElement("div");
  card.className = "card";
  const rating = s.rating || 0;
  const stars = "★".repeat(Math.round(rating));
  card.innerHTML =
    '<div class="card-body">' +
    '<div class="card-title">' + esc(s.name) + "</div>" +
    '<div class="card-meta">📍 ' + esc(s.distance_km) + " km　💰 " + esc(s.price_range) +
    "　" + stars + " " + esc(rating) + "</div>" +
    "</div>";
  const act = document.createElement("div");
  act.className = "card-actions";
  const btn = document.createElement("button");
  btn.className = "card-btn";
  btn.textContent = "选这家并下单 →";
  btn.onclick = () => sendMessage("确认");
  act.appendChild(btn);
  card.appendChild(act);
  return card;
}

function orderCard(data) {
  const box = document.createElement("div");
  box.className = "pay-box";
  box.innerHTML =
    '<div class="pay-title">订单详情</div>' +
    '<div style="font-size:13px">类型：' + esc(data.plan_type) + "　合计：¥" + esc(data.total_price) + "</div>" +
    '<div style="font-size:11px;color:var(--ink-soft)">订单号：' + esc(data.order_id) + "</div>";
  return box;
}

function payBox(data) {
  const wrap = document.createElement("div");
  wrap.className = "pay-box";
  const order = document.createElement("div");
  order.style.fontSize = "12px";
  order.style.color = "var(--ink-soft)";
  order.textContent = "订单号：" + (data.order_id || "-");
  const title = document.createElement("div");
  title.className = "pay-title";
  title.textContent = "订单已生成，去支付完成购买";
  const btn = document.createElement("button");
  btn.className = "pay-btn";
  btn.textContent = "去支付 💳";
  btn.onclick = () =>
    addNote(
      "（演示）支付跳转 → " + (data.page_path || "/pages/order/confirm") +
      "  params=" + JSON.stringify(data.params || {})
    );
  wrap.appendChild(title);
  wrap.appendChild(order);
  wrap.appendChild(btn);
  return wrap;
}

/* ---------- 按 ui 渲染 ---------- */
function renderUi(resp) {
  const ui = resp.ui;
  const data = resp.data || {};
  if (ui === "dialog_options") {
    const opts = data.options || [];
    const box = document.createElement("div");
    box.className = "options";
    opts.forEach((o) => {
      const b = document.createElement("button");
      b.className = "opt-btn";
      b.textContent = o.label;
      b.onclick = () => sendMessage(o.value);
      box.appendChild(b);
    });
    appendBotWidget(box);
  } else if (ui === "plan_card") {
    // 后端两条路径键名不一致：respond_to_user 用 "plan"，_derive_ui 兜底用 "plans"。
    // 防御式读取，两种都认；且可能是 list 或单个 dict，统一归一化。
    let plans = data.plans ?? data.plan;
    if (plans && !Array.isArray(plans)) plans = [plans];
    plans = plans || [];
    if (!plans.length) return;
    const box = document.createElement("div");
    box.className = "cards";
    plans.forEach((p) => box.appendChild(planCard(p)));
    appendBotWidget(box);
  } else if (ui === "shop_card") {
    let shops = data.shops;
    if (shops && !Array.isArray(shops)) shops = [shops];
    shops = shops || [];
    if (!shops.length) return;
    const box = document.createElement("div");
    box.className = "cards";
    shops.forEach((s) => box.appendChild(shopCard(s)));
    appendBotWidget(box);
  } else if (ui === "order_card") {
    appendBotWidget(orderCard(data));
  } else if (ui === "pay_jump") {
    appendBotWidget(payBox(data));
  } else {
    // text —— 若含生图任务，则轮询结果并渲染图片卡片
    if (data && data.task_id) {
      pollImageTask(data.task_id);
    }
  }
}

/* ---------- 主交互 ---------- */
async function sendMessage(text) {
  text = (text || "").trim();
  if (!text || busy) return;
  busy = true;
  sendBtn.disabled = true;
  addUser(text);
  hideQuickStart();
  showTyping();
  try {
    const resp = await fetch(API, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: userId, message: text, session_id: sessionId }),
    });
    const data = await resp.json();
    hideTyping();
    if (data && data.reply !== undefined) {
      addBot(data.reply);
      if (data.session_id) sessionId = data.session_id;
      setStage(data.stage);
      renderUi(data);
    } else if (data && data.detail) {
      addBot("⚠️ " + data.detail);
    } else {
      addBot("⚠️ 返回格式异常");
    }
  } catch (e) {
    hideTyping();
    addBot("⚠️ 请求失败：" + e.message);
  } finally {
    busy = false;
    sendBtn.disabled = false;
    inputEl.focus();
  }
}

async function reset() {
  if (busy) return;
  try {
    await fetch(RESET, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: userId }),
    });
  } catch (e) {
    /* 忽略重置失败，前端仍清空 */
  }
  sessionId = null;
  messagesEl.innerHTML = "";
  showQuickStart();
  setStage("准备就绪");
  addBot("嗨～我是 Flora 花艺智能体 🌸 想送谁、什么场合、预算多少？告诉我，帮你设计一束刚刚好的花。");
}

/* ---------- 事件绑定 ---------- */
sendBtn.addEventListener("click", () => {
  const v = inputEl.value;
  inputEl.value = "";
  sendMessage(v);
});
inputEl.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    const v = inputEl.value;
    inputEl.value = "";
    sendMessage(v);
  }
});
resetBtn.addEventListener("click", reset);
quickStart.querySelectorAll(".qs-chip").forEach((chip) => {
  chip.addEventListener("click", () => sendMessage(chip.getAttribute("data-q")));
});

/* ---------- 初始化 ---------- */
addBot("嗨～我是 Flora 花艺智能体 🌸 想送谁、什么场合、预算多少？告诉我，帮你设计一束刚刚好的花。");
inputEl.focus();
