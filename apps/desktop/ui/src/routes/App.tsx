import React, { useState } from "react";
import { chat, updateDraft, approveDraft, execute } from "../lib/api";

export function App() {
  const [mode, setMode] = useState("email");
  const [msg, setMsg] = useState("");
  const [convId, setConvId] = useState<string | undefined>();
  const [draftId, setDraftId] = useState<string | undefined>();
  const [draft, setDraft] = useState("");
  const [approvalId, setApprovalId] = useState<string | undefined>();
  const [toolPlan, setToolPlan] = useState<any>(null);
  const [busy, setBusy] = useState(false);

  async function onSend() {
    setBusy(true);
    try {
      const out = await chat(mode, msg, convId);
      setConvId(out.conversation_id);
      setDraftId(out.draft.id);
      setDraft(out.draft.content);
      setToolPlan(out.tool_plan);
      setApprovalId(undefined);
      setMsg("");
    } finally {
      setBusy(false);
    }
  }

  async function onApprove() {
    if (!draftId) return;
    setBusy(true);
    try {
      await updateDraft(draftId, draft);
      const out = await approveDraft(draftId);
      setApprovalId(out.approval_id);
    } finally {
      setBusy(false);
    }
  }

  async function onExecuteOpenLinks() {
    if (!approvalId) return;
    const urls = (toolPlan?.actions ?? [])
      .filter((a: any) => a.tool === "open_links")
      .flatMap((a: any) => a.params?.urls ?? []);
    if (!urls.length) return;
    setBusy(true);
    try {
      await execute(approvalId, "open_links", { urls });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "1fr 1fr",
        height: "100vh",
        gap: 12,
        padding: 12,
      }}
    >
      <div style={{ border: "1px solid #333", borderRadius: 10, padding: 12 }}>
        <h3>Chat</h3>
        <div style={{ display: "flex", gap: 8 }}>
          <select
            value={mode}
            onChange={(e) => setMode(e.target.value)}
            disabled={busy}
          >
            <option value="email">Email</option>
            <option value="routine">Routine</option>
            <option value="code">Code</option>
            <option value="linkedin">LinkedIn</option>
          </select>
          <input
            style={{ flex: 1 }}
            value={msg}
            onChange={(e) => setMsg(e.target.value)}
            placeholder="Ask LocalFlow…"
            disabled={busy}
          />
          <button onClick={onSend} disabled={busy || !msg.trim()}>
            Send
          </button>
        </div>
      </div>

      <div style={{ border: "1px solid #333", borderRadius: 10, padding: 12 }}>
        <h3>Draft Studio</h3>
        <textarea
          style={{ width: "100%", height: "60vh" }}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
        />
        <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
          <button onClick={onApprove} disabled={busy || !draftId}>
            Approve ✅
          </button>
          <button disabled={busy || !approvalId} onClick={onExecuteOpenLinks}>
            Execute: open links
          </button>
        </div>
        <pre style={{ marginTop: 8, fontSize: 12, opacity: 0.85 }}>
          approvalId: {approvalId ?? "(none)"}
          {"\n"}
          toolPlan: {JSON.stringify(toolPlan, null, 2)}
        </pre>
      </div>
    </div>
  );
}
