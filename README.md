# Cloudflare Arch Linux 私有仓库

基于 Cloudflare Workers + R2 构建个人 Arch Linux 软件仓库，通过 GitHub Actions 自动从 AUR 构建包、签名并发布。

## 架构

```
AUR (上游)                    GitHub Actions                    Cloudflare                Arch 客户端
    │                              │                               │                         │
    │  check-aur-updates           │                               │                         │
    │◄─────────────────────────────│                               │                         │
    │                              │                               │                         │
    │  git clone + makepkg         │                               │                         │
    │◄─────────────────────────────│                               │                         │
    │                              │                               │                         │
    │                              │  repo-add + GPG 签名          │                         │
    │                              │──────────────────────────────►│  R2 存储桶              │
    │                              │                               │                         │
    │                              │                               │  Worker 反向代理        │
    │                              │                               │◄────────────────────────│ pacman -Syu
    │                              │                               │                         │
```

- **Worker** (`index.js`): 从 R2 读取文件并返回，支持 Range 请求，自动将包请求转发到 `packages/` 前缀
- **R2 存储桶**: 存储 `.db`、`.files`、`.gpg` 及所有 `.pkg.tar.zst` 包文件
- **GitHub Actions**: 三个工作流分管构建、部署、更新检查

## 快速开始

### 前置条件

- Cloudflare 账号（R2 + Workers）
- GitHub 账号（运行 Actions）
- 生成的 GPG 密钥对

### 1. 生成 GPG 密钥

```bash
gpg --full-generate-key
# 建议: RSA 4096 位, 5 年有效期
```

导出密钥：

```bash
# 导出私钥（用于 Actions 签名）
gpg --armor --export-secret-keys <your-email> > private-key.asc

# 导出公钥（上传到 R2 供客户端导入）
gpg --armor --export <key-id> > public-key.gpg
```

### 2. Fork 仓库并配置

**Fork 后修改以下文件：**

| 文件 | 修改内容 |
|------|----------|
| `wrangler.toml` | `name`、`bucket_name` 改为你自己的 |
| `.github/packages.yml` | 替换为你需要的 AUR 包列表 |
| `.github/workflows/build.yml` | `generator_database` 步骤中的 `database` 参数改为你的仓库名 |

### 3. 配置 GitHub Secrets

进入仓库 Settings → Secrets and variables → Actions，添加以下 Secrets：

| Secret | 说明 |
|--------|------|
| `AWS_BUCKET` | R2 存储桶名称 |
| `AWS_KEY_ID` | R2 Access Key ID |
| `AWS_SECRET_ACCESS_KEY` | R2 Secret Access Key |
| `AWS_ENDPOINT` | R2 端点 URL（如 `https://<account-id>.r2.cloudflarestorage.com`） |
| `GPG_PRIVATE_KEY` | 私钥内容（`cat private-key.asc`） |
| `GPG_PASSPHRASE` | GPG 密钥密码 |
| `CLOUDFLARE_API_TOKEN` | Cloudflare API Token |
| `CLOUDFLARE_ACCOUNT_ID` | Cloudflare 账户 ID |
| `ACCESS_TOKEN` | GitHub 个人访问令牌（用于触发跨仓库工作流） |

### 4. 上传公钥到 R2

```bash
npx wrangler r2 object put <bucket-name>/public-key.gpg --file=/path/to/public-key.gpg
```

### 5. 首次构建 & 部署

1. 手动触发 `Build arch package` 工作流，逐个构建 `.github/packages.yml` 中的包
2. 推送代码到 `master` 分支，自动触发 `Deploy cloudflare worker` 工作流

## 包管理

### 添加新包

编辑 `.github/packages.yml`，按格式添加：

```yaml
packages:
  - name: <包名>
    url: https://aur.archlinux.org/<包名>.git
    allowed-source-patterns:
      - https://<可信域名>/*
    # 可选：构建前应用到克隆源码的修复补丁（相对仓库根目录）
    # patches:
    #   - .github/pkgbuild-patches/<包名>/0001-xxx.patch
```

### 手动构建

在 GitHub Actions 中手动触发 `Build arch package` 工作流，填写包名和 AUR 仓库 URL。

### 自动更新检查

`check-aur-updates` 工作流定期检查 AUR 上游版本，发现更新后自动触发构建。

## 客户端配置

### 导入公钥

```bash
# 下载公钥
curl -fsSL https://<your-worker-domain>/public-key.gpg -o /tmp/public-key.gpg

# 核对指纹
gpg --show-keys --fingerprint /tmp/public-key.gpg

# 导入 pacman keyring
sudo pacman-key --add /tmp/public-key.gpg

# 本地签名
sudo pacman-key --lsign-key <key-id>
```

### 添加仓库

编辑 `/etc/pacman.conf`，在文件末尾添加：

```ini
[<repo-name>]
Server = https://<your-worker-domain>
SigLevel = Required
```

### 使用

```bash
sudo pacman -Sy                   # 更新数据库
sudo pacman -S <package-name>     # 安装包
pacman -Sl <repo-name>            # 列出仓库所有包
```

## 本地开发

```bash
npm install
npm run dev      # 启动 Worker 本地开发服务器
npm test         # 运行测试
```

## 项目结构

```
.
├── index.js                          # Cloudflare Worker 入口
├── wrangler.toml                     # Wrangler 配置
├── package.json
├── test/                             # 测试文件
└── .github/
    ├── packages.yml                  # AUR 包列表
    ├── workflows/
    │   ├── build.yml                 # 构建单个包
    │   ├── deploy.yml                # 部署 Worker
    │   └── check-aur-updates.yml     # 检查 AUR 更新
    ├── build-aur-action/             # AUR 构建 Action
    ├── generator_database/           # pacman 数据库生成 Action
    ├── upload-r2-action/             # R2 上传 Action
    ├── download-r2-action/           # R2 下载 Action
    ├── clean-old-packages-action/    # 清理旧版本 Action
    └── read-packages-action/         # 读取包列表 Action
```

## 参考

- [Use GitHub Actions to build AUR](https://viflythink.com/Use_GitHubActions_to_build_AUR/)
- [build-aur-action](https://github.com/DuckSoft/build-aur-action)
- [upload-s3 Action](https://github.com/marketplace/actions/upload-s3)