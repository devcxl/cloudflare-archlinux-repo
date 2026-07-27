---
id: T4
title: "dependency-scan job — Trivy 文件系统漏洞扫描 + SARIF 上传"
phase: 2
status: pending
dependencies: ["T1"]
assigned_to: backend
pr: ""
branch: "feat/dependency-scan-job"
---

# T4: dependency-scan job — Trivy 文件系统漏洞扫描 + SARIF 上传

## 任务目标

在 `security-scan.yml` 的 `dependency-scan` job 中实现 Layer 3 漏洞扫描逻辑：
- 使用 Trivy 对 AUR 源码目录进行文件系统漏洞扫描
- 将扫描结果以 SARIF 格式上传到 GitHub Security 面板

用实际扫描步骤替换 T1 中的 stub。

## 验收标准

1. `dependency-scan` job 包含 Trivy 扫描步骤，使用 `aquasecurity/trivy-action@master`
2. Trivy 配置：`scan-type: fs`，`severity: CRITICAL,HIGH`，`exit-code: "1"`
3. Trivy 输出格式为 SARIF（`format: sarif`）
4. 扫描失败时 job 失败（`exit-code: "1"`），阻止 trigger-build
5. SARIF 上传步骤使用 `github/codeql-action/upload-sarif@v3`
6. SARIF 上传步骤设置 `if: always()`，即使扫描失败也上传结果
7. `dependency-scan` job 输出 `status: ${{ job.status }}`

## 实现步骤

1. 打开 `.github/workflows/security-scan.yml`
2. 定位 `dependency-scan` job，移除 stub echo 步骤
3. 确保保留 Checkout 步骤（`actions/checkout@v4`）
4. 确保保留 Clone AUR source 步骤
5. 添加 Trivy 扫描步骤：
   ```yaml
   - name: Trivy — filesystem vulnerability scan
     uses: aquasecurity/trivy-action@master
     with:
       scan-type: fs
       scan-ref: ${{ env.SOURCE_DIR }}
       format: sarif
       output: trivy-results.sarif
       severity: CRITICAL,HIGH
       exit-code: "1"
       ignore-unfixed: true
   ```
6. 添加 SARIF 上传步骤：
   ```yaml
   - name: Upload Trivy SARIF results
     if: always()
     uses: github/codeql-action/upload-sarif@v3
     with:
       sarif_file: trivy-results.sarif
       category: trivy-fs
   ```
7. 确认 job 的 `outputs` 包含 `status: ${{ job.status }}`

## 涉及文件

| 文件 | 操作 | 说明 |
|------|------|------|
| `.github/workflows/security-scan.yml` | 修改 | 填充 dependency-scan job 扫描步骤 |

## 测试方法

1. 手动触发 Security Scan workflow，使用测试参数：
   - `package-name`: `openssl`（包含已知 CVE 的旧版本仓库，或使用含漏洞依赖的源码）
   - `source-url`: 指向包含有漏洞依赖的测试仓库
2. 验证 `dependency-scan` job 执行 Trivy 扫描
3. 验证 SARIF 结果上传成功后，在 GitHub Security 面板的 "Code scanning" 中可查看
4. 测试含 `CRITICAL` 或 `HIGH` 级别漏洞的源码，验证 job 失败
5. 测试不含高危漏洞的源码，验证 job 通过
6. 检查 workflow log 确认扫描覆盖了正确的目录

## 参考

- 技术方案第 3 节 `dependency-scan` job：`docs/dev/specs/security-scan-workflow.md`
- Trivy Action: https://github.com/aquasecurity/trivy-action
- GitHub SARIF 上传: https://github.com/github/codeql-action/tree/main/upload-sarif
