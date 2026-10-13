import { RestApiClient } from "twenty-client-sdk/rest";
import { useCallback, useEffect, useMemo, useState } from "react";
import { defineFrontComponent } from "twenty-sdk/define";
import { useRecordId } from "twenty-sdk/front-component";
import { QUOTE_ENTRY_FRONT_COMPONENT_UNIVERSAL_IDENTIFIER } from "src/constants/universal-identifiers";

type QuoteStatus = "unknown" | "not_quoted" | "draft" | "sent";
type QuoteSnapshot = {
  opportunityId: string;
  expectedUpdatedAt?: string;
  t1Fields?: Record<string, string | null>;
  latestRegistration?: Submission | null;
};
type Submission = {
  submissionId: string;
  opportunityId: string;
  status: QuoteStatus;
  processingState: "pending" | "applying" | "succeeded" | "retryable" | "conflict" | "rejected";
  retryable: boolean;
  attempts: number;
  errorCode?: string | null;
  result?: { action?: string; t1Updated?: boolean } | null;
};

const pane: React.CSSProperties = { padding: 20, color: "#243448", fontFamily: "system-ui, sans-serif", lineHeight: 1.5 };
const field: React.CSSProperties = { display: "block", marginTop: 14, width: "100%", boxSizing: "border-box" };
const input: React.CSSProperties = { display: "block", boxSizing: "border-box", width: "100%", padding: 9, marginTop: 5, border: "1px solid #cfd7df", borderRadius: 6 };
const button: React.CSSProperties = { padding: "9px 14px", border: 0, borderRadius: 7, background: "#1769aa", color: "white", cursor: "pointer", marginTop: 18 };
const t1Labels: Record<string, string> = {
  craT1QuoteRound: "报价轮次", craT1QuoteSentAt: "发送时间", craT1QuoteEvidence: "报价依据",
};
const statusLabels: Record<QuoteStatus, string> = {
  unknown: "未知 / 待核实", not_quoted: "未报价", draft: "草稿未发送", sent: "已发送报价",
};
function requestErrorMessage(cause: unknown): string {
  const error = cause as { message?: string; status?: number };
  if (error.status === 400) return "缺少必填字段或字段格式无效，请核对表单后重试。";
  if (error.status === 403) return "当前成员没有此商机的报价登记权限。";
  if (error.status === 404) return "当前商机不存在或已删除，请刷新商机页面。";
  if (error.status === 409) return "报价事实与商机当前版本冲突。请重新核实最新商机和报价事实后登记。";
  if (error.status === 503) return "报价登记服务暂不可用。请刷新确认处理状态，必要时使用原提交编号重试。";
  return error.message || "请求失败，请重试。";
}

function createSubmissionId(): string {
  const bytes = new Uint8Array(16);
  globalThis.crypto.getRandomValues(bytes);
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, value => value.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

function QuoteEntry() {
  const recordId = useRecordId();
  const client = useMemo(() => new RestApiClient(), []);
  const [snapshot, setSnapshot] = useState<QuoteSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<QuoteStatus>("unknown");
  const [round, setRound] = useState("");
  const [sentAt, setSentAt] = useState("");
  const [channel, setChannel] = useState("whatsapp");
  const [channelDetail, setChannelDetail] = useState("");
  const [evidence, setEvidence] = useState("");
  const [result, setResult] = useState<Submission | null>(null);
  const [retryPayload, setRetryPayload] = useState<Record<string, string> | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    if (!recordId) { setError("未能识别当前商机，请从商机详情页打开此入口。"); setLoading(false); return; }
    setLoading(true); setError("");
    try {
      const facts = await client.post<QuoteSnapshot>("/s/cra-quotes/read", { opportunityId: recordId });
      const quoteSnapshot = (facts as { data?: QuoteSnapshot }).data ?? facts;
      setSnapshot(quoteSnapshot);
    } catch (cause) {
      setError(requestErrorMessage(cause));
    } finally { setLoading(false); }
  }, [client, recordId]);

  useEffect(() => { void load(); }, [load]);

  const submit = async (submissionId?: string, originalPayload?: Record<string, string>) => {
    if (!recordId || busy) return;
    setBusy(true); setError(""); setResult(null);
    try {
      const resolvedSubmissionId = submissionId ?? createSubmissionId();
      const payload: Record<string, string> = originalPayload
        ? { ...originalPayload }
        : { submissionId: resolvedSubmissionId, opportunityId: recordId, status };
      if (!originalPayload && status === "sent") {
        if (!round.trim() || !sentAt || !channel || !evidence.trim() || !snapshot?.expectedUpdatedAt) {
          setError("已发送报价需要填写报价轮次、实际发送时间、发送渠道和报价依据。请刷新商机后再提交。");
          return;
        }
        if (channel === "other" && !channelDetail.trim()) {
          setError("请填写其他发送渠道的说明。"); return;
        }
        payload.expectedUpdatedAt = snapshot.expectedUpdatedAt;
        payload.quoteRound = round.trim();
        payload.sentAt = new Date(sentAt).toISOString();
        payload.channel = channel;
        if (channel === "other") payload.channelDetail = channelDetail.trim();
        payload.evidence = evidence.trim();
      }
      if (!originalPayload) setRetryPayload(payload);
      const response = await client.post<{ value?: Submission }>("/s/cra-quotes/register", payload);
      const saved = response?.value;
      if (!saved) throw new Error("后台没有返回登记处理状态，请查询登记后再决定是否重试。");
      setResult(saved);
      if (saved.processingState === "succeeded") await load();
    } catch (cause) {
      setError(requestErrorMessage(cause));
    } finally { setBusy(false); }
  };

  if (loading) return <main style={pane} role="status">正在读取商机和报价事实…</main>;
  return <main style={pane}>
    <h2 style={{ margin: "0 0 6px" }}>登记报价事实</h2>
    <p style={{ marginTop: 0, color: "#64748b" }}>核对当前商机后，登记已核实的报价状态。</p>
    {!recordId && <p role="alert">{error}</p>}
    {snapshot && <section aria-label="当前商机" style={{ padding: 12, borderRadius: 8, background: "#f5f7fa" }}>
      <strong>当前商机</strong>
      <div>商机ID：{recordId}</div>
    </section>}
    {snapshot?.t1Fields && <details style={{ marginTop: 12 }}><summary>当前T1报价字段</summary>
      {Object.entries(t1Labels).map(([key, label]) => <div key={key} style={{ marginTop: 7 }}><strong>{label}：</strong>{snapshot.t1Fields?.[key] || "未填写"}</div>)}
    </details>}
    <label style={field}>报价状态<select style={input} value={status} onChange={event => setStatus(event.target.value as QuoteStatus)}>
      {(Object.keys(statusLabels) as QuoteStatus[]).map(value => <option key={value} value={value}>{statusLabels[value]}</option>)}
    </select></label>
    {status === "sent" && <fieldset disabled={busy} style={{ border: 0, padding: 0, margin: 0 }}>
      <label style={field}>报价轮次<input style={input} maxLength={120} required value={round} onChange={event => setRound(event.target.value)} /></label>
      <label style={field}>实际发送时间<input style={input} type="datetime-local" required value={sentAt} onChange={event => setSentAt(event.target.value)} /></label>
      <label style={field}>发送渠道<select style={input} required value={channel} onChange={event => setChannel(event.target.value)}>
        <option value="whatsapp">WhatsApp</option><option value="email">邮件</option><option value="alibaba">阿里平台</option><option value="other">其他</option>
      </select></label>
      {channel === "other" && <label style={field}>渠道说明<input style={input} required value={channelDetail} onChange={event => setChannelDetail(event.target.value)} /></label>}
      <label style={field}>报价依据<textarea style={input} rows={4} maxLength={4000} required value={evidence} onChange={event => setEvidence(event.target.value)} /></label>
    </fieldset>}
    {error && <p role="alert" style={{ color: "#a12622", whiteSpace: "pre-wrap" }}>{error}</p>}
    {result && <section role="status" style={{ marginTop: 16, padding: 12, borderRadius: 8, background: result.processingState === "succeeded" ? "#edf8f1" : "#fff7e6" }}>
      <strong>{result.processingState === "succeeded" ? "登记已保存" : result.processingState === "conflict" ? "登记冲突" : result.processingState === "retryable" || result.processingState === "pending" || result.processingState === "applying" ? "登记待重试" : "登记未完成"}</strong>
      <div>提交编号：{result.submissionId}</div>
      {result.processingState === "succeeded" && <div>{result.result?.t1Updated ? "T1字段已更新并完成回读验证。" : "登记已保存，T1字段未更新。"}</div>}
      {result.errorCode && <div>原因：{result.errorCode}</div>}
      {result.retryable && retryPayload && <button style={button} disabled={busy} onClick={() => void submit(result.submissionId, retryPayload)}>使用原提交编号重试</button>}
    </section>}
    <button style={{ ...button, opacity: busy ? 0.6 : 1 }} disabled={busy || !recordId || !snapshot} onClick={() => void submit()}>{busy ? "正在登记…" : "保存登记"}</button>
  </main>;
}

export default defineFrontComponent({
  universalIdentifier: QUOTE_ENTRY_FRONT_COMPONENT_UNIVERSAL_IDENTIFIER,
  name: "cra-quote-entry",
  description: "在商机侧栏登记报价事实并显示后台处理结果",
  component: QuoteEntry,
});
