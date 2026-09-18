(() => {
  const $ = id => document.getElementById(id);
  const el = {
    sidebar: $("sidebar"), scrim: $("sidebar-scrim"), list: $("conversation-list"),
    listState: $("conversation-state"), newChat: $("new-chat"), messages: $("messages"),
    messageState: $("message-state"), title: $("chat-title").firstElementChild,
    input: $("input"), send: $("send-btn"), status: $("connection-status"),
    statusLabel: $("status-label"), model: $("model-select"), auth: $("auth-screen"),
    authError: $("auth-error"), login: $("login-button"), code: $("login-code"),
    panel: $("model-panel"), profiles: $("profile-list"), provider: $("profile-provider"),
    profileModel: $("profile-model"), profileKey: $("profile-key"), profileKeyLabel: $("profile-key-label"),
    profileError: $("profile-error")
  };
  let ws = null, reconnectTimer = null, waiting = false, sessionId = null;
  let selectedId = null, activeModel = false, streaming = null;

  async function request(url, options) {
    const response = await fetch(url, options);
    if (response.status === 401) { showAuth("Сессия истекла, войдите снова"); throw new Error("AUTH_REQUIRED"); }
    if (!response.ok) {
      let detail = "Операция не выполнена";
      try { detail = (await response.json()).detail || detail; } catch (_) {}
      throw new Error(detail);
    }
    return response;
  }
  function setStatus(kind, text) { el.status.className = `connection-status ${kind || ""}`; el.statusLabel.textContent = text; }
  function openMenu(open) { el.sidebar.classList.toggle("open", open); el.scrim.hidden = !open; }
  $("menu-button").onclick = () => openMenu(true); $("close-menu").onclick = () => openMenu(false); el.scrim.onclick = () => openMenu(false);
  function showAuth(message = "") { el.auth.hidden = false; el.authError.textContent = message; el.input.disabled = el.send.disabled = true; if (ws) ws.close(); }
  function hideAuth() { el.auth.hidden = true; }

  async function login() {
    el.login.disabled = true;
    try { await request("/auth/code", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({code: el.code.value.trim()}) }); hideAuth(); await bootstrap(); }
    catch (error) { if (error.message !== "AUTH_REQUIRED") el.authError.textContent = error.message; }
    finally { el.login.disabled = false; }
  }
  el.login.onclick = login; el.code.onkeydown = e => { if (e.key === "Enter") login(); };
  $("logout-button").onclick = async () => { try { await fetch("/auth/logout", {method: "POST"}); } finally { if (ws) ws.close(); showAuth("Вы вышли из аккаунта"); } };

  function renderConversations(conversations) {
    el.list.replaceChildren();
    el.listState.hidden = conversations.length > 0;
    conversations.forEach(conversation => {
      const row = document.createElement("div"); row.className = `conversation-item ${conversation.id === selectedId ? "active" : ""}`;
      const select = document.createElement("button"); select.type = "button"; select.textContent = conversation.title || "Новый чат"; select.title = select.textContent;
      select.onclick = () => selectConversation(conversation.id);
      const actions = document.createElement("span"); actions.className = "conversation-actions";
      const rename = document.createElement("button"); rename.type = "button"; rename.textContent = "✎"; rename.setAttribute("aria-label", `Переименовать ${select.textContent}`);
      rename.onclick = () => renameConversation(conversation);
      const remove = document.createElement("button"); remove.type = "button"; remove.textContent = "×"; remove.setAttribute("aria-label", `Удалить ${select.textContent}`);
      remove.onclick = () => deleteConversation(conversation);
      actions.append(rename, remove); row.append(select, actions); el.list.append(row);
    });
  }
  async function loadConversations() {
    const response = await request("/conversations"); const data = await response.json(); renderConversations(data.conversations || []); return data.conversations || [];
  }
  async function selectConversation(id) {
    if (id === selectedId && ws?.readyState === WebSocket.OPEN) { openMenu(false); return; }
    try {
      setStatus("", "Загрузка…"); if (ws) ws.close();
      await request(`/session/${encodeURIComponent(sessionId)}/conversation/${encodeURIComponent(id)}`, {method: "PUT"});
      selectedId = id; await loadConversations(); await loadHistory(); connect(); openMenu(false);
    } catch (error) { showMessageState(error.message, true); setStatus("error", "Ошибка"); }
  }
  async function createConversation() {
    try {
      if (ws) ws.close(); const response = await request("/conversations", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({title: "Новый чат"})});
      const conversation = await response.json(); selectedId = conversation.id; await loadConversations(); await loadHistory(); connect(); openMenu(false);
    } catch (error) { showMessageState(error.message, true); }
  }
  async function renameConversation(conversation) {
    const title = prompt("Название чата", conversation.title || "Новый чат"); if (!title?.trim()) return;
    try { await request(`/conversations/${conversation.id}`, {method: "PATCH", headers: {"Content-Type": "application/json"}, body: JSON.stringify({title: title.trim()})}); await loadConversations(); if (conversation.id === selectedId) el.title.textContent = title.trim(); }
    catch (error) { showMessageState(error.message, true); }
  }
  async function deleteConversation(conversation) {
    if (!confirm(`Удалить «${conversation.title || "Новый чат"}»?`)) return;
    try {
      await request(`/conversations/${conversation.id}`, {method: "DELETE"});
      if (conversation.id === selectedId) { selectedId = null; const remaining = await loadConversations(); if (remaining[0]) await selectConversation(remaining[0].id); else await createConversation(); }
      else await loadConversations();
    } catch (error) { showMessageState(error.message, true); }
  }
  function showMessageState(text, error = false) { el.messageState.hidden = false; el.messageState.textContent = text; el.messageState.className = `message-state${error ? " error-text" : ""}`; }
  function clearMessages() { el.messages.querySelectorAll(".msg-wrap,.typing").forEach(node => node.remove()); streaming = null; }
  async function loadHistory() {
    clearMessages(); showMessageState("Загрузка истории…"); const response = await request(`/conversations/${encodeURIComponent(selectedId)}/messages?limit=100`);
    const data = await response.json(); const conversation = await (await request(`/conversations/${encodeURIComponent(selectedId)}`)).json(); el.title.textContent = conversation.title || "Чат";
    (data.messages || []).forEach(message => appendBubble(message.role === "user" ? "user" : "assistant", message.content, message.status === "error"));
    if (!data.messages?.length) showMessageState("Отправьте сообщение, чтобы начать"); else el.messageState.hidden = true;
    el.messages.scrollTop = el.messages.scrollHeight;
  }

  async function loadModels() {
    const [modelsRes, profilesRes, currentRes] = await Promise.all([request("/models"), request("/model-profiles"), request("/session/model")]);
    const {models} = await modelsRes.json(), {profiles} = await profilesRes.json(), current = await currentRes.json();
    sessionId = current.session_id; activeModel = current.status !== "no_active_profile" && Boolean(current.active_model);
    el.model.replaceChildren(); const groups = [["Мои профили", profiles.map(p => [`profile:${p.id}`, `${p.display_name} (${p.provider})`])], ["Модели оператора", models.map(m => [`fallback:${m.id}`, m.label])]];
    groups.forEach(([label, options]) => { if (!options.length) return; const group = document.createElement("optgroup"); group.label = label; options.forEach(([value, text]) => { const option = new Option(text, value); group.append(option); }); el.model.append(group); });
    const profile = profiles.find(p => p.is_active); if (profile) el.model.value = `profile:${profile.id}`; else if (current.active_model) el.model.value = `fallback:${current.active_model}`;
    el.model.disabled = false; updateComposer();
  }
  function updateComposer() { const enabled = activeModel && ws?.readyState === WebSocket.OPEN && !waiting && Boolean(selectedId); el.input.disabled = !enabled; el.send.disabled = !enabled; }
  async function loadProfilePanel() {
    const [providersResponse, profilesResponse] = await Promise.all([request("/model-providers"), request("/model-profiles")]);
    const {providers} = await providersResponse.json(), {profiles} = await profilesResponse.json(); el.provider.replaceChildren();
    providers.forEach(provider => el.provider.append(new Option(provider.name, provider.id))); el.provider.onchange();
    el.profiles.replaceChildren(); profiles.forEach(profile => { const row = document.createElement("div"); row.className = "profile-row"; const name = document.createElement("span"); name.textContent = `${profile.display_name}${profile.is_active ? " — активна" : ""}`; const actions = document.createElement("span"); if (!profile.is_active) { const activate = document.createElement("button"); activate.textContent = "Включить"; activate.onclick = () => updateProfile(`/model-profiles/${profile.id}/activate`, "POST"); actions.append(activate); } const remove = document.createElement("button"); remove.textContent = "Удалить"; remove.onclick = () => updateProfile(`/model-profiles/${profile.id}`, "DELETE"); actions.append(remove); row.append(name, actions); el.profiles.append(row); });
  }
  async function updateProfile(url, method) { try { await request(url, {method}); await loadProfilePanel(); await loadModels(); } catch (error) { el.profileError.textContent = error.message; } }
  $("manage-models").onclick = async () => { el.panel.hidden = false; el.profileError.textContent = ""; try { await loadProfilePanel(); } catch (error) { el.profileError.textContent = error.message; } };
  $("profile-close").onclick = () => { el.panel.hidden = true; };
  el.provider.onchange = () => { const ollama = el.provider.value === "ollama"; el.profileKey.hidden = el.profileKeyLabel.hidden = ollama; };
  $("profile-save").onclick = async () => { const modelName = el.profileModel.value.trim(), provider = el.provider.value; if (!modelName || (provider !== "ollama" && !el.profileKey.value.trim())) { el.profileError.textContent = "Укажите модель и API-ключ"; return; } try { await request("/model-profiles", {method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify({provider, model_name:modelName, display_name:modelName, api_key:el.profileKey.value || null})}); el.profileModel.value = el.profileKey.value = ""; await loadProfilePanel(); await loadModels(); } catch (error) { el.profileError.textContent = error.message; } };
  el.model.onchange = async () => { const value = el.model.value; el.model.disabled = true; try { if (value.startsWith("profile:")) await request(`/model-profiles/${value.slice(8)}/activate`, {method:"POST"}); else await request("/session/model", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({model_id:value.slice(9)})}); await loadModels(); } catch (error) { el.profileError.textContent = error.message; } finally { el.model.disabled = false; } };

  function connect() {
    if (!selectedId) return; clearTimeout(reconnectTimer); setStatus("", "Подключение…"); const proto = location.protocol === "https:" ? "wss" : "ws"; ws = new WebSocket(`${proto}://${location.host}/ws`);
    ws.onopen = () => { setStatus("connected", "Подключено"); updateComposer(); el.input.focus(); };
    ws.onclose = event => { setStatus(event.code === 1008 ? "error" : "", event.code === 1008 ? "Сессия истекла" : "Переподключение…"); updateComposer(); if (event.code === 1008) showAuth("Сессия истекла, войдите снова"); else { clearTimeout(reconnectTimer); reconnectTimer = setTimeout(connect, 2000); } };
    ws.onerror = () => ws.close();
    ws.onmessage = event => { const message = JSON.parse(event.data); if (message.type === "chunk") return appendChunk(message.content); removeTyping(); waiting = false; if (message.type === "message") finalizeStreaming(message.content); else if (message.type === "error") { if (message.code === "NO_ACTIVE_MODEL") activeModel = false; discardStreaming(); appendBubble("assistant", message.content, true); } updateComposer(); };
  }
  function appendBubble(role, content, error = false) { el.messageState.hidden = true; const wrap = document.createElement("div"); wrap.className = `msg-wrap ${role}`; const bubble = document.createElement("div"); bubble.className = `bubble${error ? " error" : ""}`; if (role === "user") bubble.textContent = content; else bubble.innerHTML = content; wrap.append(bubble); el.messages.append(wrap); return wrap; }
  function appendChunk(chunk) { if (!streaming) { removeTyping(); streaming = {wrap: appendBubble("assistant", ""), bubble: null, text:""}; streaming.bubble = streaming.wrap.querySelector(".bubble"); streaming.bubble.innerHTML = ""; } streaming.text += chunk; streaming.bubble.textContent = streaming.text; el.messages.scrollTop = el.messages.scrollHeight; }
  function finalizeStreaming(content) { if (streaming) { streaming.bubble.innerHTML = content; streaming = null; } else appendBubble("assistant", content); el.messages.scrollTop = el.messages.scrollHeight; }
  function discardStreaming() { streaming?.wrap.remove(); streaming = null; } function removeTyping() { $("typing-indicator")?.remove(); }
  function showTyping() { removeTyping(); const wrap = appendBubble("assistant", "…"); wrap.id = "typing-indicator"; wrap.classList.add("typing"); }
  function sendMessage() { const text = el.input.value.trim(); if (!text || !ws || ws.readyState !== WebSocket.OPEN || waiting) return; appendBubble("user", text); ws.send(text); el.input.value = ""; el.input.style.height = "auto"; waiting = true; updateComposer(); showTyping(); }
  el.send.onclick = sendMessage; el.input.onkeydown = event => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); sendMessage(); } }; el.input.oninput = () => { el.input.style.height = "auto"; el.input.style.height = `${Math.min(el.input.scrollHeight, 150)}px`; };

  async function bootstrap() {
    try {
      setStatus("", "Загрузка…"); await loadModels(); const conversations = await loadConversations(); const selected = await (await request(`/session/${encodeURIComponent(sessionId)}/conversation`)).json(); selectedId = selected.conversation_id;
      if (!selectedId || !conversations.some(conversation => conversation.id === selectedId)) { selectedId = conversations[0]?.id; if (selectedId) await request(`/session/${encodeURIComponent(sessionId)}/conversation/${encodeURIComponent(selectedId)}`, {method:"PUT"}); else { await createConversation(); return; } }
      await loadHistory(); connect();
    } catch (error) { if (error.message !== "AUTH_REQUIRED") showMessageState("Не удалось загрузить чаты. Попробуйте обновить.", true); }
  }
  $("new-chat").onclick = createConversation;
  fetch("/auth/me").then(response => { if (response.ok) { hideAuth(); bootstrap(); } }).catch(() => {});
})();
