const BASE = "http://127.0.0.1:7878/v1";

async function readError(r: Response): Promise<string> {
  const text = await r.text();
  try {
    const j = JSON.parse(text);
    if (j && typeof j.detail === "string") return j.detail;
  } catch {}
  return text || `HTTP ${r.status}`;
}

export async function chat(
  message: string,
  conversationId?: string,
) {
  const r = await fetch(`${BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message,
      conversation_id: conversationId ?? null,
    }),
  });
  if (!r.ok) throw new Error(await readError(r));
  return r.json();
}

export async function updateDraft(
  draftId: string,
  title: string,
  content: string,
) {
  const r = await fetch(`${BASE}/drafts/${draftId}/update`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title, content }),
  });
  if (!r.ok) throw new Error(await readError(r));
}

export async function approveDraft(draftId: string) {
  const r = await fetch(`${BASE}/drafts/${draftId}/approve`, {
    method: "POST",
  });
  if (!r.ok) throw new Error(await readError(r));
  return r.json();
}

export async function execute(
  approvalId: string,
  toolName: string,
  toolInput: any,
  confirmation?: any,
) {
  const r = await fetch(`${BASE}/executions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      approval_id: approvalId,
      tool_name: toolName,
      tool_input: toolInput,
      confirmation: confirmation ?? null,
    }),
  });
  if (!r.ok) throw new Error(await readError(r));
  return r.json();
}

// NEW: Conversations API
export type ConversationListItem = {
  id: string;
  created_at: string;
  last_activity_at: string;
  title: string;
  last_message_preview: string;
  message_count: number;
  latest_draft_id?: string | null;
};

export type ConversationListOut = {
  items: ConversationListItem[];
  total: number;
  limit: number;
  offset: number;
};

export type MessageOut = {
  id: string;
  role: "user" | "assistant" | string;
  content: string;
  created_at: string;
};

export type DraftOut = {
  id: string;
  type: string;
  title: string;
  content: string;
  status: string;
  created_at: string;
  updated_at?: string | null;
};

export type ConversationDetailOut = {
  id: string;
  created_at: string;
  updated_at?: string | null;
  messages: MessageOut[];
  latest_draft?: DraftOut | null;
};

export async function listConversations(
  limit = 30,
  offset = 0,
): Promise<ConversationListOut> {
  const r = await fetch(
    `${BASE}/conversations?limit=${limit}&offset=${offset}`,
    {
      method: "GET",
    },
  );
  if (!r.ok) throw new Error(await readError(r));
  return r.json();
}

export async function getConversation(
  conversationId: string,
): Promise<ConversationDetailOut> {
  const r = await fetch(
    `${BASE}/conversations/${encodeURIComponent(conversationId)}`,
    {
      method: "GET",
    },
  );
  if (!r.ok) throw new Error(await readError(r));
  return r.json();
}
