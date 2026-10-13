"""Read-only health aggregation for the CRA local services.

This module intentionally avoids the order report refresh endpoint, the
authenticated review error endpoint, and all recovery/startup scripts.
"""
from __future__ import annotations

import json
import math
import os
import subprocess
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "runtime" / "unified-health-status.json"
REPORT = ROOT / "records" / "order-report" / "latest-report.json"
FX_CACHE = ROOT / "records" / "order-report" / "fx-cache.json"
WHATSAPP_STATUS = ROOT / "records" / "chat-signal" / "whatsapp-status.json"
REVIEW_STARTUP_STATUS = ROOT / "runtime" / "review-startup-status.json"
EVOLUTION_ENV = ROOT / "deployment" / "evolution" / ".env"

TWENTY_URL = "http://127.0.0.1:3000/healthz"
ORDER_REPORT_URL = "http://127.0.0.1:3001/health"
REVIEW_ERRORS_URL = "http://127.0.0.1:3002/v1/review/errors"
EVOLUTION_CONNECTION_URL = (
    "http://127.0.0.1:8082/instance/connectionState/wingcore-business"
)

DISTRO = "CRA-Ubuntu-24.04"
REPORT_MAX_AGE = timedelta(minutes=15)
SHORT_STATUS_MAX_AGE = timedelta(minutes=5)
FX_RETRY_GRACE_SECONDS = 60 * 60
HONG_KONG = timezone(timedelta(hours=8), "Asia/Hong_Kong")
VALID_STATES = {"healthy", "warning", "failed"}


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso_time(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds")


def make_check(
    service: str,
    status: str,
    source: str,
    reason: str,
    check_time: str | None = None,
) -> dict[str, str]:
    if status not in VALID_STATES:
        raise ValueError("invalid health state")
    return {
        "service": service,
        "status": status,
        "check_time": check_time or iso_time(now_utc()),
        "source": source,
        "reason": reason,
    }


def summarize(checks: list[dict[str, str]], checked_at: datetime | None = None) -> dict[str, Any]:
    states = [item.get("status") for item in checks]
    if not checks or any(state not in VALID_STATES for state in states):
        overall = "failed"
    elif "failed" in states:
        overall = "failed"
    elif "warning" in states:
        overall = "warning"
    else:
        overall = "healthy"
    return {
        "status": overall,
        "check_time": iso_time(checked_at or now_utc()),
        "services": checks,
    }


def parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=HONG_KONG).astimezone(timezone.utc)
    return parsed.astimezone(timezone.utc)


def age_assessment(
    timestamp: Any,
    now: datetime,
    max_age: timedelta,
    label: str,
) -> tuple[str, str]:
    parsed = parse_time(timestamp)
    if parsed is None:
        return "warning", f"{label}缺少有效时间戳。"
    age = now.astimezone(timezone.utc) - parsed
    if age < timedelta(minutes=-2):
        return "warning", f"{label}时间晚于当前检查时间，时间同步需核对。"
    if age > max_age:
        minutes = int(age.total_seconds() // 60)
        return "warning", f"{label}已过期（约 {minutes} 分钟）。"
    return "healthy", f"{label}在有效期内。"


def read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def get_json(url: str, headers: dict[str, str] | None = None, timeout: float = 3.0) -> tuple[int, Any]:
    request = urllib.request.Request(url, headers=headers or {}, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            code = response.status
            try:
                return code, json.loads(response.read().decode("utf-8"))
            except (UnicodeError, json.JSONDecodeError):
                return code, None
    except urllib.error.HTTPError as error:
        # Read no response body: health output should not contain private data.
        return error.code, None


def check_twenty() -> dict[str, str]:
    source = f"GET {TWENTY_URL}"
    try:
        code, body = get_json(TWENTY_URL)
    except (OSError, TimeoutError, urllib.error.URLError) as error:
        return make_check("Twenty CRM", "failed", source,
                          f"健康接口不可达（{type(error).__name__}）。")
    if code != 200:
        return make_check("Twenty CRM", "failed", source,
                          f"健康接口返回 HTTP {code}。")
    if not isinstance(body, dict) or body.get("status") != "ok":
        return make_check("Twenty CRM", "warning", source,
                          "接口返回 200，但健康响应内容不完整或状态非 ok。")
    return make_check("Twenty CRM", "healthy", source,
                      "健康接口返回 HTTP 200，状态为 ok。")


def check_order_report(now: datetime) -> dict[str, str]:
    source = f"GET {ORDER_REPORT_URL}; read {REPORT.relative_to(ROOT).as_posix()}"
    try:
        code, body = get_json(ORDER_REPORT_URL)
    except (OSError, TimeoutError, urllib.error.URLError) as error:
        return make_check("订单报表服务", "failed", source,
                          f"只读健康接口不可达（{type(error).__name__}）。")
    if code != 200:
        return make_check("订单报表服务", "failed", source,
                          f"只读健康接口返回 HTTP {code}。")
    if not isinstance(body, dict) or body.get("status") != "ok":
        return make_check("订单报表服务", "warning", source,
                          "健康接口返回 200，但响应内容不完整。")

    report = read_json(REPORT)
    if report is None:
        return make_check("订单报表服务", "warning", source,
                          "服务接口可用，但报表状态文件缺失或无法解析。")
    freshness, freshness_reason = age_assessment(
        report.get("generatedAt"), now, REPORT_MAX_AGE, "报表快照"
    )
    if freshness != "healthy":
        return make_check("订单报表服务", "warning", source,
                          f"健康接口可用；{freshness_reason}")
    if report.get("error"):
        return make_check("订单报表服务", "warning", source,
                          "健康接口可用，但最近报表记录了读取错误。")
    warnings = report.get("warnings")
    warning_count = len(warnings) if isinstance(warnings, list) else 0
    reason = "健康接口正常，最近报表快照在有效期内且无服务错误。"
    if warning_count:
        reason += f"另有 {warning_count} 条报表业务警告，不作为服务故障判定。"
    return make_check("订单报表服务", "healthy", source, reason)


def check_review_backend(now: datetime) -> dict[str, str]:
    source = (
        f"GET {REVIEW_ERRORS_URL} (unauthenticated); "
        f"read {REVIEW_STARTUP_STATUS.relative_to(ROOT).as_posix()}"
    )
    try:
        code, _ = get_json(REVIEW_ERRORS_URL)
    except (OSError, TimeoutError, urllib.error.URLError) as error:
        return make_check("审核后台", "failed", source,
                          f"审核接口不可达（{type(error).__name__}）。")
    if code >= 500 or code in (404, 408, 429):
        return make_check("审核后台", "failed", source,
                          f"审核接口返回 HTTP {code}。")

    startup = read_json(REVIEW_STARTUP_STATUS)
    freshness, freshness_reason = age_assessment(
        startup.get("checkedAt") if startup else None,
        now,
        SHORT_STATUS_MAX_AGE,
        "审核后台启动状态",
    )
    if code not in (401, 403):
        return make_check("审核后台", "warning", source,
                          f"服务有响应（HTTP {code}），但匿名探测结果与预期的授权拒绝不符；未读取任何审核数据。")
    if freshness != "healthy":
        return make_check("审核后台", "warning", source,
                          f"接口按预期拒绝匿名请求；{freshness_reason}")
    if not startup or startup.get("ok") is not True:
        return make_check("审核后台", "warning", source,
                          "接口按预期拒绝匿名请求，但最近启动记录未确认成功。")
    return make_check(
        "审核后台",
        "warning",
        source,
        "接口可达且匿名访问被拒绝；没有独立无副作用探针，未验证审核数据库及系统异常队列。",
    )


def read_env_value(path: Path, key: str) -> str | None:
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except (OSError, UnicodeError):
        return None
    prefix = key + "="
    for line in lines:
        candidate = line.strip()
        if candidate.startswith(prefix) and not candidate.startswith("#"):
            value = candidate[len(prefix):].strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            return value or None
    return None


def check_whatsapp(now: datetime) -> dict[str, str]:
    source = (
        f"GET {EVOLUTION_CONNECTION_URL} (authenticated, read-only); "
        f"read {WHATSAPP_STATUS.relative_to(ROOT).as_posix()}"
    )
    api_key = read_env_value(EVOLUTION_ENV, "AUTHENTICATION_API_KEY")
    if not api_key:
        return make_check("WhatsApp Evolution API", "warning", source,
                          "本地 API 凭据不可用，无法执行认证状态探测；未输出或保存凭据。")
    headers = {
        "apikey": api_key,
        "Content-Type": "application/json",
        "Origin": "http://localhost:8082",
    }
    try:
        code, body = get_json(EVOLUTION_CONNECTION_URL, headers=headers, timeout=5.0)
    except (OSError, TimeoutError, urllib.error.URLError) as error:
        return make_check("WhatsApp Evolution API", "failed", source,
                          f"认证状态接口不可达（{type(error).__name__}）。")
    if code >= 500 or code in (404, 408, 429):
        return make_check("WhatsApp Evolution API", "failed", source,
                          f"认证状态接口返回 HTTP {code}。")
    if code in (401, 403):
        return make_check("WhatsApp Evolution API", "warning", source,
                          "API 有响应，但认证未通过；连接状态无法确认。")
    if code != 200 or not isinstance(body, dict):
        return make_check("WhatsApp Evolution API", "warning", source,
                          f"API 有响应（HTTP {code}），但状态响应不完整。")

    instance = body.get("instance")
    if not isinstance(instance, dict):
        return make_check("WhatsApp Evolution API", "warning", source,
                          "API 返回 200，但连接状态响应不完整。")
    connection_state = instance.get("state")
    if connection_state != "open":
        return make_check("WhatsApp Evolution API", "warning", source,
                          "Evolution API 可用，但 WhatsApp 实例当前未连接。")

    collector = read_json(WHATSAPP_STATUS)
    freshness, freshness_reason = age_assessment(
        collector.get("finished_at") if collector else None,
        now,
        SHORT_STATUS_MAX_AGE,
        "WhatsApp 采集状态",
    )
    if freshness != "healthy":
        return make_check("WhatsApp Evolution API", "warning", source,
                          f"WhatsApp 实例已连接；{freshness_reason}")
    if not collector or collector.get("status") != "ok":
        return make_check("WhatsApp Evolution API", "warning", source,
                          "WhatsApp 实例已连接，但最近采集状态未成功。")
    if collector.get("connection_state") != "open":
        return make_check("WhatsApp Evolution API", "warning", source,
                          "API 当前连接正常，但最近采集记录显示连接状态不一致。")
    return make_check("WhatsApp Evolution API", "healthy", source,
                      "只读认证状态接口返回 HTTP 200，实例状态为 open，采集状态在有效期内。")


def decode_command_output(value: str) -> str:
    # WSL list output can contain UTF-16-style NUL bytes through a text pipe.
    return value.replace("\x00", "").replace("\ufeff", "").strip()


def run_readonly(argv: list[str], timeout: float = 8.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def wsl_project_path(project: str) -> str:
    if os.name == "nt":
        drive = ROOT.drive[:1].lower()
        suffix = ROOT.as_posix()[2:]
        return f"/mnt/{drive}{suffix}/deployment/{project}"
    return str(ROOT / "deployment" / project)


def parse_compose_rows(output: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    text = decode_command_output(output)
    if not text:
        return rows
    try:
        value = json.loads(text)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            return [value]
    except json.JSONDecodeError:
        pass
    for line in text.splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            rows.append(value)
        elif isinstance(value, list):
            rows.extend(item for item in value if isinstance(item, dict))
    return rows


def check_docker() -> tuple[dict[str, str], dict[str, dict[str, Any]]]:
    source = "wsl.exe --list --running; docker compose ps --all --format json (read-only)"
    states: dict[str, dict[str, Any]] = {}
    try:
        listed = run_readonly(["wsl.exe", "--list", "--running", "--quiet"])
    except (OSError, subprocess.TimeoutExpired) as error:
        return (make_check("Docker 服务", "failed", source,
                           f"无法读取 WSL/Docker 运行状态（{type(error).__name__}）。"), states)
    if listed.returncode != 0:
        return (make_check("Docker 服务", "failed", source,
                           f"WSL 运行状态查询失败（退出码 {listed.returncode}）。"), states)
    distro_names = decode_command_output(listed.stdout).lower().splitlines()
    if not any(DISTRO.lower() == name.strip().lower() for name in distro_names):
        return (make_check("Docker 服务", "failed", source,
                           f"目标 WSL 发行版 {DISTRO} 未运行；未尝试启动或恢复服务。"), states)

    projects = {
        "twenty": {"server", "worker", "db", "redis"},
        "evolution": {"api", "db", "redis"},
    }
    unverified_health: list[str] = []
    for project, expected in projects.items():
        argv = [
            "wsl.exe", "-d", DISTRO, "-u", "root", "--cd", wsl_project_path(project),
            "--", "docker", "compose", "ps", "--all", "--format", "json",
        ]
        try:
            result = run_readonly(argv, timeout=12.0)
        except (OSError, subprocess.TimeoutExpired) as error:
            return (make_check("Docker 服务", "failed", source,
                               f"{project} Compose 状态查询失败（{type(error).__name__}）。"), states)
        if result.returncode != 0:
            return (make_check("Docker 服务", "failed", source,
                               f"{project} Compose 状态查询失败（退出码 {result.returncode}）。"), states)
        rows = parse_compose_rows(result.stdout)
        by_service = {str(row.get("Service", "")): row for row in rows}
        missing = sorted(expected - set(by_service))
        if missing:
            return (make_check("Docker 服务", "failed", source,
                               f"{project} 缺少必需容器状态：{', '.join(missing)}。"), states)
        for service in sorted(expected):
            row = by_service[service]
            key = f"{project}.{service}"
            states[key] = row
            container_state = str(row.get("State", "")).lower()
            health = str(row.get("Health", "")).lower()
            if container_state != "running":
                return (make_check("Docker 服务", "failed", source,
                                   f"{project}/{service} 容器状态为 {container_state or 'unknown'}。"), states)
            if health == "unhealthy":
                return (make_check("Docker 服务", "failed", source,
                                   f"{project}/{service} 容器健康检查失败。"), states)
            if health in ("starting", "starting (health: starting)"):
                unverified_health.append(f"{project}/{service} health=starting")
            elif not health:
                unverified_health.append(f"{project}/{service} 未配置 Docker healthcheck")
            elif health != "healthy":
                unverified_health.append(f"{project}/{service} health={health}")

    if unverified_health:
        reason = "所有必需容器均在运行；部分容器缺少或尚未通过 Docker healthcheck：" + "; ".join(unverified_health) + "。"
        return (make_check("Docker 服务", "warning", source, reason), states)
    return (make_check("Docker 服务", "healthy", source,
                       "Twenty 与 Evolution 所需容器均在运行且 Docker healthcheck 通过。"), states)


def evaluate_fx_cache(cache: dict[str, Any] | None, now: datetime) -> tuple[str, str]:
    if cache is None:
        return "failed", "汇率缓存缺失或无法解析。"
    rate = cache.get("rate")
    try:
        numeric_rate = float(rate)
    except (TypeError, ValueError):
        numeric_rate = 0.0
    if not math.isfinite(numeric_rate) or not numeric_rate > 0:
        return "failed", "汇率缓存没有有效正数汇率。"
    source_date = cache.get("sourceDate")
    if not isinstance(source_date, str):
        return "warning", "汇率来源日期缺失，无法判断数据是否为当天。"
    today_hk = now.astimezone(HONG_KONG).date().isoformat()
    if source_date < today_hk:
        return "warning", f"汇率来源日期为 {source_date}，早于香港当前日期 {today_hk}。"
    if source_date > today_hk:
        return "warning", "汇率来源日期晚于香港当前日期，时间或源数据需核对。"
    if cache.get("expired") is True or cache.get("lastError") or cache.get("error"):
        return "warning", "仍有汇率缓存，但最近更新记录标记过期或错误。"
    try:
        next_update = float(cache.get("nextUpdateUnix"))
    except (TypeError, ValueError):
        return "warning", "汇率缓存缺少有效的下次更新时间。"
    if now.timestamp() > next_update + FX_RETRY_GRACE_SECONDS:
        return "warning", "已超过数据源更新时间及一小时重试宽限，尚无更新缓存。"
    return "healthy", f"汇率缓存有效，来源日期为香港当前日期 {today_hk}，没有已记录的更新错误。"


def check_fx(now: datetime) -> dict[str, str]:
    source = f"read {FX_CACHE.relative_to(ROOT).as_posix()} (no refresh)"
    cache = read_json(FX_CACHE)
    status, reason = evaluate_fx_cache(cache, now)
    return make_check("汇率缓存", status, source, reason)


def collect_checks(now: datetime | None = None) -> list[dict[str, str]]:
    checked_at = now or now_utc()
    docker_check, _docker_states = check_docker()
    return [
        check_twenty(),
        check_order_report(checked_at),
        check_review_backend(checked_at),
        check_whatsapp(checked_at),
        docker_check,
        check_fx(checked_at),
    ]


def write_status(status: dict[str, Any], destination: Path = OUTPUT) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(status, ensure_ascii=False, indent=2) + "\n"
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="\n", dir=destination.parent,
            prefix=destination.name + ".", suffix=".tmp", delete=False,
        ) as temporary:
            temporary_name = temporary.name
            temporary.write(data)
        os.replace(temporary_name, destination)
    finally:
        if temporary_name and os.path.exists(temporary_name):
            os.unlink(temporary_name)


def main() -> int:
    checked_at = now_utc()
    status = summarize(collect_checks(checked_at), checked_at)
    write_status(status)
    print(json.dumps({
        "status": status["status"],
        "check_time": status["check_time"],
        "output": OUTPUT.relative_to(ROOT).as_posix(),
    }, ensure_ascii=True))
    return 1 if status["status"] == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
