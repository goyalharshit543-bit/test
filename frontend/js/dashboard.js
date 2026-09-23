/* ════════════════════════════════════════════════════════════
   SkyCart Command Center
   Map: Google Maps (if GOOGLE_MAPS_API_KEY is set in .env)
        with an automatic OpenStreetMap/Leaflet fallback.
   ════════════════════════════════════════════════════════════ */
"use strict";

const STATUS_COLORS = {
  IDLE: "#22c55e", CHARGING: "#f59e0b", LOADING: "#a855f7",
  EN_ROUTE: "#3b82f6", DELIVERING: "#06b6d4", RETURNING: "#f97316",
  PENDING: "#94a3b8", ASSIGNED: "#8b5cf6", IN_TRANSIT: "#3b82f6",
  DELIVERED: "#22c55e", ON_HOLD: "#eab308", CANCELLED: "#ef4444",
};

const state = {
  user: null,
  config: null,
  drones: [],
  orders: [],
  users: [],
  map: null,
  picked: null,          // {lat,lng} chosen for a new order
  pickMarker: null,
  chatHistory: [],
  ws: null,
  wsRetry: 0,
  placeHits: [],
  placeSeq: 0,
};

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

/* ── tiny UI helpers ─────────────────────────────────────── */
function toast(msg, isError = false) {
  const el = document.createElement("div");
  el.className = "toast" + (isError ? " err" : "");
  el.textContent = msg;
  $("#toasts").appendChild(el);
  setTimeout(() => el.remove(), 4200);
}

function badge(status) {
  return `<span class="badge ${status}">${status.replace("_", " ")}</span>`;
}

function fmtTime(iso) {
  if (!iso) return "—";
  return iso.replace("T", " ").slice(0, 16);
}

function showSection(name) {
  $$(".section").forEach((s) => s.classList.remove("active"));
  $(`#section-${name}`).classList.add("active");
  $$("#nav a").forEach((a) => a.classList.toggle("active", a.dataset.section === name));
}

/* ═══════════════ MAP ══════════════════════════════════════ */

function svgDrone(color) {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="36" height="36" viewBox="0 0 36 36">
<g stroke="${color}" stroke-width="2.2" fill="none" opacity="0.9">
<line x1="18" y1="18" x2="8" y2="8"/><line x1="18" y1="18" x2="28" y2="8"/>
<line x1="18" y1="18" x2="8" y2="28"/><line x1="18" y1="18" x2="28" y2="28"/>
<circle cx="8" cy="8" r="4.5"/><circle cx="28" cy="8" r="4.5"/>
<circle cx="8" cy="28" r="4.5"/><circle cx="28" cy="28" r="4.5"/></g>
<circle cx="18" cy="18" r="5.5" fill="${color}"/></svg>`;
  return "data:image/svg+xml;charset=UTF-8," + encodeURIComponent(svg);
}

function svgPin(color) {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="34" viewBox="0 0 24 34">
<path d="M12 0C5.4 0 0 5.4 0 12c0 8.4 12 22 12 22s12-13.6 12-22C24 5.4 18.6 0 12 0z" fill="${color}"/>
<circle cx="12" cy="12" r="4.6" fill="#fff"/></svg>`;
  return "data:image/svg+xml;charset=UTF-8," + encodeURIComponent(svg);
}

function dronePopup(d, order) {
  return `<div style="font-size:12.5px;line-height:1.6">
    <b>${d.name}</b> ${badge(d.status)}<br>
    Battery: <b>${d.battery}%</b> · Speed: ${d.speed} km/h · Alt: ${d.alt} m<br>
    Position: ${d.lat.toFixed(5)}, ${d.lng.toFixed(5)}<br>
    ${order ? `Order #${order.id}: ${order.item} → ${order.customer_name}<br>ETA: ${order.eta_min ?? "—"} min` : "No active order"}
  </div>`;
}

/* ── Google Maps adapter ─────────────────────────────────── */
class GoogleMapAdapter {
  constructor() { this.name = "Google Maps"; }

  load(center) {
    return new Promise((resolve, reject) => {
      const cbName = "__scGoogleReady";
      window[cbName] = () => {
        this.map = new google.maps.Map($("#map"), {
          center, zoom: 14, mapTypeControl: false, streetViewControl: false,
          styles: [{ elementType: "geometry", stylers: [{ color: "#1d2333" }] },
                   { elementType: "labels.text.fill", stylers: [{ color: "#8ea2c0" }] },
                   { elementType: "labels.text.stroke", stylers: [{ color: "#101828" }] }],
        });
        this.infowindow = new google.maps.InfoWindow();
        this.droneM = {}; this.orderM = {}; this.routes = {};
        this.map.addListener("click", (e) =>
          this.onClick && this.onClick(e.latLng.lat(), e.latLng.lng()));
        resolve(this);
      };
      const s = document.createElement("script");
      s.src = `https://maps.googleapis.com/maps/api/js?key=${state.config.google_maps_api_key}&callback=${cbName}`;
      s.async = true;
      s.onerror = () => reject(new Error("google maps failed to load"));
      document.head.appendChild(s);
      setTimeout(() => reject(new Error("google maps timeout")), 8000);
    });
  }

  onClickHandler(cb) { this.onClick = cb; }

  upsertDrone(d, order) {
    const color = STATUS_COLORS[d.status] || "#94a3b8";
    const pos = { lat: d.lat, lng: d.lng };
    if (this.droneM[d.id]) {
      this.droneM[d.id].setPosition(pos);
      this.droneM[d.id].setIcon({ url: svgDrone(color), scaledSize: new google.maps.Size(36, 36), anchor: new google.maps.Point(18, 18) });
    } else {
      const m = new google.maps.Marker({
        position: pos, map: this.map, title: d.name,
        icon: { url: svgDrone(color), scaledSize: new google.maps.Size(36, 36), anchor: new google.maps.Point(18, 18) }, zIndex: 50,
      });
      m.addListener("click", () => {
        this.infowindow.setContent(dronePopup(d, order));
        this.infowindow.open(this.map, m);
      });
      this.droneM[d.id] = m;
    }
  }

  upsertOrder(o) {
    if (!"SHOP PENDING ASSIGNED LOADING IN_TRANSIT DELIVERING ON_HOLD".split(" ").includes(o.status)) return;
    const pos = { lat: o.lat, lng: o.lng };
    if (this.orderM[o.id]) { this.orderM[o.id].setPosition(pos); return; }
    const m = new google.maps.Marker({
      position: pos, map: this.map, title: `Order #${o.id}`,
      icon: { url: svgPin(STATUS_COLORS[o.status] || "#ef4444"), scaledSize: new google.maps.Size(24, 34), anchor: new google.maps.Point(12, 34) },
    });
    m.addListener("click", () => this.infowindow.setContent(
      `<div style="font-size:12.5px"><b>Order #${o.id}</b> ${badge(o.status)}<br>${o.item} → ${o.customer_name}<br>${o.address || ""}</div>`));
    this.orderM[o.id] = m;
  }

  drawRoute(d, order) {
    const key = "d" + d.id;
    const flying = ["EN_ROUTE", "RETURNING", "DELIVERING"].includes(d.status);
    if (!flying || !order) {
      if (this.routes[key]) { this.routes[key].setMap(null); delete this.routes[key]; }
      return;
    }
    const dest = d.status === "RETURNING"
      ? { lat: state.config.shop.lat, lng: state.config.shop.lng }
      : { lat: order.lat, lng: order.lng };
    const path = [{ lat: d.lat, lng: d.lng }, dest];
    if (this.routes[key]) { this.routes[key].setPath(path); return; }
    this.routes[key] = new google.maps.Polyline({
      path, map: this.map, strokeColor: "#4da3ff", strokeOpacity: 0.85,
      strokeWeight: 2.5,
    });
  }

  setPickMarker(lat, lng) {
    const pos = { lat, lng };
    if (this.pickMarker) { this.pickMarker.setPosition(pos); return; }
    this.pickMarker = new google.maps.Marker({
      position: pos, map: this.map,
      icon: { url: svgPin("#ef4444"), scaledSize: new google.maps.Size(24, 34), anchor: new google.maps.Point(12, 34) }, zIndex: 60,
    });
  }

  focus(lat, lng, zoom = 16) { this.map.panTo({ lat, lng }); this.map.setZoom(zoom); }
}

/* ── Leaflet adapter (no API key needed) ─────────────────── */
class LeafletMapAdapter {
  constructor() { this.name = "OpenStreetMap (Leaflet)"; }

  async load(center) {
    const loadScript = (src) => new Promise((ok, bad) => {
      const s = document.createElement("script");
      s.src = src; s.onload = ok; s.onerror = bad; document.head.appendChild(s);
    });
    if (!window.L) {
      await loadScript("https://unpkg.com/leaflet@1.9.4/dist/leaflet.js");
      const css = document.createElement("link");
      css.rel = "stylesheet";
      css.href = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css";
      document.head.appendChild(css);
    }
    this.map = L.map("map", { zoomControl: true }).setView([center.lat, center.lng], 14);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "© OpenStreetMap contributors", maxZoom: 19,
    }).addTo(this.map);
    this.droneM = {}; this.orderM = {}; this.routes = {}; this.pickMarker = null;
    this.map.on("click", (e) => this.onClick && this.onClick(e.latlng.lat, e.latlng.lng));
    return this;
  }

  onClickHandler(cb) { this.onClick = cb; }

  upsertDrone(d, order) {
    const color = STATUS_COLORS[d.status] || "#94a3b8";
    const pos = [d.lat, d.lng];
    if (this.droneM[d.id]) {
      this.droneM[d.id].setLatLng(pos);
      this.droneM[d.id].setIcon(L.divIcon({ className: "", iconSize: [36, 36], html: `<img src="${svgDrone(color)}" width="36" height="36">` }));
      this.droneM[d.id].setPopupContent(dronePopup(d, order));
    } else {
      this.droneM[d.id] = L.marker(pos, {
        zIndexOffset: 500,
        icon: L.divIcon({ className: "", iconSize: [36, 36], html: `<img src="${svgDrone(color)}" width="36" height="36">` }),
      }).addTo(this.map).bindPopup(() => dronePopup(d, order));
    }
  }

  upsertOrder(o) {
    if (!"SHOP PENDING ASSIGNED LOADING IN_TRANSIT DELIVERING ON_HOLD".split(" ").includes(o.status)) return;
    const pos = [o.lat, o.lng];
    const icon = L.divIcon({ className: "", iconSize: [24, 34], html: `<img src="${svgPin(STATUS_COLORS[o.status] || "#ef4444")}" width="24" height="34">` });
    if (this.orderM[o.id]) { this.orderM[o.id].setLatLng(pos); return; }
    this.orderM[o.id] = L.marker(pos, { icon }).addTo(this.map)
      .bindPopup(`<div style="font-size:12.5px"><b>Order #${o.id}</b> ${badge(o.status)}<br>${o.item} → ${o.customer_name}<br>${o.address || ""}</div>`);
  }

  drawRoute(d, order) {
    const key = "d" + d.id;
    const flying = ["EN_ROUTE", "RETURNING", "DELIVERING"].includes(d.status);
    if (!flying || !order) {
      if (this.routes[key]) { this.routes[key].remove(); delete this.routes[key]; }
      return;
    }
    const dest = d.status === "RETURNING"
      ? [state.config.shop.lat, state.config.shop.lng]
      : [order.lat, order.lng];
    const pts = [[d.lat, d.lng], dest];
    if (this.routes[key]) { this.routes[key].setLatLngs(pts); return; }
    this.routes[key] = L.polyline(pts, { color: "#4da3ff", weight: 2.5, opacity: 0.85, dashArray: "7 8" }).addTo(this.map);
  }

  setPickMarker(lat, lng) {
    const pos = [lat, lng];
    if (this.pickMarker) { this.pickMarker.setLatLng(pos); return; }
    this.pickMarker = L.marker(pos, {
      icon: L.divIcon({ className: "", iconSize: [24, 34], html: `<img src="${svgPin("#ef4444")}" width="24" height="34">` }),
    }).addTo(this.map);
  }

  focus(lat, lng, zoom = 16) { this.map.setView([lat, lng], zoom); }
}

async function initMap(center) {
  if (state.config.google_maps_api_key) {
    try { return await new GoogleMapAdapter().load(center); }
    catch (e) { console.warn("Google Maps unavailable, falling back to Leaflet:", e.message); }
  }
  return await new LeafletMapAdapter().load(center);
}

/* ═══════════════ DATA FLOW ════════════════════════════════ */

function applyDrones(drones) {
  state.drones = drones;
  if (!state.map) return;
  const byId = Object.fromEntries(state.orders.map((o) => [o.id, o]));
  for (const d of drones) {
    const order = d.order_id ? byId[d.order_id] : null;
    state.map.upsertDrone(d, order);
    state.map.drawRoute(d, order);
  }
}

function applyOrders(orders) {
  state.orders = orders;
  if (state.map) for (const o of orders) state.map.upsertOrder(o);
  renderOrders();
  const active = orders.filter((o) => o.status !== "DELIVERED" && o.status !== "CANCELLED");
  $("#nav a[data-section='orders']").textContent = "";
  $("#nav a[data-section='orders']").append("📦 Orders ");
  const n = document.createElement("span");
  n.className = "chip";
  n.textContent = active.length;
  $("#nav a[data-section='orders']").appendChild(n);
}

function renderOrders() {
  const tb = $("#orders-table tbody");
  tb.innerHTML = state.orders.map((o) => `
    <tr>
      <td>${o.id}</td><td>${escapeHtml(o.item)}</td>
      <td>${escapeHtml(o.customer_name)}</td><td>${escapeHtml(o.customer_phone || "—")}</td>
      <td>${escapeHtml(o.address || `${o.lat.toFixed(4)}, ${o.lng.toFixed(4)}`)}</td>
      <td>${o.drone_name || "—"}</td><td>${badge(o.status)}</td>
      <td>${o.distance_km ?? "—"} km</td>
      <td>${o.status === "DELIVERED" ? "✅" : (o.eta_min != null ? o.eta_min + " min" : "—")}</td>
      <td>${fmtTime(o.created_at)}</td>
      <td>
        <button class="btn small ghost" data-track="${o.id}">Track</button>
        ${["DELIVERED", "CANCELLED"].includes(o.status) ? "" : `<button class="btn small danger" data-cancel="${o.id}">Cancel</button>`}
      </td>
    </tr>`).join("");

  $$("[data-track]").forEach((b) => b.onclick = () => trackOrder(+b.dataset.track));
  $$("[data-cancel]").forEach((b) => b.onclick = async () => {
    if (!confirm("Cancel this order? The drone will fly back home.")) return;
    try {
      const o = await API.post(`/api/orders/${b.dataset.cancel}/cancel`);
      toast(`Order #${o.id} cancelled`);
      refreshData();
    } catch (e) { toast(e.message, true); }
  });
}

function trackOrder(orderId) {
  const o = state.orders.find((x) => x.id === orderId);
  showSection("map");
  if (!o) return;
  const d = state.drones.find((x) => x.order_id === orderId);
  if (d) state.map.focus(d.lat, d.lng);
  else state.map.focus(o.lat, o.lng);
}

function renderDrones() {
  $("#drone-cards").innerHTML = state.drones.map((d) => {
    const order = state.orders.find((o) => o.id === d.order_id);
    const batt = Math.round(d.battery);
    const cls = batt < 25 ? "low" : batt < 55 ? "mid" : "";
    return `
    <div class="card">
      <h3>${d.name} ${badge(d.status)}</h3>
      <div class="meta">
        Model: ${d.model}<br>
        Speed: ${d.speed} km/h · Altitude: ${d.alt} m · Heading: ${d.heading}°<br>
        Position: ${d.lat.toFixed(5)}, ${d.lng.toFixed(5)}<br>
        ${order ? `Order #${order.id}: ${escapeHtml(order.item)} → ${escapeHtml(order.customer_name)}` : "No active order"}
      </div>
      <div class="batt-wrap"><div class="batt ${cls}" style="width:${batt}%"></div></div>
      <div class="meta">🔋 ${batt}% battery</div>
      <div class="actions">
        <button class="btn small" data-focus="${d.id}">Locate</button>
        ${["LOADING", "EN_ROUTE", "DELIVERING"].includes(d.status)
          ? `<button class="btn small danger" data-recall="${d.id}">Recall home</button>` : ""}
      </div>
    </div>`;
  }).join("");

  $$("[data-focus]").forEach((b) => b.onclick = () => {
    const d = state.drones.find((x) => x.id === +b.dataset.focus);
    showSection("map");
    if (d) state.map.focus(d.lat, d.lng);
  });
  $$("[data-recall]").forEach((b) => b.onclick = async () => {
    try {
      await API.post(`/api/drones/${b.dataset.recall}/recall`);
      toast("Drone returning to base");
      refreshData();
    } catch (e) { toast(e.message, true); }
  });
}

function renderUsers() {
  const tb = $("#users-table tbody");
  tb.innerHTML = state.users.map((u) => `
    <tr>
      <td>${u.id}</td><td>${escapeHtml(u.name)}</td><td>${escapeHtml(u.email)}</td>
      <td>${u.role === "admin" ? "👑 Admin" : "🏪 Shopkeeper"}</td>
      <td>${escapeHtml(u.shop_name || "—")}</td>
      <td>${u.active ? '<span class="badge DELIVERED">ACTIVE</span>' : '<span class="badge CANCELLED">DISABLED</span>'}</td>
      <td>${fmtTime(u.created_at)}</td>
      <td>${u.role === "admin" ? "" :
        `<button class="btn small ${u.active ? "danger" : ""}" data-toggle="${u.id}">${u.active ? "Disable" : "Enable"}</button>`}</td>
    </tr>`).join("");
  $$("[data-toggle]").forEach((b) => b.onclick = async () => {
    const u = state.users.find((x) => x.id === +b.dataset.toggle);
    try {
      await API.patch(`/api/users/${u.id}/active`, { active: !u.active });
      toast(`${u.name} ${u.active ? "disabled" : "enabled"}`);
      loadUsers();
    } catch (e) { toast(e.message, true); }
  });
}

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

/* ═══════════════ WEBSOCKET ════════════════════════════════ */
function connectWS() {
  if (state.ws) { try { state.ws.close(); } catch (_) {} }
  const ws = new WebSocket(wsURL("/ws"));
  state.ws = ws;
  ws.onopen = () => { state.wsRetry = 0; };
  ws.onmessage = (ev) => {
    let msg;
    try { msg = JSON.parse(ev.data); } catch (_) { return; }
    if (msg.type === "drones") {
      applyDrones(msg.drones);
      renderDrones();
    } else if (msg.type === "order" && msg.order && msg.order.id) {
      const i = state.orders.findIndex((o) => o.id === msg.order.id);
      const merged = { ...state.orders[i], ...msg.order };
      if (i >= 0) state.orders[i] = merged; else state.orders.unshift(merged);
      applyOrders(state.orders);
      if (["delivered", "created", "assigned", "on_hold"].includes(msg.event)) {
        const o = msg.order;
        if (msg.event === "delivered") toast(`📦 Order #${o.id} delivered to ${o.customer_name}!`);
        if (msg.event === "on_hold") toast(`⚠️ Order #${o.id} on hold — drone low battery / recalled`, true);
      }
    }
  };
  ws.onclose = () => {
    state.wsRetry = Math.min(state.wsRetry + 1, 6);
    setTimeout(connectWS, 1000 * state.wsRetry);
  };
}

/* ═══════════════ AI CHAT ══════════════════════════════════ */
function addBubble(role, text, engine) {
  const div = document.createElement("div");
  div.className = "bubble " + (role === "user" ? "me" : "bot");
  div.textContent = text;
  if (engine && role !== "user") {
    const e = document.createElement("span");
    e.className = "engine";
    e.textContent = "🤖 " + engine;
    div.appendChild(e);
  }
  $("#chat-log").appendChild(div);
  $("#chat-log").scrollTop = $("#chat-log").scrollHeight;
  return div;
}

async function sendChat(text) {
  addBubble("user", text);
  state.chatHistory.push({ role: "user", content: text });
  const typing = addBubble("bot", "SkyBot is thinking…", "");
  typing.classList.add("typing");
  try {
    const res = await API.post("/api/ai/chat", {
      message: text,
      history: state.chatHistory.slice(-6),
    });
    typing.remove();
    addBubble("bot", res.reply, res.engine);
    state.chatHistory.push({ role: "assistant", content: res.reply });
    refreshData();
  } catch (e) {
    typing.remove();
    addBubble("bot", "⚠️ " + e.message, "");
  }
}

/* ═══════════════ MODALS & FORMS ═══════════════════════════ */
function openModal(id) { $(id).classList.remove("hidden"); }
function closeModal(id) { $(id).classList.add("hidden"); }
$$("[data-close]").forEach((b) => b.onclick = () => b.closest(".modal").classList.add("hidden"));

/* ── place picker: type a name OR click the map ─────────── */
function showChosen(label) {
  const box = $("#place-chosen");
  if (!label) { box.classList.add("hidden"); return; }
  box.textContent = "📍 " + label;
  box.classList.remove("hidden");
}

function setPicked(lat, lng, label) {
  state.picked = { lat, lng };
  $("#lat-in").value = lat.toFixed(6);
  $("#lng-in").value = lng.toFixed(6);
  state.map.setPickMarker(lat, lng);
  state.map.focus(lat, lng, 16);
  showChosen(label || `${lat.toFixed(5)}, ${lng.toFixed(5)}`);
}

function hideSuggestions() { $("#place-suggestions").classList.add("hidden"); }

async function placeSearch(q) {
  const seq = ++state.placeSeq;
  try {
    const hits = await API.get("/api/geocode/search?q=" + encodeURIComponent(q));
    if (seq !== state.placeSeq) return;               // stale response
    const box = $("#place-suggestions");
    if (!hits.length) { hideSuggestions(); return; }
    box.innerHTML = hits.map((h, i) =>
      `<div class="place-item" data-i="${i}">${escapeHtml(h.label)}</div>`).join("");
    state.placeHits = hits;
    box.classList.remove("hidden");
    $$("#place-suggestions .place-item").forEach((el) => el.onclick = () => {
      const h = state.placeHits[+el.dataset.i];
      $("#place-in").value = h.label;
      setPicked(h.lat, h.lng, h.label);
      hideSuggestions();
    });
  } catch (_) { /* network hiccup — user can still click the map */ }
}

async function reversePick(lat, lng) {
  try {
    const r = await API.post("/api/geocode/reverse", { lat, lng });
    if (!$("#place-in").value.trim()) $("#place-in").value = r.label;   // name the click
    setPicked(lat, lng, r.label);
  } catch (_) {
    setPicked(lat, lng);                               // coordinates only
  }
}

function wirePlacePicker() {
  const input = $("#place-in");
  let timer = null;
  input.addEventListener("input", () => {
    state.picked = null;                               // typed text overrides old pick
    showChosen("");
    clearTimeout(timer);
    const q = input.value.trim();
    if (q.length < 3) { hideSuggestions(); return; }
    timer = setTimeout(() => placeSearch(q), 350);
  });
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {                           // Enter picks the first hit
      const first = $("#place-suggestions .place-item");
      if (first && !$("#place-suggestions").classList.contains("hidden")) {
        e.preventDefault();
        first.click();
      }
    }
  });
  document.addEventListener("click", (e) => {
    if (!e.target.closest(".place-wrap")) hideSuggestions();
  });
}

function openOrderModal() {
  state.picked = null;
  state.placeHits = [];
  $("#order-form").reset();
  hideSuggestions();
  showChosen("");
  openModal("#modal-order");
}

async function submitOrder(e) {
  e.preventDefault();
  const f = new FormData(e.target);
  const lat = parseFloat(f.get("lat")), lng = parseFloat(f.get("lng"));
  const place = (f.get("place") || "").trim();
  const hasCoords = !isNaN(lat) && !isNaN(lng);
  if (!hasCoords && !place) {
    toast("Type a place name or click the map to set the drop location", true);
    return;
  }
  try {
    const o = await API.post("/api/orders", {
      item: f.get("item"),
      customer_name: f.get("customer_name"),
      customer_phone: f.get("customer_phone") || "",
      address: f.get("address") || "",
      place: place || null,                            // label kept even when coords are set
      lat: hasCoords ? lat : null,
      lng: hasCoords ? lng : null,
    });
    closeModal("#modal-order");
    toast(`🚀 Order #${o.id} created — ${o.drone_name || "waiting for a free drone"} · ETA ${o.eta_min} min`);
    refreshData();
    showSection("map");
  } catch (err) { toast(err.message, true); }
}

async function submitUser(e) {
  e.preventDefault();
  const f = new FormData(e.target);
  try {
    const u = await API.post("/api/users", {
      name: f.get("name"), email: f.get("email"),
      password: f.get("password"), role: f.get("role"),
      shop_name: f.get("shop_name") || "",
    });
    closeModal("#modal-user");
    toast(`✅ Access granted to ${u.name} (${u.email})`);
    loadUsers();
  } catch (err) { toast(err.message, true); }
}

async function submitDrone(e) {
  e.preventDefault();
  const f = new FormData(e.target);
  try {
    const d = await API.post("/api/drones", {
      name: f.get("name"), model: f.get("model") || "SkyCart X1-Pro",
    });
    closeModal("#modal-drone");
    toast(`🚁 ${d.name} added to the fleet`);
    refreshData();
  } catch (err) { toast(err.message, true); }
}

/* ═══════════════ BOOT ═════════════════════════════════════ */
async function refreshData() {
  const [drones, orders] = await Promise.all([
    API.get("/api/drones"), API.get("/api/orders"),
  ]);
  applyDrones(drones.drones);
  applyOrders(orders);
  renderDrones();
}

async function loadUsers() {
  if (state.user.role !== "admin") return;
  const res = await API.get("/api/users");
  state.users = res;
  renderUsers();
}

async function boot() {
  if (!API.token()) { location.href = "/"; return; }
  try {
    state.user = await API.get("/api/auth/me");
    state.config = await API.get("/api/config");
  } catch (e) { return; } // api.js redirects to login on 401

  // Sidebar user info + admin-only elements
  $("#side-user").innerHTML =
    `<b>${escapeHtml(state.user.name)}</b>${escapeHtml(state.user.email)}<br>${state.user.role === "admin" ? "👑 Admin" : "🏪 " + escapeHtml(state.user.shop_name || "Shopkeeper")}`;
  if (state.user.role === "admin") {
    $$(".admin-only").forEach((el) => el.classList.remove("hidden"));
  }
  $("#sim-note").textContent =
    `Map: ${state.config.google_maps_api_key ? "Google Maps" : "OpenStreetMap"} · ` +
    `Firmware: ${state.config.firmware_engine} · Sim speed ×${state.config.sim_speed}`;
  $("#ai-engine").textContent = state.config.ai_engine;

  // Map
  state.map = await initMap({ lat: state.config.shop.lat, lng: state.config.shop.lng });
  state.map.onClickHandler((lat, lng) => {
    if ($("#modal-order").classList.contains("hidden")) return;
    hideSuggestions();
    reversePick(lat, lng);                             // coords + place name automatically
  });
  state.map.focus(state.config.shop.lat, state.config.shop.lng, 14);
  state.map.upsertOrder({ id: -1, status: "SHOP", lat: state.config.shop.lat,
                          lng: state.config.shop.lng, item: "🏬 " + state.config.shop.name,
                          customer_name: state.config.shop.name, address: "Home base" });

  // Live data + websocket
  await refreshData();
  await loadUsers();
  connectWS();

  // Wire up UI
  $$("#nav a").forEach((a) => a.onclick = () => showSection(a.dataset.section));
  $("#btn-logout").onclick = () => { API.clearToken(); location.href = "/"; };
  $("#btn-recenter").onclick = () => state.map.focus(state.config.shop.lat, state.config.shop.lng, 14);
  $("#btn-create-order").onclick = openOrderModal;
  $("#btn-create-order-2").onclick = openOrderModal;
  $("#btn-add-user").onclick = () => { $("#user-form").reset(); openModal("#modal-user"); };
  $("#btn-add-drone").onclick = () => { $("#drone-form").reset(); openModal("#modal-drone"); };
  $("#order-form").onsubmit = submitOrder;
  wirePlacePicker();
  $("#user-form").onsubmit = submitUser;
  $("#drone-form").onsubmit = submitDrone;
  $("#chat-form").onsubmit = (e) => {
    e.preventDefault();
    const v = $("#chat-input").value.trim();
    if (!v) return;
    $("#chat-input").value = "";
    sendChat(v);
  };
  $$(".suggestion").forEach((b) => b.onclick = () => sendChat(b.textContent));
  addBubble("bot",
    `Hi ${state.user.name.split(" ")[0]}! I'm SkyBot 🤖 — your delivery copilot.\n` +
    `Ask me things like "where is drone 1", "show recent orders", or "create an order" ` +
    `(for that I'll need the item, customer name and the drop location — a place name works).`,
    state.config.ai_engine);

  // Safety net: if the map lib never loads, tell the user why.
  if (!state.map) toast("Map library failed to load — check your internet connection", true);
}

boot();
