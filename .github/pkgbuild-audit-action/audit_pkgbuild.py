#!/usr/bin/env python3
"""
PKGBUILD 安全审计脚本

审计范围：
  - PKGBUILD（含架构特定 source/sha 数组）
  - 补丁文件（*.patch / *.diff）
  - 辅助脚本与配置文件（*.install / *.sh / *.service / *.desktop / *.js / *.py 等）

检查 PKGBUILD 文件中的供应链攻击模式，分级处理：
  CRITICAL / ERROR → 阻断构建
  WARNING          → 仅告警，不阻断

用法:
  SOURCE_URL=... PACKAGE_NAME=... CONFIG_PATH=... python3 audit_pkgbuild.py
"""

import os
import re
import shutil
import sys
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.parse import urlparse

CRITICAL = "CRITICAL"
ERROR = "ERROR"
WARNING = "WARNING"


def _parse_bash_array_body(body):
    """解析 bash 数组体，返回条目列表（支持引号、转义、嵌套括号）。"""
    items = []
    current = []
    in_quote = None
    i = 0
    while i < len(body):
        ch = body[i]
        if in_quote:
            if ch == '\\' and i + 1 < len(body):
                current.append(body[i + 1])
                i += 2
                continue
            if ch == in_quote:
                in_quote = None
            else:
                current.append(ch)
        else:
            if ch in ("'", '"'):
                in_quote = ch
            elif ch == '\n' or ch == ' ':
                if current:
                    items.append(''.join(current).strip())
                    current = []
            else:
                current.append(ch)
        i += 1
    if current:
        items.append(''.join(current).strip())
    return [it for it in items if it and not it.startswith('#')]


def _extract_bash_array_variants(content, varname):
    """提取指定数组及其架构特定变体（如 source_x86_64、sha256sums_aarch64）的全部条目。"""
    pattern = re.compile(
        r'\b' + re.escape(varname) + r'(?:_[A-Za-z0-9_]+)?\s*=\s*\(((?:[^()]|\([^)]*\))*)\)',
        re.DOTALL
    )
    items = []
    for match in pattern.finditer(content):
        items.extend(_parse_bash_array_body(match.group(1)))
    return items


def extract_sources(content):
    """提取 source 及所有架构特定 source 数组（source_x86_64、source_aarch64 等）。"""
    return _extract_bash_array_variants(content, 'source')


def extract_checksums(content):
    """提取所有校验和数组（含架构特定变体），返回 {变量名: [值列表]}。"""
    checksum_vars = [
        'sha256sums', 'sha512sums', 'sha384sums', 'sha224sums',
        'sha1sums', 'md5sums', 'b2sums',
    ]
    result = {}
    for v in checksum_vars:
        values = _extract_bash_array_variants(content, v)
        if values:
            result[v] = values
    return result


def extract_source_urls(sources):
    """从 source 列表中提取远程 URL（去掉 filename:: 前缀和变量引用）。"""
    urls = []
    for src in sources:
        m = re.search(r'::(https?://\S+)', src)
        if m:
            urls.append(m.group(1))
            continue
        m = re.match(r'^(https?://\S+)', src)
        if m:
            urls.append(m.group(1))
    return urls


def _extract_static_pkgbuild_variables(content):
    """提取可安全替换的静态 PKGBUILD 标量，不执行 shell。

    包含标准变量（pkgname/pkgver/pkgrel/epoch）以及自定义静态标量
    （如 _npmname=wrangler），用于展开 source URL 中的变量引用。
    """
    variables = {}
    for name in ('pkgname', 'pkgver', 'pkgrel', 'epoch'):
        match = re.search(
            rf'^\s*{name}\s*=\s*(?:"([^"\n]*)"|\'([^\'\n]*)\'|([^\s#]+))',
            content,
            re.MULTILINE,
        )
        if match:
            variables[name] = next(value for value in match.groups() if value is not None)
    # 自定义静态标量：仅接受纯字符串/数字赋值，不包含命令替换等动态内容。
    # 若同一变量在文件其他位置被动态赋值（含 $、反引号、命令替换），
    # 则放弃展开该变量，避免替换结果与 bash 实际求值不一致。
    custom_candidates = {}
    dynamic_names = set()
    for match in re.finditer(
        r'^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?:"([^"\n]*)"|\'([^\'\n]*)\'|([^\s#(][^\s#]*))',
        content,
        re.MULTILINE,
    ):
        name = match.group(1)
        value = next(v for v in match.groups()[1:] if v is not None)
        if re.search(r'[$`\\]|\$\{', value):
            dynamic_names.add(name)
            custom_candidates.pop(name, None)
        elif name not in custom_candidates:
            custom_candidates[name] = value
    for name, value in custom_candidates.items():
        if name not in variables and name not in dynamic_names:
            variables[name] = value
    return variables


def _expand_static_pkgbuild_variables(value, variables):
    """仅展开已解析的静态变量，保留未知变量供白名单拒绝。"""
    for name, replacement in variables.items():
        value = re.sub(
            rf'\$(?:\{{{name}\}}|{name}\b)',
            lambda _: replacement,
            value,
        )
    return value


def clone_repository(source_url, repo_dir, attempts=3):
    """克隆源码仓库，并对瞬时网络失败进行有限重试。"""
    last_error = ''
    for attempt in range(1, attempts + 1):
        shutil.rmtree(repo_dir, ignore_errors=True)
        try:
            result = subprocess.run(
                ['git', 'clone', '--depth', '1', source_url, repo_dir],
                capture_output=True, text=True, timeout=60
            )
            if result.returncode == 0:
                return True, ''
            last_error = (result.stderr or '').strip()
        except (OSError, subprocess.TimeoutExpired) as exc:
            last_error = str(exc)

        if attempt < attempts:
            print(f"::warning::git clone 失败，第 {attempt + 1} 次重试", file=sys.stderr)
            time.sleep(attempt * 5)

    return False, last_error


def extract_patch_additions(content):
    """提取补丁文件中新增的行（+ 开头，排除 +++ 文件头）。"""
    lines = []
    for line in content.split('\n'):
        if line.startswith('+') and not line.startswith('+++'):
            lines.append(line[1:])
    return '\n'.join(lines)


def find_patch_files(repo_dir):
    """在仓库目录中查找所有补丁文件，返回 {相对路径: 文件内容}。"""
    patches = {}
    repo = Path(repo_dir)
    for ext in ('.patch', '.diff'):
        for path in repo.rglob(f'*{ext}'):
            if path.is_file():
                try:
                    patches[str(path.relative_to(repo))] = path.read_text(
                        encoding='utf-8', errors='replace'
                    )
                except Exception:
                    pass
    return patches


def _full_content_dangerous_rules():
    """作用于完整文件内容的危险模式规则（适用于 PKGBUILD 及辅助脚本）。

    返回 [(severity, rule_id, regex, description)]。
    """
    return [
        (CRITICAL, 'curl-pipe-shell',
         r'curl\s+\S+\s*\|\s*(?:ba)?sh\b', 'curl 管道到 shell 执行'),
        (CRITICAL, 'wget-pipe-shell',
         r'wget\s+\S+\s+-O\s*-\s*\|', 'wget 管道到 shell 执行'),
        (CRITICAL, 'eval-exec',
         r'\beval\s+', 'eval 命令执行'),
        (CRITICAL, 'base64-decode',
         r'base64\s+(?:-d|--decode)\b', 'base64 解码（疑似混淆）'),
        (CRITICAL, 'reverse-shell',
         r'(?:nc|ncat|netcat)\s+.*-e\b', '疑似反向 shell'),
        (CRITICAL, 'destructive-rm',
         r'rm\s+-rf\s+(?:/|/\*|~\s*/\*|\$HOME\s*/\*)', '危险删除命令'),
        (CRITICAL, 'chmod-world-writable',
         r'chmod\s+(?:-R\s+)?777\b', '设置全局可写权限'),
        (ERROR, 'sudoers-modification',
         r'[>\|]\s*/etc/sudoers(?:\.d/)?', '修改 sudoers 配置文件'),
        (ERROR, 'create-system-user',
         r'\b(?:useradd|groupadd|usermod)\b', '创建或修改系统用户/组'),
        (ERROR, 'dd-write-device',
         r'dd\s+if=.*\bof=/dev/', 'dd 写入块设备'),
        (ERROR, 'hosts-modification',
         r'[>\|]\s*/etc/hosts\b', '修改 /etc/hosts'),
    ]


# 辅助脚本/配置文件扩展名（除 PKGBUILD 与补丁外的审计范围）
AUX_FILE_EXTENSIONS = (
    '.install', '.sh', '.bash', '.zsh',
    '.service', '.timer', '.socket', '.desktop',
    '.mjs', '.js', '.ts', '.py',
    '.conf', '.cfg',
)

# 跳过超大文件（避免扫描 vendor 产物），上限 512KB
AUX_FILE_MAX_SIZE = 512 * 1024

# 单个仓库最多审计的辅助文件数量
AUX_FILE_MAX_COUNT = 50

# 跳过依赖/构建产物目录
AUX_FILE_EXCLUDED_DIRS = {'.git', 'node_modules', '__pycache__', 'dist', 'build'}


def find_aux_files(repo_dir):
    """查找 PKGBUILD 之外的辅助脚本/配置文件（.install/.sh/.service 等）。

    返回 {相对路径: 文件内容}，跳过二进制、超大文件及依赖目录。
    """
    aux = {}
    repo = Path(repo_dir)
    count = 0
    for ext in AUX_FILE_EXTENSIONS:
        for path in repo.rglob(f'*{ext}'):
            rel_parts = path.relative_to(repo).parts
            if any(part in AUX_FILE_EXCLUDED_DIRS for part in rel_parts):
                continue
            if not path.is_file() or path.stat().st_size > AUX_FILE_MAX_SIZE:
                continue
            if count >= AUX_FILE_MAX_COUNT:
                return aux
            try:
                content = path.read_text(encoding='utf-8', errors='replace')
            except Exception:
                continue
            if '\x00' in content:
                continue  # 二进制文件
            aux[str(path.relative_to(repo))] = content
            count += 1
    return aux


def run_aux_file_checks(aux_contents):
    """对辅助脚本/配置文件执行危险模式检查。

    返回 [(severity, rule_id, description)]，描述中附文件名。
    """
    issues = []
    for filename, content in aux_contents.items():
        for severity, rule_id, pattern, desc in _full_content_dangerous_rules():
            if re.search(pattern, content, re.IGNORECASE):
                issues.append((severity, rule_id, f'{desc}（{filename}）'))
    return issues


def _glob_to_regex(pattern):
    """将 glob 模式转换为正则表达式。* 匹配任意字符，? 匹配单个字符。"""
    regex = ''
    for ch in pattern:
        if ch == '*':
            regex += '.*'
        elif ch == '?':
            regex += '.'
        elif ch in '.+^$[]{}()|\\':
            regex += '\\' + ch
        else:
            regex += ch
    return '^' + regex + '$'


def load_allowed_patterns(config_path, package_name):
    """从 packages.yml 读取指定包的 allowed-source-patterns。"""
    config_file = Path(config_path)
    if not config_file.exists():
        return None

    try:
        import yaml
    except ImportError:
        return None

    with open(config_file, 'r') as f:
        data = yaml.safe_load(f)

    for pkg in data.get('packages', []):
        if pkg.get('name') == package_name:
            patterns = pkg.get('allowed-source-patterns')
            if patterns:
                return patterns
            return None
    return None


def run_checks(content, allowed_patterns, patch_contents=None):
    """
    对 PKGBUILD 内容运行所有安全检查。

    patch_contents: {filename: content} 补丁文件内容字典，可选

    返回: (issues, has_blocking) 其中 issues 是 [(severity, rule_id, description)]
    """
    sources = extract_sources(content)
    checksums = extract_checksums(content)
    variables = _extract_static_pkgbuild_variables(content)
    source_urls = [
        _expand_static_pkgbuild_variables(url, variables)
        for url in extract_source_urls(sources)
    ]

    sources_text = '\n'.join(sources)
    checksums_text = '\n'.join(
        val for vals in checksums.values() for val in vals
    )
    checksums_vars_text = '\n'.join(checksums.keys())

    issues = []

    # ── CRITICAL / ERROR（完整文件内容） ─────────────────────

    for severity, rule_id, pattern, desc in _full_content_dangerous_rules():
        if re.search(pattern, content, re.IGNORECASE):
            issues.append((severity, rule_id, desc))

    # ── ERROR（仅 source URL） ────────────────────────────────

    source_url_rules = [
        (
            'source-raw-ip',
            r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b',
            'source URL 包含裸 IP 地址',
        ),
        (
            'source-file-protocol',
            r"^file://",
            'source URL 使用 file:// 协议',
        ),
        (
            'source-git-insecure',
            r"^git://",
            'source URL 使用不安全的 git:// 协议',
        ),
    ]

    for rule_id, pattern, desc in source_url_rules:
        if re.search(pattern, sources_text, re.IGNORECASE):
            issues.append((ERROR, rule_id, desc))

    # ── 上游 URL 模式白名单检查 ───────────────────────────────

    if source_urls:
        if allowed_patterns is None:
            issues.append((
                WARNING, 'source-patterns-unconfigured',
                f'未配置 allowed-source-patterns，当前 source URL: {", ".join(source_urls)}'
            ))
        else:
            compiled = [re.compile(_glob_to_regex(p)) for p in allowed_patterns]
            for url in source_urls:
                if not any(r.search(url) for r in compiled):
                    issues.append((
                        ERROR, 'source-patterns-mismatch',
                        f'source URL 不在模式白名单中: {url}'
                    ))

    # ── 补丁文件内容审计 ──────────────────────────────────────

    if patch_contents:
        patch_rules = [
            (
                'patch-eval',
                r'\beval\s*\(',
                '补丁中引入 eval 调用',
                CRITICAL,
            ),
            (
                'patch-base64',
                r'base64\s+(?:-d|--decode)',
                '补丁中引入 base64 解码',
                CRITICAL,
            ),
            (
                'patch-hardcoded-ip',
                r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b',
                '补丁中包含硬编码 IP 地址',
                ERROR,
            ),
            (
                'patch-etc-write',
                r'["\']?/etc/(?!ssl/certs)',
                '补丁中涉及 /etc 路径修改',
                WARNING,
            ),
            (
                'patch-system-call',
                r'\b(?:system|exec[lv]?[pe]?|popen)\s*\(',
                '补丁中引入命令执行调用',
                WARNING,
            ),
            (
                'patch-network',
                r'\b(?:connect|socket|gethostbyname)\s*\(',
                '补丁中引入网络连接',
                WARNING,
            ),
            (
                'patch-download',
                r'\b(?:curl|wget|fetch)\s',
                '补丁中引入下载命令',
                WARNING,
            ),
            (
                'patch-chmod',
                r'\bchmod\s',
                '补丁中引入 chmod 调用',
                WARNING,
            ),
            (
                'patch-evil-keyword',
                r'\b(?:backdoor|trojan|malware|keylogger|ransomware|rootkit)\b',
                '补丁中包含可疑关键词',
                WARNING,
            ),
        ]

        for filename, patch_content in patch_contents.items():
            additions = extract_patch_additions(patch_content)
            if not additions:
                continue
            for rule_id, pattern, desc, severity in patch_rules:
                if re.search(pattern, additions, re.IGNORECASE):
                    issues.append((
                        severity, rule_id,
                        f'{desc}（{filename}）'
                    ))

    # ── WARNING ───────────────────────────────────────────────

    warning_rules = [
        (
            'checksum-skip',
            r'\bSKIP\b',
            '校验和设为 SKIP（无完整性验证）',
            'checksums',
        ),
        (
            'checksum-md5',
            r'md5sums',
            '使用弱哈希算法 MD5',
            'checksums_var',
        ),
        (
            'source-non-https',
            r'^(?:http|ftp)://',
            'source URL 使用非 HTTPS 协议',
            'source',
        ),
        (
            'source-suspicious-tld',
            r'https?://[^/\s]*\.(?:xyz|top|tk|ml|ga|cf|gq|pw|cc|su|ws|loan|click|download|party|review|science|bid|trade|date|racing|accountant|win|men|stream|ooo|ren|kim|site|website|space|press|club|online)\b',
            'source URL 来自可疑顶级域名',
            'source',
        ),
    ]

    for rule_id, pattern, desc, scope in warning_rules:
        target = _select_scope(content, sources_text, checksums_text, checksums_vars_text, scope)
        if re.search(pattern, target, re.IGNORECASE):
            issues.append((WARNING, rule_id, desc))

    if not checksums:
        issues.append((WARNING, 'checksum-missing', '未定义任何校验和'))

    has_blocking = any(sev in (CRITICAL, ERROR) for sev, _, _ in issues)
    return issues, has_blocking


def _select_scope(full, sources, checksums, checksums_vars, scope):
    return {
        'full': full,
        'source': sources,
        'checksums': checksums,
        'checksums_var': checksums_vars,
    }.get(scope, full)


def _find_pkgbuild(repo_dir):
    repo = Path(repo_dir)
    pkgbuild = repo / 'PKGBUILD'
    if pkgbuild.exists():
        return pkgbuild
    for path in repo.rglob('PKGBUILD'):
        return path
    return None


def main():
    source_url = os.environ.get('SOURCE_URL', '').strip()
    package_name = os.environ.get('PACKAGE_NAME', '').strip()
    source_dir = os.environ.get('SOURCE_DIR', '').strip()
    config_path = os.environ.get('CONFIG_PATH', '.github/packages.yml')

    if not source_url:
        print("::error::SOURCE_URL 环境变量未设置", file=sys.stderr)
        sys.exit(1)

    print("PKGBUILD 安全审计")
    print("===================")
    print(f"包名: {package_name}")
    print(f"源仓库: {source_url}")

    if source_dir:
        repo_dir = source_dir
        if not Path(repo_dir).is_dir():
            print(f"::error::源码目录不存在: {repo_dir}", file=sys.stderr)
            sys.exit(1)
    else:
        tmpdir = tempfile.mkdtemp(prefix='pkgbuild-audit-')
        repo_dir = os.path.join(tmpdir, 'repo')
        success, clone_error = clone_repository(source_url, repo_dir)
        if not success:
            print(f"::error::git clone 失败: {clone_error}", file=sys.stderr)
            sys.exit(1)

    pkgbuild_path = _find_pkgbuild(repo_dir)
    if not pkgbuild_path:
        print("::error::未找到 PKGBUILD 文件", file=sys.stderr)
        sys.exit(1)

    print(f"PKGBUILD: {pkgbuild_path}")

    allowed_patterns = load_allowed_patterns(config_path, package_name)
    if allowed_patterns:
        print(f"上游 URL 模式白名单: {', '.join(allowed_patterns)}")
    else:
        print("上游 URL 模式白名单: 未配置")

    patch_files = find_patch_files(repo_dir)
    if patch_files:
        print(f"发现补丁文件: {', '.join(patch_files.keys())}")
    else:
        print("补丁文件: 无")

    aux_files = find_aux_files(repo_dir)
    if aux_files:
        print(f"辅助脚本/配置文件: {', '.join(aux_files.keys())}")
    else:
        print("辅助脚本/配置文件: 无")

    print()

    content = pkgbuild_path.read_text(encoding='utf-8', errors='replace')
    issues, has_blocking = run_checks(content, allowed_patterns, patch_files)

    aux_issues = run_aux_file_checks(aux_files)
    issues.extend(aux_issues)
    has_blocking = has_blocking or any(
        sev in (CRITICAL, ERROR) for sev, _, _ in aux_issues
    )

    if not issues:
        print("结果: 未发现安全问题")
        print("状态: PASSED")
        return

    counts = {CRITICAL: 0, ERROR: 0, WARNING: 0}
    for sev, rid, desc in issues:
        counts[sev] += 1
        prefix = '::error' if sev in (CRITICAL, ERROR) else '::warning'
        print(f"{prefix} [{sev}] {rid}: {desc}")

    print()
    print(f"统计: {counts[CRITICAL]} 严重, {counts[ERROR]} 错误, {counts[WARNING]} 警告")

    if has_blocking:
        print("状态: FAILED — 存在阻断级别问题，构建已中止")
        sys.exit(1)
    else:
        print("状态: PASSED — 仅有警告级别问题，构建继续")


if __name__ == '__main__':
    main()
