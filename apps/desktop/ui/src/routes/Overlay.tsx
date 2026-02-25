import React, { useState } from "react";
import { approveDraft, chat, updateDraft } from "../lib/api";

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
    <div className="overlay-shell">
      <div className="overlay-title" data-tauri-drag-region>
        LocalFlow Overlay
      </div>

      <div className="overlay-row">
        <input
          className="overlay-input"
          value={msg}
          onChange={(e) => setMsg(e.target.value)}
          placeholder="Quick ask..."
          disabled={busy}
          onKeyDown={(e) => {
            if (e.key === "Enter") onSend();
          }}
        />
        <button className="btn btn-primary" onClick={onSend} disabled={busy || !msg.trim()}>
          Send
        </button>
      </div>

      {err && (
        <div className="error-banner" style={{ margin: 0 }}>
          <b>Error:</b> {err}
        </div>
      )}

      <div>
        <div className="label" style={{ color: "#f6fbfc" }}>
          Title
        </div>
        <input
          className="overlay-input"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Title..."
          disabled={busy}
        />
      </div>

      <textarea
        className="overlay-area"
        value={content}
        onChange={(e) => setContent(e.target.value)}
        placeholder="Draft..."
        disabled={busy}
      />

      <div className="overlay-footer">
        <button className="btn btn-accent" onClick={onApprove} disabled={busy || !draftId}>
          Approve
        </button>
        <div className={`status-pill ${approvalId ? "status-pill--ok" : ""}`}>
          {approvalId ? "Approved" : "Not approved"}
        </div>
      </div>
    </div>
  );
}
