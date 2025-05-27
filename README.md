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
[devcxl@ms7b89 ~]$ gpg --armor --export-secret-keys example@devcxl.cn > example-private-key.asc
[devcxl@ms7b89 ~]$ cat example-private-key.asc 
-----BEGIN PGP PRIVATE KEY BLOCK-----
// 中间省略
-----END PGP PRIVATE KEY BLOCK-----
```


##  信任公钥

`sudo curl -sL https://repo.archlinux.devcxl.cn/self.gpg | sudo pacman-key --add - && sudo pacman-key --lsign-key C185EFFBD7587B346642F06A9AC873FEDCC2792A`


## 参考文档
- https://viflythink.com/Use_GitHubActions_to_build_AUR/
- https://github.com/DuckSoft/build-aur-action
- https://github.com/marketplace/actions/upload-s3