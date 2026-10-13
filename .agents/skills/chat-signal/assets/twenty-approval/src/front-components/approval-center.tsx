import { RestApiClient } from "twenty-client-sdk/rest";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { defineFrontComponent } from "twenty-sdk/define";
import { useUserId } from "twenty-sdk/front-component";
import { APPROVAL_FRONT_COMPONENT_UNIVERSAL_IDENTIFIER } from "src/constants/universal-identifiers";
import { parsePage, parseRequest, statuses } from "src/lib/contracts";
import type { ReviewRequest, ReviewStatus, ExecutionStatus } from "src/lib/contracts";

const labels: Record<ReviewStatus, string> = { pending: "待审核", approved: "已通过", rejected: "已拒绝", superseded: "已失效" };
const executionLabels: Record<ExecutionStatus, string> = {
  not_started: "尚未执行", queued: "等待执行", running: "执行中", succeeded: "执行成功",
  conflict: "记录有变化，需要处理", failed: "执行失败", manual_required: "需要人工完成操作",
};
const button = { padding: "9px 16px", border: "1px solid #cfd7df", borderRadius: 8, cursor: "pointer", background: "white", color: "#243448" };
const panel = { background: "white", border: "1px solid #dde3ea", borderRadius: 12, padding: 20 };
const time = (value: string) => new Date(value).toLocaleString();

function ApprovalCenter() {
  const userId = useUserId();
  const client = useMemo(() => new RestApiClient(), []);
  const [status, setStatus] = useState<ReviewStatus>("pending");
  const [requests, setRequests] = useState<ReviewRequest[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [cursor, setCursor] = useState<string | undefined>();
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [choice, setChoice] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const generation = useRef(0);
  const submitting = useRef(false);
  const selected = requests.find(row => row.id === selectedId) ?? null;

  const load = useCallback(async () => {
    const current = ++generation.current;
    setLoading(true); setError(""); setRequests([]); setSelectedId(null); setNextCursor(null);
    if (!userId) { setLoading(false); return; }
    try {
      const page = parsePage(await client.get("/s/cra-review/requests", { query: { status, ...(cursor ? { cursor } : {}) } }));
      if (generation.current !== current) return;
      setRequests(page.values); setNextCursor(page.nextCursor); setSelectedId(page.values[0]?.id ?? null);
    } catch {
      if (generation.current === current) setError("未能读取待审核事项。请重试；若持续失败，请让 Codex 核对审核服务和成员权限。");
    } finally { if (generation.current === current) setLoading(false); }
  }, [client, status, cursor, userId]);

  useEffect(() => { void load(); return () => { generation.current++; }; }, [load]);
  useEffect(() => { setChoice(null); setNote(""); }, [selectedId, selected?.planDigest]);

  const decide = async (outcome: "approved" | "rejected") => {
    if (!selected || selected.status !== "pending" || !selected.canDecide || loading || submitting.current) return;
    if (outcome === "approved" && selected.choices.length && !choice) return;
    submitting.current = true; setBusy(true); setError(""); setNotice("");
    const request = selected;
    try {
      const response = await client.post("/s/cra-review/decision", {
        id: request.id, planDigest: request.planDigest, outcome, note,
        selectedChoiceId: outcome === "approved" ? choice : null,
      });
      const saved = parseRequest((response as { value?: unknown }).value);
      setNotice(outcome === "approved" ? `已通过。${executionLabels[saved.execution.status]}。可在“已通过”中查看后续结果。` : "已拒绝，本次变更不会执行。");
      await load();
    } catch {
      setError("未能确认审核结果，可能是方案已变化或连接中断。请先刷新核对，避免凭旧内容继续处理。");
      // 超时可能已提交成功；清空可操作的旧记录，要求重新读取。
      setRequests([]); setSelectedId(null); setNextCursor(null);
    } finally { submitting.current = false; setBusy(false); }
  };

  if (!userId) return <div style={panel}>请登录 Twenty 后查看待审核事项。</div>;
  return <main style={{ padding: 24, background: "#f5f7fa", minHeight: "100vh", color: "#243448", fontFamily: "system-ui, sans-serif", lineHeight: 1.6 }}>
    <header style={{ display: "flex", justifyContent: "space-between", flexWrap: "wrap", gap: 16, marginBottom: 20 }}>
      <div><h1 style={{ margin: 0, fontSize: 27 }}>待审核</h1><p style={{ margin: "4px 0", color: "#64748b" }}>集中处理需要你确认的变更，查看依据和执行结果。</p></div>
      <button style={button} disabled={busy || loading} onClick={() => { setNotice(""); void load(); }}>刷新</button>
    </header>
    <nav aria-label="审核状态" style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 16 }}>
      {statuses.map(value => <button key={value} aria-pressed={status === value} disabled={busy || loading} style={{ ...button, background: status === value ? "#243448" : "white", color: status === value ? "white" : "#243448" }} onClick={() => { setStatus(value); setCursor(undefined); setNotice(""); }}>{labels[value]}</button>)}
    </nav>
    {error && <p role="alert" style={{ ...panel, color: "#a12622" }}>{error}</p>}
    {notice && <p role="status" style={{ ...panel, color: "#176441" }}>{notice}</p>}
    {loading ? <p role="status">正在读取…</p> : <div style={{ display: "flex", flexWrap: "wrap", alignItems: "flex-start", gap: 18 }}>
      <section aria-label="审核列表" style={{ ...panel, flex: "1 1 270px", minWidth: 240 }}>
        {!requests.length && !error && <p>当前没有{labels[status]}事项。</p>}
        {requests.map(row => <button key={row.id} disabled={busy} onClick={() => setSelectedId(row.id)} style={{ ...button, width: "100%", textAlign: "left", display: "block", marginBottom: 10, background: selectedId === row.id ? "#eef4fa" : "white" }}>
          <strong>{row.title}</strong><div style={{ color: "#64748b", fontSize: 13 }}>{row.target.recordLabel} · {time(row.createdAt)}</div>
          {row.status === "approved" && <div>{executionLabels[row.execution.status]}</div>}
        </button>)}
        <div style={{ display: "flex", gap: 8 }}>
          {cursor && <button style={button} disabled={busy} onClick={() => setCursor(undefined)}>返回首页</button>}
          {nextCursor && <button style={button} disabled={busy} onClick={() => setCursor(nextCursor)}>下一页</button>}
        </div>
      </section>
      {selected && <section aria-label="审核详情" style={{ ...panel, flex: "2 1 420px", minWidth: 260, overflowWrap: "anywhere" }}>
        <h2 style={{ marginTop: 0 }}>{selected.title}</h2>
        <p>{selected.target.objectLabel} · {selected.target.recordLabel}</p>
        <p style={{ background: "#fff7e6", padding: 12, borderRadius: 8 }}>{selected.reason}</p>
        <h3>准备变更</h3>
        {selected.changes.map((change, index) => <div key={index} style={{ borderTop: "1px solid #dde3ea", padding: "12px 0" }}>
          <strong>{change.fieldLabel}</strong><div style={{ whiteSpace: "pre-wrap" }}>当前：{change.before || "未填写"}</div><div style={{ whiteSpace: "pre-wrap" }}>拟改为：{change.after || "清空"}</div>
        </div>)}
        {!selected.changes.length && <p>请根据下方依据和选项确认处理方式。</p>}
        <h3>判断依据</h3>
        {selected.evidence.map((evidence, index) => <blockquote key={index} style={{ margin: "12px 0", paddingLeft: 12, borderLeft: "3px solid #cfd7df", whiteSpace: "pre-wrap" }}>
          <div>{evidence.excerpt || "原文请按来源引用查阅"}</div><small>{evidence.sourceLabel} · {evidence.reference}</small>
        </blockquote>)}
        <p style={{ color: "#64748b", fontSize: 13 }}>依据业务规则：{selected.ruleId} · {selected.ruleVersion}</p>
        {selected.status === "pending" && selected.canDecide && <fieldset disabled={busy} style={{ border: 0, padding: 0 }}>
          {!!selected.choices.length && <><legend>选择处理结果</legend>{selected.choices.map(option => <label key={option.id} style={{ display: "block", padding: 10, border: "1px solid #dde3ea", borderRadius: 8, marginBottom: 8 }}>
            <input type="radio" name="review-choice" checked={choice === option.id} onChange={() => setChoice(option.id)} /> {option.label}<div style={{ marginLeft: 24 }}>{option.description}</div>
          </label>)}</>}
          <label style={{ display: "block", marginTop: 12 }}>审核备注（可选）<textarea maxLength={4000} value={note} onChange={event => setNote(event.target.value)} rows={3} style={{ display: "block", boxSizing: "border-box", width: "100%", margin: "6px 0 12px", padding: 10, border: "1px solid #cfd7df", borderRadius: 8 }} /></label>
          <div style={{ display: "flex", gap: 10 }}>
            <button style={{ ...button, background: "#176441", color: "white" }} disabled={busy || (!!selected.choices.length && !choice)} onClick={() => void decide("approved")}>通过此变更</button>
            <button style={button} disabled={busy} onClick={() => void decide("rejected")}>拒绝</button>
          </div>
        </fieldset>}
        {selected.status === "pending" && !selected.canDecide && <p>当前事项暂不能处理，请核对分工或方案状态。</p>}
        {selected.decision && <div><h3>审核决定</h3><p>{labels[selected.decision.outcome]} · {selected.decision.actorLabel} · {time(selected.decision.decidedAt)}</p>
          {selected.decision.selectedChoiceId && <p>选择：{selected.choices.find(option => option.id === selected.decision?.selectedChoiceId)?.label}</p>}
          <p style={{ whiteSpace: "pre-wrap" }}>{selected.decision.note}</p></div>}
        {selected.status === "approved" && <div><h3>执行结果</h3><p>{executionLabels[selected.execution.status]}</p><p>{selected.execution.message}</p></div>}
        {selected.status === "superseded" && <p>此方案已失效，请处理最新的待审核事项。</p>}
      </section>}
    </div>}
  </main>;
}

export default defineFrontComponent({
  universalIdentifier: APPROVAL_FRONT_COMPONENT_UNIVERSAL_IDENTIFIER,
  name: "cra-approval-center",
  description: "依据客户规则展示审核事项、证据、决定及执行状态",
  component: ApprovalCenter,
});
