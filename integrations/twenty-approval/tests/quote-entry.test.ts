import assert from "node:assert/strict";
import test from "node:test";
import { quoteCall, readQuoteConfig, requireQuoteMember } from "../src/lib/quote-entry.ts";

const actor = "ceb518d8-6989-443f-aa75-197021ee139c";
const op = "c6c75dc6-9f6f-4e27-a27c-096c373217af";
const env = {
  CRA_REVIEW_API_URL: "https://quote.example.test", CRA_QUOTE_API_TOKEN: "synthetic-bridge",
  CRA_QUOTE_WORKSPACE_ID: "b7d89ec7-6e83-4216-8e1d-cf16feea5e27",
  CRA_QUOTE_MEMBER_SCOPES: JSON.stringify({ [actor]: [op] }),
};
const config = readQuoteConfig(env);

test("quote configuration denies incomplete, insecure and malformed values", () => {
  for (const change of [{ CRA_QUOTE_API_TOKEN: "" }, { CRA_REVIEW_API_URL: "http://unknown.test" },
    { CRA_QUOTE_MEMBER_SCOPES: "{}" }, { CRA_QUOTE_WORKSPACE_ID: "invalid" },
    { CRA_QUOTE_MEMBER_SCOPES: JSON.stringify({ [actor]: "all" }) }]) {
    assert.throws(() => readQuoteConfig({ ...env, ...change }));
  }
});

test("quote member and target scope checks", () => {
  assert.equal(requireQuoteMember(config, actor, op), actor);
  assert.throws(() => requireQuoteMember(config, null, op));
  assert.throws(() => requireQuoteMember(config, "other", op));
  assert.throws(() => requireQuoteMember(config, actor, "d3b424a0-764b-41c7-81b7-e5e6eb2e8c01"));
});

test("submission passes trusted context identity and persisted retry result", async () => {
  const saved = globalThis.fetch;
  let captured: RequestInit | undefined;
  globalThis.fetch = async (_url, init) => {
    captured = init;
    return new Response(JSON.stringify({ value: { processingState: "retryable", retryable: true } }), { status: 503 });
  };
  try {
    const result = await quoteCall(config, actor, { opportunityId: op, submissionId: op, status: "draft" }, true);
    assert.deepEqual(result, { value: { processingState: "retryable", retryable: true } });
    assert.equal((captured?.headers as Record<string, string>)["x-cra-member-id"], actor);
    assert.equal(captured?.method, "POST");
    assert.equal(captured?.redirect, "error");
    assert.equal((JSON.parse(captured?.body as string) as Record<string, unknown>).actorId, undefined);
  } finally { globalThis.fetch = saved; }
});

test("body cannot override actor and unauthorized member never calls backend", async () => {
  const saved = globalThis.fetch;
  let calls = 0;
  globalThis.fetch = async () => { calls++; throw new Error("unexpected call"); };
  try {
    await assert.rejects(quoteCall(config, actor, { opportunityId: op, actorId: "attacker" }, true));
    await assert.rejects(quoteCall(config, null, { opportunityId: op }, true));
    await assert.rejects(quoteCall(config, actor, { opportunityId: op, workspaceId: "forged" }, true));
    for (const field of ["name", "amount", "stage", "companyId", "pointOfContactId", "ownerId", "updatedBy", "craT1QuoteRound", "query", "fields"]) {
      await assert.rejects(quoteCall(config, actor, { opportunityId: op, [field]: "forged" }, true));
    }
    assert.equal(calls, 0);
  } finally { globalThis.fetch = saved; }
});

test("read uses bounded path and submission lookup", async () => {
  const saved = globalThis.fetch;
  let path = "";
  globalThis.fetch = async url => {
    path = String(url);
    return new Response(JSON.stringify({ value: { processingState: "succeeded" } }), { status: 200 });
  };
  try {
    await quoteCall(config, actor, { opportunityId: op, submissionId: op }, false);
    assert.equal(path, `https://quote.example.test/v1/quotes/opportunities/${op}?submissionId=${op}`);
    await assert.rejects(quoteCall(config, actor, { opportunityId: op, submissionId: "../../other" }, false));
  } finally { globalThis.fetch = saved; }
});

test("gateway does not expose upstream error contents", async () => {
  const saved = globalThis.fetch;
  globalThis.fetch = async () => new Response(JSON.stringify({ error: "secret-key internal-stack" }), { status: 403 });
  try {
    await assert.rejects(quoteCall(config, actor, { opportunityId: op }, false), error =>
      error instanceof Error && error.message.includes("403") && !error.message.includes("secret-key"));
  } finally { globalThis.fetch = saved; }
});
