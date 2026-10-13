"""Synthetic MIME decoding quality checks; never connects to a mailbox or AI."""
from __future__ import annotations

import email
import email.policy
import importlib.util
import json
import pathlib
import base64
import quopri
import sys
from typing import Any


SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
COLLECTOR_PATH = SCRIPT_DIR / "collect-mail.py"
spec = importlib.util.spec_from_file_location("mail_collector_under_test", COLLECTOR_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError("cannot_load_collect_mail")
collector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(collector)

REPLACEMENT = "\ufffd"


def make_mime(
    content: bytes,
    *,
    charset: str | None,
    transfer_encoding: str = "8bit",
) -> bytes:
    content_type = "text/plain"
    if charset is not None:
        content_type += f'; charset="{charset}"'
    headers = [
        f"Content-Type: {content_type}".encode("ascii"),
        f"Content-Transfer-Encoding: {transfer_encoding}".encode("ascii"),
    ]
    return b"\r\n".join(headers) + b"\r\n\r\n" + content


def simulate_collect_mail(
    raw_message: bytes,
    *,
    body_octets_override: int | None = None,
) -> dict[str, Any]:
    """Run the collector's MIME metadata selection and decode_part logic."""
    message = email.message_from_bytes(raw_message, policy=email.policy.default)
    content_type = message.get_content_type()
    subtype = message.get_content_subtype()
    charset = message.get_content_charset()
    transfer_encoding = str(message.get("Content-Transfer-Encoding", "7bit")).lower()
    encoded_payload = raw_message.split(b"\r\n\r\n", 1)[1]
    declared_octets = (
        body_octets_override if body_octets_override is not None else len(encoded_payload)
    )

    # Match the single text/plain BODYSTRUCTURE shape consumed by text_parts().
    params = ["CHARSET", charset] if charset else None
    structure = [
        "TEXT",
        subtype.upper(),
        params,
        None,
        None,
        transfer_encoding,
        declared_octets,
        1,
    ]
    parts = collector.text_parts(structure)
    chosen = [part for part in parts if part["subtype"] == "plain"]
    decoded_parts: list[str] = []
    decode_errors: list[bool] = []
    for part in chosen:
        decoded, decode_error = collector.decode_part_with_status(encoded_payload, part)
        decoded_parts.append(decoded)
        decode_errors.append(decode_error)
    complete = collector.text_completeness(chosen, decode_errors)

    return {
        "content_type": content_type,
        "charset_declared": charset,
        "text": "\n".join(decoded_parts),
        "completeness": complete,
    }


def run_case(
    name: str,
    raw_message: bytes,
    *,
    expected_fragment: str,
    expected_completeness: str = "text_only",
    expected_replacement: bool = False,
    body_octets_override: int | None = None,
) -> dict[str, Any]:
    result = simulate_collect_mail(raw_message, body_octets_override=body_octets_override)
    has_replacement = REPLACEMENT in result["text"]
    decoded_as_expected = expected_fragment in result["text"]
    checks = {
        "expected_text_decoded": decoded_as_expected,
        "replacement_character_as_expected": has_replacement == expected_replacement,
        "completeness_as_expected": result["completeness"] == expected_completeness,
    }
    if expected_completeness == "text_decode_error":
        checks["text_decode_error_state_supported"] = result["completeness"] == "text_decode_error"
    return {
        "case": name,
        "charset_declared": result["charset_declared"],
        "replacement_character": has_replacement,
        "completeness_observed": result["completeness"],
        "completeness_expected": expected_completeness,
        "text_decode_error_supported": result["completeness"] == "text_decode_error",
        "checks": checks,
        "passed": all(checks.values()),
    }


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    utf8_text = "询价：产品A，数量10件"
    gbk_text = "产品咨询：请提供规格"
    qp_text = "售后问题：请协助确认"
    b64_text = "样品申请：需要两个样品"
    japanese_text = "製品の仕様を教えてください"
    russian_text = "Пожалуйста, пришлите цену и характеристики"

    damaged_payload = b"Broken UTF-8: \xff\xfe quantity 10"
    cases = [
        run_case(
            "UTF-8正文",
            make_mime(utf8_text.encode("utf-8"), charset="utf-8"),
            expected_fragment=utf8_text,
        ),
        run_case(
            "中文GBK正文",
            make_mime(gbk_text.encode("gbk"), charset="gbk"),
            expected_fragment=gbk_text,
        ),
        run_case(
            "quoted-printable编码正文",
            make_mime(
                quopri.encodestring(qp_text.encode("utf-8")),
                charset="utf-8",
                transfer_encoding="quoted-printable",
            ),
            expected_fragment=qp_text,
        ),
        run_case(
            "Base64编码正文",
            make_mime(
                base64.b64encode(b64_text.encode("utf-8")),
                charset="utf-8",
                transfer_encoding="base64",
            ),
            expected_fragment=b64_text,
        ),
        run_case(
            "日文正文",
            make_mime(japanese_text.encode("utf-8"), charset="utf-8"),
            expected_fragment=japanese_text,
        ),
        run_case(
            "俄文正文",
            make_mime(russian_text.encode("utf-8"), charset="utf-8"),
            expected_fragment=russian_text,
        ),
        run_case(
            "损坏字符输入",
            make_mime(damaged_payload, charset="utf-8"),
            expected_fragment=f"Broken UTF-8: {REPLACEMENT}{REPLACEMENT} quantity 10",
            expected_completeness="text_decode_error",
            expected_replacement=True,
        ),
        run_case(
            "未知MIME charset",
            make_mime("未知字符集".encode("utf-8"), charset="x-unknown-charset"),
            expected_fragment="未知字符集",
            expected_completeness="text_decode_error",
        ),
        run_case(
            "正文含U+FFFD",
            make_mime(f"型号A{REPLACEMENT}B".encode("utf-8"), charset="utf-8"),
            expected_fragment=f"型号A{REPLACEMENT}B",
            expected_completeness="text_decode_error",
            expected_replacement=True,
        ),
        run_case(
            "未声明charset输入",
            make_mime(utf8_text.encode("utf-8"), charset=None),
            expected_fragment=utf8_text,
        ),
        run_case(
            "超长正文状态",
            make_mime(b"truncated synthetic body", charset="utf-8"),
            expected_fragment="truncated synthetic body",
            expected_completeness="text_truncated",
            body_octets_override=collector.MAX_TEXT_BYTES + 1,
        ),
    ]

    failed = [case for case in cases if not case["passed"]]
    report = {
        "title": "邮件编码质量测试报告",
        "scope": "合成MIME输入；复用collect-mail.py中的text_parts/decode_part逻辑",
        "real_mail_read": False,
        "ai_calls": 0,
        "crm_writes": 0,
        "case_count": len(cases),
        "passed_count": len(cases) - len(failed),
        "failed_count": len(failed),
        "text_decode_error_supported": any(
            case["completeness_observed"] == "text_decode_error" for case in cases
        ),
        "results": cases,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
