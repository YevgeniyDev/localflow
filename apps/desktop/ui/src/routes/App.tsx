import React, { useEffect, useMemo, useState } from "react";
import {
  approveDraft,
  chat,
  ConversationDetailOut,
  ConversationListItem,
  execute,
  getConversation,
  listConversations,
  updateDraft,
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
  return /\b(email|mail|subject|cover letter|letter)\b/.test(text);
}

function shouldOpenDraftStudio(
  userText: string,
  draft: { title?: string | null; content?: string | null } | null | undefined,
  toolPlan: any,
): boolean {
  const text = (userText || "").trim().toLowerCase();
  const hasToolActions = Array.isArray(toolPlan?.actions) && toolPlan.actions.length > 0;
  if (hasToolActions) return true;

  const hasDraftMaterial = !!((draft?.title || "").trim() || (draft?.content || "").trim());
  if (!hasDraftMaterial) return false;

  const requestVerb =
    /\b(write|draft|compose|prepare|create|generate|rewrite|edit|summarize|translate|outline|format|plan|code|implement|open|search|find|send)\b/.test(
      text,
    );
  const deliverableTarget =
    /\b(email|mail|message|reply|post|linkedin|tweet|caption|plan|schedule|checklist|proposal|document|report|summary|code|script|function|routine)\b/.test(
      text,
    );
  const conversationalCue =
    /^(hi|hello|hey|yo|sup)\b|(?:^|\s)(can|could|should|do|does|is|are|what|why|how|would)\b.*\?|(?:^|\s)(idea|opinion|advice|think)\b/.test(
      text,
    );

  if (conversationalCue && !(requestVerb && deliverableTarget)) return false;
  if (requestVerb && deliverableTarget) return true;

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
  const [lastExecutionResult, setLastExecutionResult] = useState<any>(null);
  const [approvedBrowserActionKeys, setApprovedBrowserActionKeys] = useState<Record<string, boolean>>({});
  const [allowHighRiskBrowser, setAllowHighRiskBrowser] = useState(false);
  const [showDraftStudio, setShowDraftStudio] = useState(false);
  const [needsTitleInput, setNeedsTitleInput] = useState(false);

  const [history, setHistory] = useState<ConversationListItem[]>([]);
  const [historyBusy, setHistoryBusy] = useState(false);

  const canSend = useMemo(() => !busy && msg.trim().length > 0, [busy, msg]);
  const canApprove = useMemo(() => !busy && !!draftId, [busy, draftId]);
  const canExecute = useMemo(() => !busy && !!approvalId, [busy, approvalId]);
  const browserPlans = useMemo(() => {
    const actions = Array.isArray(toolPlan?.actions) ? toolPlan.actions : [];
    return actions
      .map((a: any, idx: number) => ({ a, idx }))
      .filter((x: any) => x.a?.tool === "browser_automation" && Array.isArray(x.a?.params?.actions))
      .map((x: any) => {
        const actionIds = (x.a.params.actions as any[])
          .map((s: any) => (typeof s?.id === "string" ? s.id.trim() : ""))
          .filter((id: string) => id.length > 0);
        return {
          planIndex: x.idx,
          params: x.a.params,
          actionIds,
        };
      });
  }, [toolPlan]);
  const browserSearchPlans = useMemo(() => {
    const actions = Array.isArray(toolPlan?.actions) ? toolPlan.actions : [];
    return actions
      .map((a: any, idx: number) => ({ a, idx }))
      .filter((x: any) => x.a?.tool === "browser_search" && typeof x.a?.params?.query === "string")
      .map((x: any) => ({
        planIndex: x.idx,
        params: x.a.params,
      }));
  }, [toolPlan]);

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
        const titleless = isTitlelessIntent(lastUserMessage);
        const hasTitle = !!(out.latest_draft.title ?? "").trim();

        setDraftId(out.latest_draft.id);
        setDraftTitle(out.latest_draft.title ?? "");
        setDraftBody(out.latest_draft.content ?? "");
        setNeedsTitleInput(!titleless && (hasTitle || inferNeedsTitleInput(lastUserMessage)));
        setShowDraftStudio(
          shouldOpenDraftStudio(lastUserMessage, out.latest_draft, out.latest_tool_plan ?? null),
        );
        setToolPlan(out.latest_tool_plan ?? null);
      } else {
        setDraftId(undefined);
        setDraftTitle("");
        setDraftBody("");
        setNeedsTitleInput(false);
        setShowDraftStudio(false);
        setToolPlan(null);
      }

      setApprovalId(undefined);
      setLastExecutionResult(null);
      setApprovedBrowserActionKeys({});
      setAllowHighRiskBrowser(false);
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
    setLastExecutionResult(null);
    setApprovedBrowserActionKeys({});
    setAllowHighRiskBrowser(false);
    setNeedsTitleInput(false);
    setShowDraftStudio(false);
  }

  async function onSend() {
    setErr(null);
    const userText = msg.trim();
    if (!userText) return;
    setMsg("");
    setBusy(true);
    try {
      const titleless = isTitlelessIntent(userText);
      const needsTitleFromPrompt = inferNeedsTitleInput(userText);
      setChatLog((prev) => [...prev, { role: "user", content: userText }]);

      const out = await chat(userText, convId);

      setConvId(out.conversation_id);
      setDraftId(out.draft.id);
      setDraftTitle(out.draft.title ?? "");
      setDraftBody(out.draft.content ?? "");
      setNeedsTitleInput(!titleless && (!!(out.draft.title ?? "").trim() || needsTitleFromPrompt));
      setShowDraftStudio(shouldOpenDraftStudio(userText, out.draft, out.tool_plan));

      setToolPlan(out.tool_plan);
      setApprovalId(undefined);
      setLastExecutionResult(null);
      setApprovedBrowserActionKeys({});
      setAllowHighRiskBrowser(false);

      const assistantText = out.assistant_message ?? "";
      if (assistantText) {
        setChatLog((prev) => [...prev, { role: "assistant", content: assistantText }]);
      }
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
      setLastExecutionResult({ tool: "open_links", urls });
    } catch (e: any) {
      setErr(String(e?.message ?? e));
    } finally {
      setBusy(false);
    }
  }

  async function onExecuteBrowserSearch() {
    if (!approvalId) return;
    setErr(null);
    setBusy(true);
    try {
      if (!browserSearchPlans.length) {
        setErr("No browser_search actions in tool plan.");
        return;
      }
      const outputs: any[] = [];
      for (const plan of browserSearchPlans) {
        const out = await execute(
          approvalId,
          "browser_search",
          plan.params,
          { approved_actions: [] },
        );
        outputs.push({ planIndex: plan.planIndex, output: out });
      }
      setLastExecutionResult({ tool: "browser_search", outputs });
    } catch (e: any) {
      setErr(String(e?.message ?? e));
    } finally {
      setBusy(false);
    }
  }

  function toggleBrowserAction(planIndex: number, actionId: string, checked: boolean) {
    const key = `${planIndex}:${actionId}`;
    setApprovedBrowserActionKeys((prev) => ({ ...prev, [key]: checked }));
  }

  async function onExecuteBrowserAutomation() {
    if (!approvalId) return;
    setErr(null);
    setBusy(true);
    try {
      if (!browserPlans.length) {
        setErr("No browser_automation actions in tool plan.");
        return;
      }
      if (!allowHighRiskBrowser) {
        setErr("Enable high-risk confirmation before running browser automation.");
        return;
      }

      for (const plan of browserPlans) {
        if (!plan.actionIds.length) {
          setErr("Every browser automation step must include an id.");
          return;
        }

        const approvedActions = plan.actionIds.filter(
          (id) => !!approvedBrowserActionKeys[`${plan.planIndex}:${id}`],
        );
        if (approvedActions.length !== plan.actionIds.length) {
          setErr("Confirm each browser action checkbox before execution.");
          return;
        }

        await execute(approvalId, "browser_automation", plan.params, {
          approved_actions: approvedActions,
          allow_high_risk: true,
        });
      }
    } catch (e: any) {
      setErr(String(e?.message ?? e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="app-shell app-shell--no-draft">
      <aside className="panel sidebar-panel">
        <div className="panel-header sidebar-header">
          <h2 className="panel-title">LocalFlow</h2>
        </div>

        <div className="sidebar-actions">
          <button className="btn btn-primary sidebar-btn" onClick={onNewChat} disabled={busy}>
            New Chat
          </button>
          <button className="btn sidebar-btn" onClick={refreshHistory} disabled={historyBusy || busy}>
            Refresh
          </button>
        </div>

        <div className="history-scroll history-list">
          {historyBusy && <div className="loading-text">Loading conversations...</div>}
          {!historyBusy && history.length === 0 && <div className="empty-text">No conversations yet.</div>}

          {!historyBusy &&
            history.map((c) => {
              const active = !!convId && c.id === convId;
              return (
                <button
                  key={c.id}
                  className={`history-card ${active ? "history-card--active" : ""}`}
                  onClick={() => loadConversation(c.id)}
                  disabled={busy}
                  title={c.id}
                >
                  <div className="history-card__title">{c.title || "Conversation"}</div>
                  <div className="history-card__meta">{c.message_count} messages</div>
                  <div className="history-card__preview">{c.last_message_preview}</div>
                </button>
              );
            })}
        </div>

        <div className="meta-line">Active: {convId ?? "(none)"}</div>
      </aside>

      <section className="panel chat-panel chat-main">
        <div className="panel-header chat-topbar">
          <h2 className="panel-title">Chat</h2>
        </div>

        <div className="chat-scroll">
          {chatLog.length === 0 ? (
            <div className="empty-text">No messages yet.</div>
          ) : (
            <>
              {chatLog.map((m, idx) => (
                <article
                  key={idx}
                  className={`chat-msg ${
                    m.role === "assistant" ? "chat-msg--assistant" : "chat-msg--user"
                  }`}
                >
                  <div className="chat-msg__content">{m.content}</div>
                </article>
              ))}
              {showDraftStudio && (
                <article className="chat-msg chat-msg--assistant draft-inline">
                  <div className="chat-msg__role">Draft Studio</div>

                  {needsTitleInput && (
                    <div>
                      <div className="label">Title</div>
                      <input
                        className="field"
                        value={draftTitle}
                        onChange={(e) => setDraftTitle(e.target.value)}
                        placeholder="Title..."
                      />
                    </div>
                  )}

                  <div>
                    <div className="label">Content</div>
                    <textarea
                      className="textarea draft-inline__textarea"
                      value={draftBody}
                      onChange={(e) => setDraftBody(e.target.value)}
                      placeholder="Draft content..."
                    />
                  </div>

                  <div className="draft-actions">
                    <button className="btn btn-accent" onClick={onApprove} disabled={!canApprove}>
                      Approve
                    </button>
                    <button className="btn" onClick={onExecuteOpenLinks} disabled={!canExecute}>
                      Execute: open links
                    </button>
                    <button className="btn" onClick={onExecuteBrowserSearch} disabled={!canExecute || !browserSearchPlans.length}>
                      Execute: browser search
                    </button>
                    <button className="btn" onClick={onExecuteBrowserAutomation} disabled={!canExecute || !browserPlans.length}>
                      Execute: browser automation
                    </button>
                    <div className={`status-pill ${approvalId ? "status-pill--ok" : ""}`}>
                      {approvalId ? "Approved (hash locked)" : "Not approved"}
                    </div>
                  </div>

                  {browserPlans.length > 0 && (
                    <div className="debug-box" style={{ marginTop: 8 }}>
                      <div style={{ fontWeight: 700, marginBottom: 6 }}>Browser Actions (explicit confirmation)</div>
                      {browserPlans.map((plan) => (
                        <div key={plan.planIndex} style={{ marginBottom: 8 }}>
                          <div style={{ marginBottom: 4 }}>Plan #{plan.planIndex + 1}</div>
                          {plan.actionIds.map((actionId) => {
                            const key = `${plan.planIndex}:${actionId}`;
                            return (
                              <label key={key} style={{ display: "block", marginBottom: 3 }}>
                                <input
                                  type="checkbox"
                                  checked={!!approvedBrowserActionKeys[key]}
                                  onChange={(e) => toggleBrowserAction(plan.planIndex, actionId, e.target.checked)}
                                  disabled={busy || !approvalId}
                                />{" "}
                                {actionId}
                              </label>
                            );
                          })}
                        </div>
                      ))}
                      <label style={{ display: "block", marginTop: 4 }}>
                        <input
                          type="checkbox"
                          checked={allowHighRiskBrowser}
                          onChange={(e) => setAllowHighRiskBrowser(e.target.checked)}
                          disabled={busy || !approvalId}
                        />{" "}
                        I confirm high-risk browser automation
                      </label>
                    </div>
                  )}

                  <pre className="debug-box">
                    draftId: {draftId ?? "(none)"}
                    {"\n"}
                    approvalId: {approvalId ?? "(none)"}
                    {"\n"}
                    toolPlan: {JSON.stringify(toolPlan, null, 2)}
                    {"\n"}
                    lastExecutionResult: {JSON.stringify(lastExecutionResult, null, 2)}
                  </pre>
                </article>
              )}
            </>
          )}
        </div>

        <div className="chat-footer">
          {err && (
            <div className="error-banner">
              <b>Error:</b> {err}
            </div>
          )}
          <div className="composer">
            <input
              className="field"
              value={msg}
              onChange={(e) => setMsg(e.target.value)}
              placeholder="Ask LocalFlow..."
              disabled={busy}
              onKeyDown={(e) => {
                if (e.key === "Enter") onSend();
              }}
            />
            <button className="btn btn-primary" onClick={onSend} disabled={!canSend}>
              Send
            </button>
          </div>
        </div>
      </section>

    </div>
  );
}
