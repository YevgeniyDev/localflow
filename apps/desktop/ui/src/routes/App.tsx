import React, { useEffect, useMemo, useState } from "react";
import {
  chat,
  updateDraft,
  approveDraft,
  execute,
  listConversations,
  getConversation,
  ConversationListItem,
  ConversationDetailOut,
} from "../lib/api";

type ChatMsg = { role: "user" | "assistant"; content: string };

function safeString(x: any): string {
  return typeof x === "string" ? x : x == null ? "" : String(x);
}

function toChatRole(role: string): "user" | "assistant" {
  const r = (role || "").toLowerCase();
  return r === "user" ? "user" : "assistant";
}

function isTitlelessIntent(userText: string): boolean {
  const text = (userText || "").toLowerCase();
  return /\b(linkedin|tweet|x post|caption)\b/.test(text);
}

function inferNeedsTitleInput(userText: string): boolean {
  const text = (userText || "").toLowerCase();
  if (/\b(email|mail|subject|cover letter|letter)\b/.test(text)) return true;
  return false;
}

export function App() {
  const [msg, setMsg] = useState("");

  const [chatLog, setChatLog] = useState<ChatMsg[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [convId, setConvId] = useState<string | undefined>();
  const [draftId, setDraftId] = useState<string | undefined>();
  const [draftTitle, setDraftTitle] = useState("");
  const [draftBody, setDraftBody] = useState("");

  const [approvalId, setApprovalId] = useState<string | undefined>();
  const [toolPlan, setToolPlan] = useState<any>(null);
  const [showDraftStudio, setShowDraftStudio] = useState(false);
  const [needsTitleInput, setNeedsTitleInput] = useState(false);

  const [history, setHistory] = useState<ConversationListItem[]>([]);
  const [historyBusy, setHistoryBusy] = useState(false);

  const canSend = useMemo(() => !busy && msg.trim().length > 0, [busy, msg]);
  const canApprove = useMemo(() => !busy && !!draftId, [busy, draftId]);
  const canExecute = useMemo(() => !busy && !!approvalId, [busy, approvalId]);

  async function refreshHistory() {
    setErr(null);
    setHistoryBusy(true);
    try {
      const out = await listConversations(50, 0);
      setHistory(out.items ?? []);
    } catch (e: any) {
      setErr(String(e?.message ?? e));
    } finally {
      setHistoryBusy(false);
    }
  }

  async function loadConversation(conversationId: string) {
    setErr(null);
    setBusy(true);
    try {
      const out: ConversationDetailOut = await getConversation(conversationId);
      setConvId(out.id);

      const msgs = (out.messages ?? []).map((m) => ({
        role: toChatRole(safeString(m.role)),
        content: safeString(m.content),
      }));
      setChatLog(msgs);

      if (out.latest_draft) {
        const lastUserMessage =
          [...(out.messages ?? [])]
            .reverse()
            .find((m) => toChatRole(safeString(m.role)) === "user")?.content ?? "";
        setDraftId(out.latest_draft.id);
        setDraftTitle(out.latest_draft.title ?? "");
        setDraftBody(out.latest_draft.content ?? "");
        const titleless = isTitlelessIntent(lastUserMessage);
        setNeedsTitleInput(
          !titleless &&
            (!!(out.latest_draft.title ?? "").trim() || inferNeedsTitleInput(lastUserMessage)),
        );
        setShowDraftStudio(true);
      } else {
        setDraftId(undefined);
        setDraftTitle("");
        setDraftBody("");
        setNeedsTitleInput(false);
        setShowDraftStudio(false);
      }

      setApprovalId(undefined);
      setToolPlan(null);
    } catch (e: any) {
      setErr(String(e?.message ?? e));
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    refreshHistory();
  }, []);

  function onNewChat() {
    setErr(null);
    setConvId(undefined);
    setChatLog([]);
    setMsg("");
    setDraftId(undefined);
    setDraftTitle("");
    setDraftBody("");
    setApprovalId(undefined);
    setToolPlan(null);
    setNeedsTitleInput(false);
    setShowDraftStudio(false);
  }

  async function onSend() {
    setErr(null);
    setBusy(true);
    try {
      const userText = msg.trim();
      const needsTitleFromPrompt = inferNeedsTitleInput(userText);
      const titleless = isTitlelessIntent(userText);
      setChatLog((prev) => [...prev, { role: "user", content: userText }]);

      const out = await chat(userText, convId);

      setConvId(out.conversation_id);
      setDraftId(out.draft.id);
      setDraftTitle(out.draft.title ?? "");
      setDraftBody(out.draft.content ?? "");
      setNeedsTitleInput(!titleless && (!!(out.draft.title ?? "").trim() || needsTitleFromPrompt));
      setShowDraftStudio(true);

      setToolPlan(out.tool_plan);
      setApprovalId(undefined);

      const assistantText = out.assistant_message ?? "";
      if (assistantText) {
        setChatLog((prev) => [...prev, { role: "assistant", content: assistantText }]);
      }

      setMsg("");
      refreshHistory();
    } catch (e: any) {
      setErr(String(e?.message ?? e));
    } finally {
      setBusy(false);
    }
  }

  async function onApprove() {
    if (!draftId) return;
    setErr(null);
    setBusy(true);
    try {
      await updateDraft(draftId, draftTitle, draftBody);
      const out = await approveDraft(draftId);
      setApprovalId(out.approval_id);
      refreshHistory();
    } catch (e: any) {
      setErr(String(e?.message ?? e));
    } finally {
      setBusy(false);
    }
  }

  async function onExecuteOpenLinks() {
    if (!approvalId) return;
    setErr(null);
    setBusy(true);
    try {
      const urls = (toolPlan?.actions ?? [])
        .filter((a: any) => a.tool === "open_links")
        .flatMap((a: any) => a.params?.urls ?? []);

      if (!urls.length) {
        setErr("No open_links URLs in tool plan.");
        return;
      }
      await execute(approvalId, "open_links", { urls });
    } catch (e: any) {
      setErr(String(e?.message ?? e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: showDraftStudio
          ? "320px minmax(0, 1.4fr) minmax(0, 1fr)"
          : "320px minmax(0, 1fr)",
        height: "100vh",
        gap: 12,
        padding: 12,
      }}
    >
      <div
        style={{
          border: "1px solid #333",
          borderRadius: 10,
          padding: 12,
          display: "flex",
          flexDirection: "column",
          overflow: "hidden",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <h3 style={{ marginTop: 0, marginBottom: 0 }}>History</h3>
          <button onClick={onNewChat} disabled={busy}>
            New Chat
          </button>
          <button
            onClick={refreshHistory}
            disabled={historyBusy || busy}
            style={{ marginLeft: "auto" }}
          >
            Refresh
          </button>
        </div>

        <div
          style={{
            marginTop: 10,
            border: "1px solid #bbb",
            borderRadius: 8,
            padding: 10,
            flex: 1,
            overflowY: "auto",
          }}
        >
          {historyBusy && <div style={{ opacity: 0.7 }}>Loading...</div>}

          {!historyBusy && history.length === 0 && (
            <div style={{ opacity: 0.7 }}>No conversations yet.</div>
          )}

          {!historyBusy &&
            history.map((c) => {
              const active = !!convId && c.id === convId;
              return (
                <button
                  key={c.id}
                  onClick={() => loadConversation(c.id)}
                  disabled={busy}
                  style={{
                    width: "100%",
                    textAlign: "left",
                    padding: 10,
                    marginBottom: 8,
                    borderRadius: 10,
                    border: active ? "2px solid #333" : "1px solid #ccc",
                    background: active ? "#f2f2f2" : "white",
                    cursor: "pointer",
                  }}
                  title={c.id}
                >
                  <div style={{ fontWeight: 800, marginBottom: 4 }}>
                    {c.title || "Conversation"}
                  </div>
                  <div style={{ fontSize: 12, opacity: 0.8, marginBottom: 6 }}>
                    {c.message_count} messages
                  </div>
                  <div style={{ fontSize: 12, opacity: 0.85, whiteSpace: "pre-wrap" }}>
                    {c.last_message_preview}
                  </div>
                </button>
              );
            })}
        </div>

        <div style={{ marginTop: 8, fontSize: 12, opacity: 0.85 }}>
          Active: {convId ?? "(none)"}
        </div>
      </div>

      <div
        style={{
          border: "1px solid #333",
          borderRadius: 10,
          padding: 12,
          display: "flex",
          flexDirection: "column",
        }}
      >
        <h3 style={{ marginTop: 0 }}>Chat</h3>

        <div style={{ display: "flex", gap: 8 }}>
          <input
            style={{ flex: 1 }}
            value={msg}
            onChange={(e) => setMsg(e.target.value)}
            placeholder="Ask LocalFlow..."
            disabled={busy}
            onKeyDown={(e) => {
              if (e.key === "Enter") onSend();
            }}
          />
          <button onClick={onSend} disabled={!canSend}>
            Send
          </button>
        </div>

        {err && (
          <div style={{ marginTop: 10, color: "crimson", whiteSpace: "pre-wrap" }}>
            <b>Error:</b> {err}
          </div>
        )}

        <div
          style={{
            marginTop: 10,
            border: "1px solid #bbb",
            borderRadius: 8,
            padding: 10,
            flex: 1,
            overflowY: "auto",
          }}
        >
          {chatLog.length === 0 ? (
            <div style={{ opacity: 0.7 }}>No messages yet.</div>
          ) : (
            chatLog.map((m, idx) => (
              <div key={idx} style={{ marginBottom: 10 }}>
                <div style={{ fontWeight: 700 }}>
                  {m.role === "user" ? "You" : "Assistant"}
                </div>
                <div style={{ whiteSpace: "pre-wrap" }}>{m.content}</div>
              </div>
            ))
          )}
        </div>
      </div>

      {showDraftStudio && (
        <div
          style={{
            border: "1px solid #333",
            borderRadius: 10,
            padding: 12,
            display: "flex",
            flexDirection: "column",
          }}
        >
          <h3 style={{ marginTop: 0 }}>Draft Studio</h3>

          {needsTitleInput && (
            <div style={{ marginBottom: 8 }}>
              <div style={{ fontWeight: 700, marginBottom: 4 }}>Title</div>
              <input
                style={{ width: "100%" }}
                value={draftTitle}
                onChange={(e) => setDraftTitle(e.target.value)}
                placeholder="Title..."
              />
            </div>
          )}

          <div style={{ flex: 1, display: "flex", flexDirection: "column" }}>
            <div style={{ fontWeight: 700, marginBottom: 4 }}>Content</div>
            <textarea
              style={{ width: "100%", flex: 1 }}
              value={draftBody}
              onChange={(e) => setDraftBody(e.target.value)}
              placeholder="Draft content..."
            />
          </div>

          <div
            style={{
              display: "flex",
              gap: 8,
              marginTop: 8,
              alignItems: "center",
            }}
          >
            <button onClick={onApprove} disabled={!canApprove}>
              Approve
            </button>
            <button onClick={onExecuteOpenLinks} disabled={!canExecute}>
              Execute: open links
            </button>

            <div style={{ marginLeft: "auto", fontSize: 12, opacity: 0.85 }}>
              {approvalId ? (
                <span style={{ color: "green", fontWeight: 700 }}>
                  Approved (hash locked)
                </span>
              ) : (
                <span style={{ color: "#555" }}>Not approved</span>
              )}
            </div>
          </div>

          <pre style={{ marginTop: 8, fontSize: 12, opacity: 0.85 }}>
            draftId: {draftId ?? "(none)"}
            {"\n"}
            approvalId: {approvalId ?? "(none)"}
            {"\n"}
            toolPlan: {JSON.stringify(toolPlan, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}
