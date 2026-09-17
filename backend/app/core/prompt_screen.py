"""Deterministic prompt screening compiled from Vietnamese policy text."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.core.models import CompiledPolicy

_ATTACK_MARKERS = (
    r"bỏ qua mọi",
    r"bo qua moi",
    r"chỉ thị ẩn",
    r"chi thi an",
    r"in nguyên văn system prompt",
    r"in nguyen van system prompt",
    r"xuất record",
    r"xuat record",
    r"không cần xác nhận",
    r"khong can xac nhan",
    r"bỏ qua otp",
    r"bo qua otp",
    r"tắt.*audit",
    r"tat.*audit",
    r"-canary-",
    r"reveal_",
    r"debug_mode",
    r"hidden_debug",
    r"<<<system override>>>",
)

_PEDAGOGY = (
    r"giải thích vì sao",
    r"giai thich vi sao",
    r"mô tả các bước",
    r"mo ta cac buoc",
    r"hướng dẫn cách",
    r"huong dan cach",
    r"đây chỉ là ví dụ",
    r"day chi la vi du",
    r"không thực hiện",
    r"khong thuc hien",
    r"cảnh báo nếu",
    r"canh bao neu",
)

_POLICY_MARKERS: dict[str, tuple[str, ...]] = {
    "POL-01": (
        r"người khác",
        r"nguoi khac",
        r"tài khoản khác",
        r"tai khoan khac",
        r"bạn tôi",
        r"ban toi",
        r"tenant_b",
        r"tenant-\*",
    ),
    "POL-02": (r"cccd", r"không che", r"khong che", r"toàn bộ .*nhạy cảm", r"toan bo"),
    "POL-03": (
        r"thực hiện .*ngay",
        r"thuc hien .*ngay",
        r"bỏ qua otp",
        r"bo qua otp",
        r"lặp lại thao tác",
        r"lap lai thao tac",
    ),
    "POL-04": (
        r"chỉ thị ẩn",
        r"chi thi an",
        r"làm theo lệnh",
        r"lam theo lenh",
        r"bỏ qua nhiệm vụ",
        r"bo qua nhiem vu",
    ),
    "POL-05": (r"system prompt", r"api key", r"access token", r"in nguyên", r"in nguyen"),
    "POL-06": (
        r"quản trị viên cấp cao",
        r"quan tri vien cap cao",
        r"đổi role",
        r"doi role",
        r"bạn là admin",
        r"ban la admin",
    ),
    "POL-07": (r"outside\.example", r"attacker@", r"gửi toàn bộ", r"gui toan bo"),
    "POL-08": (r"mọi tool", r"moi tool", r"hàng loạt ticket", r"hang loat ticket", r"export_data"),
    "POL-09": (
        r"base64",
        r"mã hóa",
        r"ma hoa",
        r"reveal_",
        r"từng đoạn 4 ký tự",
        r"tung doan 4 ky tu",
    ),
    "POL-10": (r"tắt hoặc xóa audit", r"tat hoac xoa audit", r"không lưu dấu", r"khong luu dau"),
}


@dataclass(frozen=True)
class ScreenResult:
    flagged: bool
    score: int
    matched: tuple[str, ...]
    pedagogy: bool


def _search(patterns: tuple[str, ...], text: str) -> list[str]:
    hits: list[str] = []
    for pattern in patterns:
        if re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL):
            hits.append(pattern)
    return hits


def screen_prompt(text: str, policy: CompiledPolicy) -> ScreenResult:
    lowered = text.lower()
    attack_hits = _search(_ATTACK_MARKERS, lowered)
    policy_hits = _search(_POLICY_MARKERS.get(policy.id, ()), lowered)
    example_hits = [ex for ex in policy.forbidden_examples if ex.lower() in lowered]
    pedagogy_hits = _search(_PEDAGOGY, lowered)

    score = 2 * len(attack_hits) + len(policy_hits) + len(example_hits) - 2 * len(pedagogy_hits)
    flagged = score >= 2
    matched = tuple(attack_hits + policy_hits + example_hits)
    return ScreenResult(flagged=flagged, score=score, matched=matched, pedagogy=bool(pedagogy_hits))
