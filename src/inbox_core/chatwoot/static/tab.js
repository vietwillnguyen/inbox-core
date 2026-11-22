// The inbox-core draft tab. Plain script, no dependencies, no innerHTML.
//
// Chatwoot posts this frame the conversation and the "current agent", unsigned
// and to any origin. The conversation id is used only to choose what to ask
// for; the server decides what this signed-in agent may see and do. The
// agent's identity comes from the session the server minted after checking
// their own Chatwoot token with Chatwoot.
"use strict";

(() => {
  const CHATWOOT_ORIGIN = document.documentElement.dataset.chatwootOrigin;
  const SESSION_KEY = "inbox-core-tab-session";
  const $ = (id) => document.getElementById(id);
  let conversationId = null;

  const storage = {
    get() {
      try {
        const raw = window.sessionStorage.getItem(SESSION_KEY);
        if (!raw) return null;
        const session = JSON.parse(raw);
        if (!session.token || Date.parse(session.expires_at) <= Date.now()) return null;
        return session;
      } catch (_) {
        return null;
      }
    },
    set(session) {
      try { window.sessionStorage.setItem(SESSION_KEY, JSON.stringify(session)); } catch (_) { /* private mode */ }
    },
    clear() {
      try { window.sessionStorage.removeItem(SESSION_KEY); } catch (_) { /* private mode */ }
    },
  };
  let memorySession = null;
  const session = () => storage.get() || memorySession;

  function status(text, kind) {
    const el = $("status");
    el.textContent = text || "";
    el.className = "status" + (kind ? " " + kind : "");
  }

  function show(id) {
    for (const name of ["outside", "sign-in", "drafts", "empty"]) $(name).hidden = name !== id;
  }

  function showWho() {
    const current = session();
    $("who").hidden = !current;
    $("who-name").textContent = current ? "Signed in as " + (current.agent_name || "agent " + current.agent_id) : "";
  }

  function signOut(message) {
    storage.clear();
    memorySession = null;
    showWho();
    show("sign-in");
    status(message || "", message ? "error" : "");
  }

  async function call(method, path, body) {
    const current = session();
    const headers = { Accept: "application/json" };
    if (current) headers.Authorization = "Bearer " + current.token;
    if (body !== undefined) headers["Content-Type"] = "application/json";
    const response = await fetch(path, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      credentials: "omit",
      cache: "no-store",
    });
    let data = null;
    try { data = await response.json(); } catch (_) { data = null; }
    return { ok: response.ok, status: response.status, data };
  }

  function formatWhen(iso) {
    const at = new Date(iso);
    if (Number.isNaN(at.getTime())) return "";
    return "Held " + at.toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
  }

  function label(value) {
    return String(value || "").replace(/_/g, " ");
  }

  function render(list) {
    const container = $("drafts");
    container.replaceChildren();
    if (!list.drafts.length) {
      show("empty");
      return;
    }
    for (const draft of list.drafts) container.appendChild(renderDraft(draft));
    show("drafts");
  }

  function renderDraft(draft) {
    const node = $("draft-template").content.firstElementChild.cloneNode(true);
    const field = (name) => node.querySelector(`[data-field="${name}"]`);
    field("kind").textContent = draft.kind === "holding" ? "Holding message" : "Proposed answer";
    field("when").textContent = formatWhen(draft.created_at);
    field("category").textContent = label(draft.category) || "-";
    field("tier").textContent = label(draft.tier) || "-";
    field("confidence").textContent =
      typeof draft.confidence === "number" ? Math.round(draft.confidence * 100) + "%" : "-";
    field("held").textContent = draft.held_because || "-";
    const sources = field("sources");
    for (const source of draft.sources) {
      const item = document.createElement("li");
      item.textContent = source.title ? `${source.id} ${source.title}` : source.id;
      sources.appendChild(item);
    }
    field("sources-wrap").hidden = draft.sources.length === 0;
    const text = node.querySelector("textarea");
    const textId = `draft-${draft.id}`;
    text.id = textId;
    node.querySelector(".draft__label").htmlFor = textId;
    text.value = draft.text;
    text.addEventListener("input", () => {
      field("edited").hidden = text.value.trim() === draft.text.trim();
    });
    const buttons = node.querySelectorAll("button");
    const busy = (on) => buttons.forEach((b) => { b.disabled = on; });
    node.querySelector('[data-action="send"]').addEventListener("click", async () => {
      if (!text.value.trim()) { status("A reply cannot be empty.", "error"); return; }
      busy(true);
      status("Sending...");
      const result = await call("POST", `/tab/conversations/${conversationId}/drafts/${draft.id}/send`, {
        text: text.value,
        action_token: draft.action_token,
      });
      afterAction(result, result.data && result.data.outcome === "sent_edited" ? "Sent, with your edits." : "Sent to the visitor.");
      busy(false);
    });
    node.querySelector('[data-action="discard"]').addEventListener("click", async () => {
      busy(true);
      const result = await call("POST", `/tab/conversations/${conversationId}/drafts/${draft.id}/discard`, {
        action_token: draft.action_token,
      });
      afterAction(result, "Draft discarded. Nothing was sent.");
      busy(false);
    });
    return node;
  }

  async function afterAction(result, success) {
    if (result.status === 401) { signOut("Your session ended. Sign in again."); return; }
    await load();
    if (result.ok) status(success, "ok");
    else status((result.data && result.data.error) || `That did not work (HTTP ${result.status}).`, "error");
  }

  async function load() {
    if (!conversationId) return;
    if (!session()) { showWho(); show("sign-in"); return; }
    showWho();
    const result = await call("GET", `/tab/conversations/${conversationId}/drafts`);
    if (result.status === 401) { signOut("Your session ended. Sign in again."); return; }
    if (!result.ok) {
      show("empty");
      status((result.data && result.data.error) || `Could not load drafts (HTTP ${result.status}).`, "error");
      return;
    }
    render(result.data);
  }

  $("sign-in-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const input = $("token");
    const button = $("sign-in-button");
    button.disabled = true;
    status("Checking with Chatwoot...");
    const result = await call("POST", "/tab/session", { chatwoot_token: input.value.trim() });
    input.value = "";
    button.disabled = false;
    if (!result.ok) {
      status((result.data && result.data.error) || `Sign-in failed (HTTP ${result.status}).`, "error");
      return;
    }
    const current = {
      token: result.data.session_token,
      agent_id: result.data.agent_id,
      agent_name: result.data.agent_name,
      expires_at: result.data.expires_at,
    };
    memorySession = current;
    storage.set(current);
    status("");
    await load();
  });

  $("sign-out").addEventListener("click", () => signOut(""));

  window.addEventListener("message", (event) => {
    if (event.origin !== CHATWOOT_ORIGIN || event.source !== window.parent) return;
    let message;
    try { message = JSON.parse(event.data); } catch (_) { return; }
    if (!message || message.event !== "appContext" || !message.data) return;
    const data = message.data;
    if (data.theme === "dark" || data.theme === "light") document.documentElement.dataset.theme = data.theme;
    const id = data.conversation && Number(data.conversation.id);
    if (!Number.isInteger(id) || id < 1) return;
    if (id !== conversationId) {
      conversationId = id;
      status("");
      load();
    }
  });

  if (window.parent === window) {
    show("outside");
  } else {
    show(session() ? "drafts" : "sign-in");
    showWho();
    window.parent.postMessage("chatwoot-dashboard-app:fetch-info", CHATWOOT_ORIGIN);
  }
})();
