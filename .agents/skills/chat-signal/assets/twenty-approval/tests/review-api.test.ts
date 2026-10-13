import assert from "node:assert/strict";
import { afterEach, test } from "node:test";
import { parseDecision, parsePage, parseRequest } from "../src/lib/contracts.ts";
import type { ReviewRequest } from "../src/lib/contracts.ts";
import { decideReview, listReviews, readConfig } from "../src/lib/review-api.ts";

const config = readConfig({ CRA_REVIEW_API_URL: "https://review.example.test", CRA_REVIEW_API_TOKEN: "synthetic-token", CRA_REVIEW_WORKSPACE_ID: "customer-workspace", CRA_REVIEWER_MEMBER_IDS: "member-a" });
const originalFetch = globalThis.fetch;
afterEach(() => { globalThis.fetch = originalFetch; });
function request(): ReviewRequest {
  return {
    id: "review-1", workspaceId: config.workspaceId, planDigest: "a".repeat(64),
    ruleId: "customer-confirmed-discount", ruleVersion: "business-7",
    title: "确认报价折扣", reason: "本次折扣达到企业确认的审核条件", status: "pending",
    createdAt: "2026-09-01T00:00:00Z", target: { objectLabel: "报价", recordLabel: "合成报价" },
    changes: [{ fieldLabel: "折扣", before: "5%", after: "12%" }],
    evidence: [{ sourceLabel: "合成消息", reference: "sample-1", excerpt: "希望调整报价" }],
    choices: [], decision: null, execution: { status: "not_started", message: "等待审核" }, canDecide: true,
  };
}
const input = () => ({ id: "review-1", planDigest: "a".repeat(64), outcome: "approved", note: "", selectedChoiceId: null });

test("企业自定义审核原因可显示，不依赖作者三种动作或测试工作区", async () => {
  globalThis.fetch = async (url, init) => {
    assert.match(String(url), /status=pending&limit=50/);
    assert.equal((init?.headers as Record<string, string>)["x-cra-workspace-id"], config.workspaceId);
    return Response.json({ values: [request()], nextCursor: "opaque-cursor" });
  };
  const page = await listReviews(config, "member-a");
  assert.equal(page.values[0].ruleId, "customer-confirmed-discount");
  assert.equal(page.nextCursor, "opaque-cursor");
});

test("未登录、非审核成员不会访问后台", async () => {
  globalThis.fetch = async () => { assert.fail("must not call backend"); };
  await assert.rejects(listReviews(config, null), /权限/);
  await assert.rejects(decideReview(config, "outsider", input()), /权限/);
});

test("浏览器不能伪造审核人、工作区、计划动作或执行权限", async () => {
  globalThis.fetch = async (_url, init) => {
    assert.equal((init?.headers as Record<string, string>)["x-cra-reviewer-id"], "member-a");
    assert.equal(init?.redirect, "error");
    assert.deepEqual(JSON.parse(String(init?.body)), input());
    return Response.json({ value: { ...request(), status: "approved", canDecide: false,
      decision: { outcome: "approved", actorLabel: "审核员", decidedAt: "2026-09-01T01:00:00Z", note: "", selectedChoiceId: null },
      execution: { status: "queued", message: "等待执行" } } });
  };
  const response = await decideReview(config, "member-a", { ...input(), actor: "owner", workspaceId: "other", changes: [], canDecide: true });
  assert.equal(response.value.execution.status, "queued");
});

test("跨工作区、缺少工作区和损坏列表均拒绝", async () => {
  for (const value of [{ ...request(), workspaceId: "other" }, { ...request(), workspaceId: undefined }]) {
    globalThis.fetch = async () => Response.json({ values: [value], nextCursor: null });
    await assert.rejects(listReviews(config, "member-a"), /工作区/);
  }
  assert.throws(() => parsePage({ values: [], nextCursor: 3 }));
  assert.throws(() => parsePage({ values: [request(), request()], nextCursor: null }));
});

test("拒绝或待审不能声称执行成功，批准可以等待人工操作", () => {
  assert.throws(() => parseRequest({ ...request(), execution: { status: "succeeded", message: "" } }));
  const approved = { ...request(), status: "approved", canDecide: false,
    decision: { outcome: "approved", actorLabel: "审核员", decidedAt: "2026-09-01T01:00:00Z", note: "", selectedChoiceId: null },
    execution: { status: "manual_required", message: "由客户指定负责人在 CRM 中完成" } };
  assert.equal(parseRequest(approved).execution.status, "manual_required");
  assert.throws(() => parseRequest({ ...approved, status: "rejected" }));
});

test("409 要求刷新，不盲目重试决定；上游错误不泄漏凭据", async () => {
  let calls = 0;
  globalThis.fetch = async () => { calls++; return Response.json({ error: "private-secret" }, { status: 409 }); };
  await assert.rejects(decideReview(config, "member-a", input()), /刷新/);
  assert.equal(calls, 1);
  globalThis.fetch = async () => Response.json({ error: "private-secret" }, { status: 500 });
  await assert.rejects(listReviews(config, "member-a"), error => error instanceof Error && !error.message.includes("private-secret"));
});

test("拒绝未知状态、路径注入、无效摘要和空成员配置", () => {
  assert.throws(() => parseDecision({ ...input(), id: "../other" }));
  assert.throws(() => parseDecision({ ...input(), planDigest: "old" }));
  assert.throws(() => parseDecision({ ...input(), outcome: "rejected", selectedChoiceId: "choice" }));
  assert.throws(() => readConfig({}));
  for (const url of ["http://review.example.test", "https://token@review.example.test", "https://review.example.test?token=x"]) {
    assert.throws(() => readConfig({ CRA_REVIEW_API_URL: url }));
  }
});

test("重复、无效候选与不匹配的决定返回不能被展示为成功", async () => {
  const choice = { id: "choice-1", label: "合成客户", description: "相同邮箱" };
  assert.throws(() => parseRequest({ ...request(), choices: [choice, choice] }));
  globalThis.fetch = async () => Response.json({ value: { ...request(), id: "different", status: "approved", canDecide: false,
    decision: { outcome: "approved", actorLabel: "审核员", decidedAt: "2026-09-01T01:00:00Z", note: "", selectedChoiceId: null } } });
  await assert.rejects(decideReview(config, "member-a", input()), /不符/);
});
