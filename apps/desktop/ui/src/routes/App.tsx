import React, { useEffect, useMemo, useState } from "react";
import {
  approveDraft,
  chat,
  ConversationDetailOut,
  ConversationListItem,
  execute,
  getConversation,
  listConversations,
  ragBuildIndex,
  ragListDirs,
  ragListDrives,
  ragListPermissions,
  ragStatus,
  ragSetPermissions,
  updateDraft,
} from "../lib/api";

type ChatMsg = { role: "user" | "assistant"; content: string };
type RagConfigSnapshot = {
  baseAccess: "full" | "disks" | "advanced";
  selectedDisks: Record<string, boolean>;
  advancedPaths: string[];
};

const RAG_CONFIG_STORAGE_KEY = "localflow.fileSearch.config.v1";

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

function isRagLikeIntent(userText: string): boolean {
  const text = (userText || "").trim().toLowerCase();
  if (!text) return false;
  if (/\breadme\b/.test(text)) return true;
  if (/\b\w+\.(txt|md|pdf|doc|docx|ppt|pptx|xls|xlsx|csv|json|py|ts|js|cpp|c|java|go|rs)\b/.test(text)) {
    return true;
  }
  if (/\b(find|search|locate|lookup|look up)\b/.test(text) && /\b(for|about)\b/.test(text)) {
    return true;
  }
  return (
    /\b(find|search|scan|lookup|look up|read|summarize|open)\b/.test(text) &&
    /\b(file|files|document|documents|folder|directory|local|pc|computer|disk|drive|pdf|docx|txt)\b/.test(
      text,
    )
  );
}

function shouldOpenDraftStudio(
  userText: string,
  draft: { title?: string | null; content?: string | null } | null | undefined,
  toolPlan: any,
): boolean {
  const text = (userText || "").trim().toLowerCase();
  if (isRagLikeIntent(text)) return false;
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
  const [copiedMsgIdx, setCopiedMsgIdx] = useState<number | null>(null);
  const [fileSearchInProgress, setFileSearchInProgress] = useState(false);
  const [fileSearchMode, setFileSearchMode] = useState(false);
  const [showRagPermissionModal, setShowRagPermissionModal] = useState(false);
  const [ragAvailableDrives, setRagAvailableDrives] = useState<string[]>([]);
  const [ragBaseAccess, setRagBaseAccess] = useState<"full" | "disks" | "advanced">("disks");
  const [ragSelectedDisks, setRagSelectedDisks] = useState<Record<string, boolean>>({});
  const [ragAdvancedPaths, setRagAdvancedPaths] = useState<string[]>([]);
  const [ragRootDirs, setRagRootDirs] = useState<string[]>([]);
  const [ragTreeChildren, setRagTreeChildren] = useState<Record<string, string[]>>({});
  const [ragTreeExpanded, setRagTreeExpanded] = useState<Record<string, boolean>>({});
  const [ragConfigBusy, setRagConfigBusy] = useState(false);
  const [fileSearchScopeSummary, setFileSearchScopeSummary] = useState("");

  const canSend = useMemo(() => !busy, [busy]);
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

  useEffect(() => {
    (async () => {
      try {
        const out = await ragListPermissions();
        const roots = out.roots ?? [];
        setFileSearchScopeSummary(formatScopeSummary(roots));
      } catch {
        // non-blocking
      }
    })();
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
    setFileSearchMode(false);
    setShowRagPermissionModal(false);
    setRagAvailableDrives([]);
    setRagBaseAccess("disks");
    setRagSelectedDisks({});
    setRagAdvancedPaths([]);
    setRagRootDirs([]);
    setRagTreeChildren({});
    setRagTreeExpanded({});
    setRagConfigBusy(false);
    setFileSearchInProgress(false);
  }

  async function refreshDirBrowserRoots() {
    try {
      const out = await ragListDirs(null);
      const dirs = out.dirs ?? [];
      setRagRootDirs(dirs);
      setRagTreeChildren({});
      setRagTreeExpanded({});
    } catch (e: any) {
      setErr(String(e?.message ?? e));
    }
  }

  async function toggleFolder(path: string) {
    if (ragTreeExpanded[path]) {
      setRagTreeExpanded((prev) => ({ ...prev, [path]: false }));
      return;
    }
    if (!ragTreeChildren[path]) {
      try {
        const out = await ragListDirs(path);
        setRagTreeChildren((prev) => ({ ...prev, [path]: out.dirs ?? [] }));
      } catch (e: any) {
        setErr(String(e?.message ?? e));
        return;
      }
    }
    setRagTreeExpanded((prev) => ({ ...prev, [path]: true }));
  }

  function addAdvancedPath(path: string) {
    const p = path.trim();
    if (!p) return;
    setRagAdvancedPaths((prev) => (prev.includes(p) ? prev : [...prev, p]));
  }

  function removeAdvancedPath(path: string) {
    setRagAdvancedPaths((prev) => prev.filter((p) => p !== path));
  }

  function folderLabel(path: string): string {
    const p = (path || "").replace(/[\\/]+$/, "");
    const m = p.match(/[^\\/]+$/);
    if (m && m[0]) return m[0];
    return path;
  }

  function compactPathByFolders(path: string, maxChars = 40): string {
    const raw = (path || "").trim();
    if (!raw) return raw;
    if (raw.length <= maxChars) return raw;

    const parts = raw.split(/[\\/]+/).filter((p) => p.length > 0);
    if (parts.length === 0) return raw;
    const last = parts[parts.length - 1];
    if (last.length + 4 >= maxChars) return `...\\${last}`;

    let out = last;
    for (let i = parts.length - 2; i >= 0; i -= 1) {
      const candidate = `${parts[i]}\\${out}`;
      if (`...\\${candidate}`.length > maxChars) break;
      out = candidate;
    }
    return `...\\${out}`;
  }

  function loadSavedRagConfig(): RagConfigSnapshot | null {
    try {
      const raw = localStorage.getItem(RAG_CONFIG_STORAGE_KEY);
      if (!raw) return null;
      const parsed = JSON.parse(raw);
      if (!parsed || typeof parsed !== "object") return null;
      const baseAccess =
        parsed.baseAccess === "full" || parsed.baseAccess === "disks" || parsed.baseAccess === "advanced"
          ? parsed.baseAccess
          : "disks";
      const selectedDisks =
        parsed.selectedDisks && typeof parsed.selectedDisks === "object" ? parsed.selectedDisks : {};
      const advancedPaths = Array.isArray(parsed.advancedPaths)
        ? parsed.advancedPaths.filter((x: any) => typeof x === "string" && x.trim())
        : [];
      return { baseAccess, selectedDisks, advancedPaths };
    } catch {
      return null;
    }
  }

  function saveRagConfigSnapshot(snapshot: RagConfigSnapshot) {
    try {
      localStorage.setItem(RAG_CONFIG_STORAGE_KEY, JSON.stringify(snapshot));
    } catch {
      // non-blocking
    }
  }

  async function openFileSearchSetupModal() {
    setErr(null);
    try {
      const [drivesOut, permsOut] = await Promise.all([ragListDrives(), ragListPermissions()]);
      const drives = drivesOut.drives ?? [];
      const roots = permsOut.roots ?? [];
      const saved = loadSavedRagConfig();
      const diskMap: Record<string, boolean> = {};
      for (const d of drives) {
        diskMap[d] = roots.some((r) => r.toLowerCase().startsWith(d.toLowerCase()));
      }
      setRagAvailableDrives(drives);
      if (saved) {
        const selectedMap: Record<string, boolean> = {};
        for (const d of drives) selectedMap[d] = !!saved.selectedDisks[d];
        setRagBaseAccess(saved.baseAccess);
        setRagSelectedDisks(selectedMap);
        setRagAdvancedPaths(saved.advancedPaths);
      } else {
        setRagSelectedDisks(diskMap);
        if (roots.length && roots.every((r) => drives.some((d) => r.toLowerCase().startsWith(d.toLowerCase())))) {
          if (drives.length && drives.every((d) => diskMap[d])) {
            setRagBaseAccess("full");
          } else {
            setRagBaseAccess("disks");
          }
          setRagAdvancedPaths([]);
        } else {
          setRagBaseAccess("advanced");
          setRagAdvancedPaths(roots);
        }
      }
      setShowRagPermissionModal(true);
      await refreshDirBrowserRoots();
    } catch (e: any) {
      setErr(String(e?.message ?? e));
    }
  }

  function sameRootSets(a: string[], b: string[]): boolean {
    const aa = [...a].map((x) => x.toLowerCase()).sort();
    const bb = [...b].map((x) => x.toLowerCase()).sort();
    if (aa.length !== bb.length) return false;
    for (let i = 0; i < aa.length; i += 1) {
      if (aa[i] !== bb[i]) return false;
    }
    return true;
  }

  function formatScopeSummary(roots: string[]): string {
    if (!roots.length) return "";
    const unique = Array.from(new Set(roots.map((r) => r.trim()).filter((r) => r.length > 0)));
    const drives = unique.filter((r) => /^[a-zA-Z]:\\?$/.test(r));
    if (drives.length === unique.length) {
      return drives.join(" + ");
    }
    const compact = unique.slice(0, 3);
    if (unique.length > 3) compact.push(`+${unique.length - 3} more`);
    return compact.join(" + ");
  }

  async function onApproveRagPermission() {
    setErr(null);
    setRagConfigBusy(true);
    try {
      let roots: string[] = [];
      if (ragBaseAccess === "full") {
        roots = [...ragAvailableDrives];
      } else if (ragBaseAccess === "disks") {
        roots = ragAvailableDrives.filter((d) => !!ragSelectedDisks[d]);
      } else {
        roots = ragAdvancedPaths.map((x) => x.trim()).filter((x) => x.length > 0);
      }
      if (!roots.length) {
        setErr("Select at least one disk or folder.");
        return;
      }
      const status = await ragStatus();
      const indexedRoots = Array.isArray(status?.index_meta?.roots) ? status.index_meta.roots : [];
      const indexReady = !!status?.index_exists && sameRootSets(roots, indexedRoots);
      await ragSetPermissions(roots);
      if (!indexReady) {
        await ragBuildIndex(2500, roots);
      }
      setShowRagPermissionModal(false);
      setFileSearchMode(true);
      setFileSearchScopeSummary(formatScopeSummary(roots));
      saveRagConfigSnapshot({
        baseAccess: ragBaseAccess,
        selectedDisks: ragSelectedDisks,
        advancedPaths: ragAdvancedPaths,
      });
      setChatLog((prev) => [
        ...prev,
        {
          role: "assistant",
          content:
            "File Search mode is enabled and searchable folders are configured. You can now ask file search queries.",
        },
      ]);
    } catch (e: any) {
      setErr(String(e?.message ?? e));
    } finally {
      setRagConfigBusy(false);
    }
  }

  function onRejectRagPermission() {
    setShowRagPermissionModal(false);
    setFileSearchMode(false);
    setChatLog((prev) => [
      ...prev,
      {
        role: "assistant",
        content:
          "Understood. I couldn't access local files without your permission. Do you want to try again or do you have other questions?",
      },
    ]);
  }

  function renderFolderTree(nodes: string[], level = 0): React.ReactNode {
    return nodes.map((dir) => {
      const children = ragTreeChildren[dir] ?? [];
      const expanded = !!ragTreeExpanded[dir];
      const indent = Math.min(level * 14, 84);
      return (
        <React.Fragment key={dir}>
          <div
            className="permission-browser__row"
            style={{ paddingLeft: `${indent}px` }}
            onClick={() => toggleFolder(dir)}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                toggleFolder(dir);
              }
            }}
            aria-label={expanded ? "Collapse folder row" : "Expand folder row"}
          >
            <button
              className="permission-browser__toggle"
              type="button"
              onClick={() => toggleFolder(dir)}
              disabled={ragConfigBusy}
              aria-label={expanded ? "Collapse folder" : "Expand folder"}
              title={expanded ? "Collapse folder" : "Expand folder"}
            >
              <svg
                viewBox="0 0 24 24"
                width="14"
                height="14"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.2"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                {expanded ? <path d="m6 9 6 6 6-6" /> : <path d="m9 6 6 6-6 6" />}
              </svg>
            </button>
            <span className="permission-browser__dir">{folderLabel(dir)}</span>
            <button
              className="permission-browser__add"
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                addAdvancedPath(dir);
              }}
              disabled={ragConfigBusy}
              data-tooltip="Allow this folder"
              aria-label="Allow access to this folder"
            >
              +
            </button>
          </div>
          {expanded && children.length > 0 && renderFolderTree(children, level + 1)}
        </React.Fragment>
      );
    });
  }

  async function onSend() {
    setErr(null);
    const userText = msg.trim();
    if (!userText) return;
    setMsg("");
    const forceFileSearch = fileSearchMode;
    setFileSearchInProgress(forceFileSearch);
    setBusy(true);
    try {
      const titleless = isTitlelessIntent(userText);
      const needsTitleFromPrompt = inferNeedsTitleInput(userText);
      setChatLog((prev) => [...prev, { role: "user", content: userText }]);

      const out = await chat(userText, convId, { forceFileSearch });

      setConvId(out.conversation_id);
      setDraftId(out.draft.id);
      setDraftTitle(out.draft.title ?? "");
      setDraftBody(out.draft.content ?? "");
      setNeedsTitleInput(!titleless && (!!(out.draft.title ?? "").trim() || needsTitleFromPrompt));
      const hasRagHits = Array.isArray(out.rag_hits) && out.rag_hits.length > 0;
      setShowDraftStudio(
        !out.rag_permission_required &&
          !hasRagHits &&
          shouldOpenDraftStudio(userText, out.draft, out.tool_plan),
      );

      setToolPlan(out.tool_plan);
      setApprovalId(undefined);
      setLastExecutionResult(null);
      setApprovedBrowserActionKeys({});
      setAllowHighRiskBrowser(false);

      const assistantText = out.assistant_message ?? "";
      if (assistantText) {
        setChatLog((prev) => [...prev, { role: "assistant", content: assistantText }]);
      }
      if (out.rag_permission_required) {
        await openFileSearchSetupModal();
        const suggested = (out.rag_suggested_path ?? "").trim();
        if (suggested) {
          setRagBaseAccess("advanced");
          setRagAdvancedPaths([suggested]);
        }
        setShowDraftStudio(false);
      } else {
        setShowRagPermissionModal(false);
      }
      refreshHistory();
    } catch (e: any) {
      setErr(String(e?.message ?? e));
    } finally {
      setBusy(false);
      setFileSearchInProgress(false);
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

  function previousUserMessage(idx: number): string {
    for (let i = idx - 1; i >= 0; i -= 1) {
      if (chatLog[i]?.role === "user") return chatLog[i].content;
    }
    return "";
  }

  async function onCopyAssistant(text: string, idx: number) {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedMsgIdx(idx);
      setTimeout(() => setCopiedMsgIdx((prev) => (prev === idx ? null : prev)), 1400);
    } catch (e: any) {
      setErr(String(e?.message ?? e));
    }
  }

  async function onRegenerateAssistant(idx: number) {
    const userText = previousUserMessage(idx).trim();
    if (!userText || !convId) return;
    setErr(null);
    const forceFileSearch = fileSearchMode;
    setFileSearchInProgress(forceFileSearch);
    setBusy(true);
    try {
      const out = await chat(userText, convId, { forceFileSearch });
      setConvId(out.conversation_id);
      const assistantText = out.assistant_message ?? "";
      if (assistantText) {
        setChatLog((prev) =>
          prev.map((m, i) =>
            i === idx && m.role === "assistant" ? { role: "assistant", content: assistantText } : m,
          ),
        );
      }
      if (out.draft) {
        const titleless = isTitlelessIntent(userText);
        const needsTitleFromPrompt = inferNeedsTitleInput(userText);
        const hasRagHits = Array.isArray(out.rag_hits) && out.rag_hits.length > 0;
        setDraftId(out.draft.id);
        setDraftTitle(out.draft.title ?? "");
        setDraftBody(out.draft.content ?? "");
        setNeedsTitleInput(!titleless && (!!(out.draft.title ?? "").trim() || needsTitleFromPrompt));
        setShowDraftStudio(
          !out.rag_permission_required &&
            !hasRagHits &&
            shouldOpenDraftStudio(userText, out.draft, out.tool_plan),
        );
        setToolPlan(out.tool_plan);
        setApprovalId(undefined);
      }
      refreshHistory();
    } catch (e: any) {
      setErr(String(e?.message ?? e));
    } finally {
      setBusy(false);
      setFileSearchInProgress(false);
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
                  {m.role === "assistant" && (
                    <div className="chat-msg__actions">
                      <button
                        className="chat-action-btn chat-action-btn--icon"
                        onClick={() => onCopyAssistant(m.content, idx)}
                        disabled={busy}
                        aria-label="Copy response"
                        data-tooltip={copiedMsgIdx === idx ? "Copied" : "Copy"}
                      >
                        <span className="chat-action-btn__icon" aria-hidden="true">
                          {copiedMsgIdx === idx ? (
                            <svg
                              viewBox="0 0 24 24"
                              width="16"
                              height="16"
                              fill="none"
                              stroke="currentColor"
                              strokeWidth="2"
                              strokeLinecap="round"
                              strokeLinejoin="round"
                            >
                              <path d="M20 6 9 17l-5-5" />
                            </svg>
                          ) : (
                            <svg
                              viewBox="0 0 24 24"
                              width="16"
                              height="16"
                              fill="none"
                              stroke="currentColor"
                              strokeWidth="2"
                              strokeLinecap="round"
                              strokeLinejoin="round"
                            >
                              <rect x="9" y="9" width="11" height="11" rx="2" />
                              <rect x="4" y="4" width="11" height="11" rx="2" />
                            </svg>
                          )}
                        </span>
                      </button>
                      <button
                        className="chat-action-btn chat-action-btn--icon"
                        onClick={() => onRegenerateAssistant(idx)}
                        disabled={busy || !previousUserMessage(idx)}
                        aria-label="Regenerate response"
                        data-tooltip="Try again"
                      >
                        <span className="chat-action-btn__icon" aria-hidden="true">
                          <svg
                            viewBox="0 0 24 24"
                            width="16"
                            height="16"
                            fill="none"
                            stroke="currentColor"
                            strokeWidth="2"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                          >
                            <path d="M21 12a9 9 0 1 1-2.64-6.36" />
                            <path d="M21 3v6h-6" />
                          </svg>
                        </span>
                      </button>
                    </div>
                  )}
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
          <div className="composer-modes">
            <button
              className={`mode-chip ${fileSearchMode ? "mode-chip--active" : ""}`}
              onClick={() => {
                if (fileSearchMode) {
                  setFileSearchMode(false);
                } else {
                  openFileSearchSetupModal();
                }
              }}
              disabled={busy}
              type="button"
            >
              File Search
            </button>
            {fileSearchMode && fileSearchScopeSummary && (
              <div className="mode-scope-summary">
                File Search: {fileSearchScopeSummary}
              </div>
            )}
          </div>
          {fileSearchInProgress && (
            <div className="search-progress">
              <div className="search-progress__label">Searching local files...</div>
              <div className="search-progress__bar">
                <div className="search-progress__indeterminate" />
              </div>
            </div>
          )}
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
            <button className="btn btn-primary" onClick={onSend} disabled={!canSend} aria-label={busy ? "Sending" : "Send"}>
              {busy ? <span className="btn-spinner" aria-hidden="true" /> : "Send"}
            </button>
          </div>
        </div>
      </section>

      {showRagPermissionModal && (
        <div className="permission-modal-backdrop" role="dialog" aria-modal="true">
          <div className="permission-modal">
            {ragConfigBusy && (
              <div className="permission-modal__overlay">
                <div className="permission-modal__overlay-card">
                  <span className="btn-spinner" aria-hidden="true" />
                  <span>Applying permissions...</span>
                </div>
              </div>
            )}
            <div className="permission-modal__title">Configure File Search Access</div>
            <div className="permission-modal__text">
              Select what LocalFlow is allowed to search.
            </div>
            <label className="permission-option">
              <input
                type="radio"
                name="base-access"
                checked={ragBaseAccess === "full"}
                onChange={() => setRagBaseAccess("full")}
                disabled={busy}
              />{" "}
              Full access (all detected disks)
            </label>
            <label className="permission-option">
              <input
                type="radio"
                name="base-access"
                checked={ragBaseAccess === "disks"}
                onChange={() => setRagBaseAccess("disks")}
                disabled={busy}
              />{" "}
              Disk-only selection
            </label>
            {ragBaseAccess === "disks" && (
              <div className="permission-disk-list">
                {ragAvailableDrives.map((d) => (
                  <label key={d} className="permission-option permission-option--sub">
                    <input
                      type="checkbox"
                      checked={!!ragSelectedDisks[d]}
                      onChange={(e) => setRagSelectedDisks((prev) => ({ ...prev, [d]: e.target.checked }))}
                      disabled={busy}
                    />{" "}
                    {d}
                  </label>
                ))}
              </div>
            )}
            <label className="permission-option">
              <input
                type="radio"
                name="base-access"
                checked={ragBaseAccess === "advanced"}
                onChange={() => setRagBaseAccess("advanced")}
                disabled={busy}
              />{" "}
              Advanced folder paths
              <span
                className="help-hint"
                data-tooltip="Click the arrow to open folders. Click + to allow that folder."
                aria-label="How to use advanced folder selection"
              >
                ?
              </span>
            </label>
            {ragBaseAccess === "advanced" && (
              <div className="permission-tags">
                {ragAdvancedPaths.length === 0 && (
                  <div className="permission-tags__empty">No folders selected yet. Use + in browser below.</div>
                )}
                {ragAdvancedPaths.map((p) => (
                  <span key={p} className="permission-tag">
                    <span className="permission-tag__text">{compactPathByFolders(p)}</span>
                    <button
                      className="permission-tag__remove"
                      type="button"
                      onClick={() => removeAdvancedPath(p)}
                      disabled={busy || ragConfigBusy}
                      aria-label="Remove folder path"
                      data-tooltip="Remove folder"
                    >
                      <svg
                        viewBox="0 0 24 24"
                        width="12"
                        height="12"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="2.4"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        aria-hidden="true"
                      >
                        <path d="M18 6 6 18" />
                        <path d="m6 6 12 12" />
                      </svg>
                    </button>
                  </span>
                ))}
              </div>
            )}
            {ragBaseAccess === "advanced" && (
              <div className="permission-browser">
                <div className="permission-browser__header">
                  <span>Browse folders</span>
                </div>
                <div className="permission-browser__path">Drives and folders</div>
                <div className="permission-browser__list">
                  {renderFolderTree(ragRootDirs)}
                </div>
              </div>
            )}
            <div className="permission-modal__actions">
              <button className="btn btn-accent" onClick={onApproveRagPermission} disabled={busy || ragConfigBusy}>
                Save & Enable
              </button>
              <button className="btn" onClick={onRejectRagPermission} disabled={busy || ragConfigBusy}>
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

    </div>
  );
}

