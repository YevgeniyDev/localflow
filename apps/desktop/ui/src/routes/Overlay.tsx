import React, { useState } from "react";
import { chat, updateDraft, approveDraft } from "../lib/api";

export function Overlay() {
  const [msg, setMsg] = useState("");
  const [convId, setConvId] = useState<string | undefined>();
  const [draftId, setDraftId] = useState<string | undefined>();

  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");

  const [approvalId, setApprovalId] = useState<string | undefined>();
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSend() {
    setErr(null);
    setBusy(true);
    try {
      const out = await chat(msg.trim(), convId);
      setConvId(out.conversation_id);
      setDraftId(out.draft.id);
      setTitle(out.draft.title ?? "");
      setContent(out.draft.content ?? "");
      setApprovalId(undefined);
      setMsg("");
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
      await updateDraft(draftId, title, content);
      const out = await approveDraft(draftId);
      setApprovalId(out.approval_id);
    } catch (e: any) {
      setErr(String(e?.message ?? e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      style={{
        height: "100vh",
        padding: 10,
        background: "rgba(20,20,20,0.55)",
        borderRadius: 14,
        border: "1px solid rgba(255,255,255,0.15)",
        backdropFilter: "blur(8px)",
        color: "white",
        display: "flex",
        flexDirection: "column",
        gap: 8,
      }}
    >
      <div data-tauri-drag-region style={{ fontWeight: 800, cursor: "move" }}>
        LocalFlow Overlay
      </div>

      <div style={{ display: "flex", gap: 6 }}>
        <input
          style={{ flex: 1 }}
          value={msg}
          onChange={(e) => setMsg(e.target.value)}
          placeholder="Quick ask…"
          disabled={busy}
          onKeyDown={(e) => {
            if (e.key === "Enter") onSend();
          }}
        />
        <button onClick={onSend} disabled={busy || !msg.trim()}>
          ↵
        </button>
      </div>

      {err && (
        <div style={{ color: "#ff8a8a", whiteSpace: "pre-wrap" }}>
          <b>Error:</b> {err}
        </div>
      )}

      <div>
        <div style={{ fontWeight: 700, marginBottom: 4 }}>Title</div>
        <input
          style={{ width: "100%" }}
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Title…"
          disabled={busy}
        />
      </div>

      <textarea
        style={{
          width: "100%",
          flex: 1,
          background: "rgba(0,0,0,0.25)",
          color: "white",
          borderRadius: 8,
        }}
        value={content}
        onChange={(e) => setContent(e.target.value)}
        placeholder="Draft…"
        disabled={busy}
      />

      <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
        <button onClick={onApprove} disabled={busy || !draftId}>
          Approve ✅
        </button>

        <div style={{ fontSize: 12, opacity: 0.9 }}>
          {approvalId ? (
            <span style={{ color: "#7CFF7C" }}>Approved</span>
          ) : (
            "Not approved"
          )}
        </div>
      </div>
    </div>
  );
}
