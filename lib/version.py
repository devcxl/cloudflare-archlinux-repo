"""Arch Linux 包版本比较（pacman `vercmp` 语义）。

原本这套逻辑在 check-aur-updates / clean-old-packages / download-r2 三个脚本中
整段重复（约 300 行），且分隔符比较方式与 pacman `vercmp` 存在偏差：例如
`1.0.1` 与 `1.0_1` 会被误判为不同，而 `vercmp` 视为相等。本模块作为唯一实现，
统一采用 rpmvercmp 风格的段比较算法（分隔符被忽略，数字段长于字母段，等等），
并以此为准。

调用方只需 `from lib.version import compare_versions, parse_package_filename`。
"""

import re

_PKGNAME_RE = re.compile(r'^[a-zA-Z0-9@._+-]+$')
_ARCH_RE = re.compile(r'-(x86_64|i686|armv7h|aarch64|any)$')


def parse_arch_version(version_string):
    """将 ``[epoch:]pkgver-pkgrel`` 解析为 ``(epoch, pkgver, pkgrel)``。

    epoch 与 pkgrel 为非负整数；pkgver 为字符串（交给段比较算法处理）。
    """
    if version_string is None:
        return (0, '', 0)
    s = str(version_string)
    epoch = 0
    if ':' in s:
        epoch_str, s = s.split(':', 1)
        try:
            epoch = int(epoch_str)
        except ValueError:
            epoch = 0
    if '-' in s:
        pkgver, pkgrel_str = s.rsplit('-', 1)
        try:
            pkgrel = int(pkgrel_str)
        except ValueError:
            pkgrel = 0
    else:
        pkgver = s
        pkgrel = 0
    return (epoch, pkgver, pkgrel)


def _grab(s, pos):
    """从 pos 抓取一个纯数字或纯字母段，返回 ``(段, 新位置)``。"""
    n = len(s)
    start = pos
    if s[pos].isdigit():
        while pos < n and s[pos].isdigit():
            pos += 1
    else:
        while pos < n and s[pos].isalpha():
            pos += 1
    return s[start:pos], pos


def _remaining_sign(s, pos):
    """pacman 语义：一段耗尽后，剩余段若为数字则更长者更新，
    若为字母（预发布后缀）则更长者更旧。返回该侧的相对符号。"""
    n = len(s)
    while pos < n and not s[pos].isalnum():
        pos += 1
    if pos >= n:
        return 0
    return 1 if s[pos].isdigit() else -1


def _segment_cmp(a, b):
    """比较两个 pkgver/pkgrel 段，返回 1 / -1 / 0（pacman vercmp 语义）。"""
    ia = ib = 0
    while True:
        # 跳过非字母数字分隔符
        while ia < len(a) and not a[ia].isalnum():
            ia += 1
        while ib < len(b) and not b[ib].isalnum():
            ib += 1

        a_exh = ia >= len(a)
        b_exh = ib >= len(b)
        if a_exh and b_exh:
            return 0
        if a_exh:
            # b 仍有剩余段：数字→b 更新，字母→b 更旧
            return -_remaining_sign(b, ib)
        if b_exh:
            return _remaining_sign(a, ia)

        sa, ia = _grab(a, ia)
        sb, ib = _grab(b, ib)

        a_dig = sa[0].isdigit()
        b_dig = sb[0].isdigit()
        if a_dig and b_dig:
            sa2 = sa.lstrip('0') or '0'
            sb2 = sb.lstrip('0') or '0'
            if len(sa2) != len(sb2):
                return 1 if len(sa2) > len(sb2) else -1
            if sa2 != sb2:
                return 1 if sa2 > sb2 else -1
        elif a_dig and not b_dig:
            return 1  # 数字段新于字母段
        elif b_dig and not a_dig:
            return -1
        else:  # 两段均为字母
            if sa != sb:
                return 1 if sa > sb else -1
        # 两段相等，继续下一轮


def compare_versions(v1, v2):
    """比较两个完整 Arch 版本字符串。

    ``v1 > v2`` 返回 1，相等返回 0，``v1 < v2`` 返回 -1。
    先比较 epoch，再比较 pkgver（段算法），最后比较 pkgrel（数值）。
    """
    e1, pv1, pr1 = parse_arch_version(v1)
    e2, pv2, pr2 = parse_arch_version(v2)
    if e1 != e2:
        return 1 if e1 > e2 else -1
    seg = _segment_cmp(pv1, pv2)
    if seg != 0:
        return seg
    if pr1 != pr2:
        return 1 if pr1 > pr2 else -1
    return 0


def parse_package_filename(filename):
    """解析 Arch 包文件名，返回 ``(name, version, arch)`` 或 None。"""
    if not filename.endswith('.pkg.tar.zst'):
        return None

    base = filename[:-len('.pkg.tar.zst')]

    arch_match = _ARCH_RE.search(base)
    if not arch_match:
        return None

    arch = arch_match.group(1)
    base = base[:arch_match.start()]

    version_match = re.search(r'-\d+(\.\d+)*', base)
    if not version_match:
        return None

    version = base[version_match.start() + 1:]
    name = base[:version_match.start()]

    if not _PKGNAME_RE.match(name):
        return None

    if not re.match(r'^[a-zA-Z0-9_]+$', arch):
        return None

    return (name, version, arch)
