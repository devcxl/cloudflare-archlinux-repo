# 从aur选择项目并使用cloudflare构建你自己的仓库

## 生成你自己的GPG密钥对

```shell
[devcxl@air14 cloudflare-archlinux-repo]$ gpg --full-generate-key
gpg (GnuPG) 2.4.7; Copyright (C) 2024 g10 Code GmbH
This is free software: you are free to change and redistribute it.
There is NO WARRANTY, to the extent permitted by law.

请选择您要使用的密钥类型：
   (1) RSA 和 RSA 
   (2) DSA 和 Elgamal 
   (3) DSA（仅用于签名）
   (4) RSA（仅用于签名）
   (9) ECC（签名和加密） *默认*
  (10) ECC（仅用于签名）
 （14）卡中现有密钥 
您的选择是？ 1
RSA 密钥的长度应在 1024 位与 4096 位之间。
您想要使用的密钥长度？(3072) 4096
请求的密钥长度是 4096 位
请设定这个密钥的有效期限。
         0 = 密钥永不过期
      <n>  = 密钥在 n 天后过期
      <n>w = 密钥在 n 周后过期
      <n>m = 密钥在 n 月后过期
      <n>y = 密钥在 n 年后过期
密钥的有效期限是？(0) 5y
密钥于 2030年05月25日 星期六 22时27分25秒 CST 过期
这些内容正确吗？ (y/N) y

GnuPG 需要构建用户标识以辨认您的密钥。

真实姓名： devcxl
电子邮件地址： example@devcxl.cn
注释： Example
您选定了此用户标识：
    “devcxl (Example) <example@devcxl.cn>”

更改姓名（N）、注释（C）、电子邮件地址（E）或确定（O）/退出（Q）？ O
我们需要生成大量的随机字节。在质数生成期间做些其他操作（敲打键盘
、移动鼠标、读写硬盘之类的）将会是一个不错的主意；这会让随机数
发生器有更好的机会获得足够的熵。
adsasda我们需要生成大量的随机字节。在质数生成期间做些其他操作（敲打键盘
、移动鼠标、读写硬盘之类的）将会是一个不错的主意；这会让随机数
发生器有更好的机会获得足够的熵。
gpg: 吊销证书已被存储为‘/home/devcxl/.gnupg/openpgp-revocs.d/D12A6ED8CDA1B38C3AD03D48ECBFD0BD2666278B.rev’
公钥和私钥已经生成并被签名。

pub   rsa4096 2025-05-26 [SC] [有效至：2030-05-25]
      D12A6ED8CDA1B38C3AD03D48ECBFD0BD2666278B
uid                      devcxl (Example) <example@devcxl.cn>
sub   rsa4096 2025-05-26 [E] [有效至：2030-05-25]
```

## 查看已经生成的密钥

```shell
[devcxl@air14 cloudflare-archlinux-repo]$ gpg --list-secret-keys
gpg: 正在检查信任度数据库
gpg: marginals needed: 3  completes needed: 1  trust model: pgp
gpg: 深度：0  有效性：  1  已签名：  0  信任度：0-，0q，0n，0m，0f，2u
gpg: 下次信任度数据库检查将于 2028-05-04 进行
[keyboxd]
---------
sec   rsa4096 2025-05-26 [SC] [有效至：2030-05-25]
      D12A6ED8CDA1B38C3AD03D48ECBFD0BD2666278B
uid             [ 绝对 ] devcxl (Example) <example@devcxl.cn>
ssb   rsa4096 2025-05-26 [E] [有效至：2030-05-25]
```
## 导出私钥

```
[devcxl@air14 ~]$ gpg --armor --export-secret-keys example@devcxl.cn > example-private-key.asc
[devcxl@air14 ~]$ cat example-private-key.asc 
-----BEGIN PGP PRIVATE KEY BLOCK-----
// 中间省略
-----END PGP PRIVATE KEY BLOCK-----
```
## 导出公钥
```
gpg --armor  --export D12A6ED8CDA1B38C3AD03D48ECBFD0BD2666278B > devcxl.gpg
```

## 将公钥上传到Cloudflare R2存储桶

`npx wrangler r2 object put <bucketname>/devcxl.gpg --file=/path/to/devcxl.gpg`

## 在 Arch Linux 客户端导入并信任公钥

建议按下面的顺序操作：先下载公钥、核对指纹，再导入 pacman keyring 并进行本地签名。

### 1. 下载公钥

```bash
curl -fsSL https://repo.archlinux.devcxl.cn/devcxl.gpg -o /tmp/devcxl.gpg
```

### 2. 查看并核对公钥指纹

```bash
gpg --show-keys --fingerprint /tmp/devcxl.gpg
```

请确认输出的指纹与你实际发布的仓库公钥一致。

### 3. 导入到 pacman keyring

```bash
sudo pacman-key --add /tmp/devcxl.gpg
```

### 4. 本地签名并信任该公钥

将下面命令中的 `<your-key-id>` 替换为上一步确认过的完整指纹或 Key ID：

```bash
sudo pacman-key --lsign-key <your-key-id>
```

### 5. 刷新仓库数据库

```bash
sudo pacman -Syy
```

如果你使用的仍然是之前已经导入并本地签名过的同一把密钥，通常无需重复信任，只需要确保客户端使用的是新的公钥下载地址 `devcxl.gpg`。


## Using the Repository

### 1. Add Repository to pacman.conf

Edit `/etc/pacman.conf` and add the repository configuration:

```
[devcxl]
Server = https://your-worker-domain.workers.dev
SigLevel = Required
```

Replace `your-worker-domain.workers.dev` with your actual Cloudflare Worker URL.

仓库数据库和 `devcxl.gpg` 发布在存储桶根路径，所有包文件发布在 `packages/` 目录下。Worker 会把根路径包请求自动转发到 `packages/`，所以客户端配置仍然保持不变。

### 迁移已有部署

如果你之前已经把仓库文件发布在 `repo/` 前缀下，切换到当前版本前请先完成其中一种迁移方式：

1. 将 `repo/` 下的包文件迁移到 `packages/`，并将数据库文件迁移到存储桶根路径；
2. 或者按 `.github/packages.yml` 中的包列表重新触发完整构建，重新生成根路径下的 `devcxl.db*` 与 `devcxl.files*`，以及 `packages/` 下的所有包文件。

迁移完成后，再把客户端配置切换到 `[devcxl]`。

### 2. Update Package Database

```bash
sudo pacman -Sy
```

### 3. Install Packages

To install a package from the repository:

```bash
sudo pacman -S localsend-bin
```

Replace `localsend-bin` with the package name you want to install.

### 4. Upgrade Packages

To update all packages from this repository:

```bash
sudo pacman -Syu
```

### 5. List Available Packages

To list all packages in the repository:

```bash
sudo pacman -Sl devcxl
```

### Troubleshooting

- If you get signature errors, verify the GPG key is trusted with `pacman-key -l`
- If packages aren't found, check that the repository URL is correct
- Ensure the Worker is deployed and accessible


## 参考文档
- https://viflythink.com/Use_GitHubActions_to_build_AUR/
- https://github.com/DuckSoft/build-aur-action
- https://github.com/marketplace/actions/upload-s3
