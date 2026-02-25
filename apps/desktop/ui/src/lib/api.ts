const BASE = "http://127.0.0.1:7878/v1";

export async function chat(
  mode: string,
  message: string,
  conversationId?: string,
) {
  const r = await fetch(`${BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      mode,
      message,
      conversation_id: conversationId ?? null,
    }),
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

export async function updateDraft(draftId: string, content: string) {
  const r = await fetch(`${BASE}/drafts/${draftId}/update`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content }),
  });
  if (!r.ok) throw new Error(await r.text());
}

export async function approveDraft(draftId: string) {
  const r = await fetch(`${BASE}/drafts/${draftId}/approve`, {
    method: "POST",
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

export async function execute(
  approvalId: string,
  toolName: string,
  toolInput: any,
) {
  const r = await fetch(`${BASE}/executions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      approval_id: approvalId,
      tool_name: toolName,
      tool_input: toolInput,
    }),
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}
