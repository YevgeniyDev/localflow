import React, { useState } from "react";
import { chat, updateDraft, approveDraft } from "../lib/api";

export function Overlay() {
  const [mode] = useState("email");
  const [msg, setMsg] = useState("");
  const [convId, setConvId] = useState<string | undefined>();
  const [draftId, setDraftId] = useState<string | undefined>();
  const [draft, setDraft] = useState("");
  const [approvalId, setApprovalId] = useState<string | undefined>();

  async function onSend() {
    const out = await chat(mode, msg, convId);
    setConvId(out.conversation_id);
    setDraftId(out.draft.id);
    setDraft(out.draft.content);
    setApprovalId(undefined);
    setMsg("");
  }

  async function onApprove() {
    if (!draftId) return;
    await updateDraft(draftId, draft);
    const out = await approveDraft(draftId);
    setApprovalId(out.approval_id);
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
      }}
    >
      {/* In Tauri, you can use data-tauri-drag-region for draggable zones */}
      <div
        data-tauri-drag-region
        style={{ fontWeight: 700, marginBottom: 8, cursor: "move" }}
      >
        LocalFlow Overlay
      </div>

      <div style={{ display: "flex", gap: 6 }}>
        <input
          style={{ flex: 1 }}
          value={msg}
          onChange={(e) => setMsg(e.target.value)}
          placeholder="Quick ask…"
        />
        <button onClick={onSend} disabled={!msg.trim()}>
          ↵
        </button>
      </div>

      <textarea
        style={{
          width: "100%",
          height: "70vh",
          marginTop: 8,
          background: "rgba(0,0,0,0.25)",
          color: "white",
        }}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
      />

      <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
        <button onClick={onApprove} disabled={!draftId}>
          Approve ✅
        </button>
        <div style={{ fontSize: 12, opacity: 0.9, alignSelf: "center" }}>
          {approvalId ? "Approved" : "Not approved"}
        </div>
      </div>
    </div>
  );
}
