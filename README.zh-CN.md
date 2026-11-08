# hapd

**在 Linux 上签名、安装、调试鸿蒙 HAP 包 —— 不需要 DevEco Studio，不需要 Windows 或 macOS。**

`hapd` 是一个单文件、零第三方依赖的 Python CLI，把华为官方的 HarmonyOS
Command Line Tools（`hdc` + `hap-sign-tool`）封装成一条非交互命令。

存在的原因：华为没有 Linux 版 DevEco Studio；而手敲 `hdc` / `hap-sign-tool`
是一路地雷——证书链顺序、Profile 与包名的匹配、以及一堆没有文档的错误码。

> English: [README.md](README.md)
> 鸿蒙签名机制的深入说明：[docs/harmonyos-signing.md](docs/harmonyos-signing.md)

---

## 功能

- **一条命令装完** —— `hapd deploy app.hap` 完成签名、安装、启动。
- **任意 HAP，不只你自己的** —— `--rename-bundle` 直接改写包内 `app.bundleName`，
  让下载来的包可以用**你的** Profile 签名。
- **权限修复** —— `--strip-unsupported` 自动剥掉 Profile 没授权的权限，
  这是 `9568289` 的对症药。
- **自动修正证书链顺序** —— AGC 下载的 `.cer` 是「根→中间→实体」，
  `hap-sign-tool` 要「实体→中间→根」，自动处理。
- **体检** —— `hapd doctor` 检查工具链、Java、签名材料、Profile 有效期，
  以及当前设备的 UDID 是否在 Profile 里。
- **对 agent 友好** —— 所有命令支持 `--json`、`--dry-run`，退出码有明确含义，
  不弹交互、不依赖 TTY、不输出颜色。
- **错误码翻译** —— `hapd explain 9568257` 用人话解释。

## 前置条件

| 项 | 说明 |
|---|---|
| Linux x86_64 | glibc ≥ 2.28（Debian 11+ / Ubuntu 20.04+） |
| **HarmonyOS Command Line Tools** | 唯一不太容易拿的依赖，提供 `hdc`、`hap-sign-tool.jar` 和 SDK。需要（免费）华为开发者账号。 |
| JDK 17 或 21 | CLT 26.x 推荐 21，更早的版本要 17。只用来跑 `hap-sign-tool.jar`。 |
| Python 3.8+ | 只用标准库。 |
| `openssl`、`keytool` | 证书链重排、密钥库检查。 |
| 华为开发者账号 | 免费。只需用一次，去 AGC 申请**调试证书**和**调试 Profile**。 |
| 鸿蒙设备 | 开启 开发者选项 → 无线调试（或 USB）。 |

### 获取 Command Line Tools

到 <https://developer.huawei.com/consumer/cn/download/> 下载
**Command Line Tools → Linux-x64**（需要登录）：

```bash
unzip commandline-tools-linux-x64-<version>.zip -d ~/opt/apps/harmonyos/<version>
# => ~/opt/apps/harmonyos/<version>/command-line-tools
```

`hapd` 会自动发现 `~/opt/apps/harmonyos/*/command-line-tools`（新版本优先）。
也可以用 `HAPD_TOOLCHAIN` 或 `COMMANDLINE_TOOL_DIR` 指定。

### 获取签名材料（一次性的）

HAP 必须用设备信任的证书签名。**OpenHarmony 社区证书在商业鸿蒙设备上会被拒绝**
（`9568257`），所以必须用 AGC 的材料：

1. `keytool -genkeypair -alias my-key -keyalg EC -groupname secp256r1 \
   -sigalg SHA256withECDSA -keystore my.p12 -storetype pkcs12 -validity 9125 \
   -storepass '<密码>' -keypass '<密码>' -dname "C=CN,O=Me,OU=Dev,CN=my-key"`
2. `keytool -certreq -alias my-key -keystore my.p12 -storetype pkcs12 -file my.csr -storepass '<密码>'`
3. AGC 里：登记包名（APP ID）→ 上传 `my.csr` 拿**调试证书** `.cer` →
   登记设备 UDID → 创建绑定该证书和设备的**调试 Profile** `.p7b`
4. 把 `my.p12`、`*.cer`、`*.p7b` 放进 `./signing/`

详细步骤见 [docs/harmonyos-signing.md](docs/harmonyos-signing.md)。

## 安装

`hapd` 以 [Environment Modules](https://modules.readthedocs.io/) 包的形式发布，
不往 shell 的 rc 文件里写任何东西，还能锁版本、回滚版本。

```bash
git clone https://github.com/lql341/hapd.git ~/work/hapd
cd ~/work/hapd
./install.sh                       # -> $MODULEFILES_DIR/hapd/<版本号>
module load hapd/0.1.0
hapd --version
```

`install.sh` 参数：

| 参数 | 作用 |
|---|---|
| `--module-dir DIR` | 把 modulefile 写到 `DIR/hapd/<版本>`（默认 `$MODULEFILES_DIR` 或 `~/opt/modulefiles`） |
| `--no-link` | 不创建 `~/.local/bin` 下的便捷软链 |

如果你的 `MODULEPATH` 还没包含那个目录，在 module 初始化文件里加一次
（`module use ~/opt/modulefiles`）——**不要**从 `.bashrc` 里 export hapd 的变量。

没有 modules 环境？一条软链也行：

```bash
ln -s "$PWD/hapd" ~/.local/bin/hapd
```

### 用 module 覆盖层放签名材料

`install.sh` 会在脚本旁生成 `hapd.local.tcl`（已加入 .gitignore）。
生成的 modulefile 在 `module load` 时 source 它，所以密钥既不进 shell rc，
也不进仓库：

```tcl
# hapd.local.tcl
setenv HAPD_P12      /path/to/my-key.p12
setenv HAPD_CERT     /path/to/my-debug.cer
setenv HAPD_PROFILE  /path/to/my-debug.p7b
setenv HAPD_P12_PWD  <密钥库密码>
setenv HAPD_ALIAS    my-key
```

配好之后，`hapd doctor` 和 `hapd deploy` 不需要任何参数或环境变量。


## 快速开始

```bash
module load hapd/0.1.0

# 1. 环境体检
hapd doctor

# 2. 连手机（无线调试页面会显示 ip:port）
hapd connect 192.168.1.63:32907
hapd udid                    # 填到 AGC 注册设备

# 3. 签名 + 安装 + 启动
hapd deploy app-unsigned.hap

# 4. 看日志
hapd log --filter myapp
```

## 命令

| 命令 | 作用 |
|---|---|
| `hapd doctor` | 检查工具链、Java、签名材料、Profile 有效期、设备 UDID 是否匹配 |
| `hapd devices` | 列出已连接设备 |
| `hapd connect <ip:port>` | 无线连接 |
| `hapd udid` | 打印设备 UDID（AGC 注册用） |
| `hapd info <hap>` | 查看包名、版本、API、权限、Ability |
| `hapd profiles` | 列出本地 Profile：包名、有效期、设备数 |
| `hapd sign <hap>` | 只签名 |
| `hapd install <hap>` | 安装（加 `--sign` 先签名） |
| `hapd run <bundle>` | 启动 Ability（`--hap` 可从包里读 `mainElement`） |
| `hapd log [--filter X]` | 跟 hilog |
| `hapd deploy <hap>` | 签名 → 安装 → 启动 |
| `hapd update <url\|路径>` | 下载新构建后直接部署 |
| `hapd explain <code>` | 解释设备错误码 |

全局参数：`--json`、`--dry-run`、`--version`。

### 签名材料的查找顺序

module 覆盖层 → 显式参数 → 环境变量 → `./signing/` 下最新文件：

| 用途 | 参数 | 环境变量 |
|---|---|---|
| 密钥库 | `--p12` | `HAPD_P12` |
| 证书 | `--cert` | `HAPD_CERT` |
| Profile | `--profile` | `HAPD_PROFILE` |
| 密钥库密码 | `--password` | `HAPD_P12_PWD` |
| 密钥别名 | `--alias` | `HAPD_ALIAS` |
| 材料目录 | `--signing-dir` | — |

## 签别人的包

下载来的 HAP 通常是别人的签名，或者压根没签。`hapd` 可以重新定向：

```bash
# Profile 里是 com.example.mine，包里是 com.someone.else
hapd sign downloaded.hap -o mine.hap --rename-bundle com.example.mine

# 安装报 9568289 → 把 Profile 不允许的权限全剥掉
hapd sign downloaded.hap -o mine.hap --rename-bundle com.example.mine --strip-unsupported
```

`--rename-bundle` 会改写包内 `module.json`（以及 `pack.info`），再重新签名。
如果指定的名字和 Profile 的包名不一致，它会直接拒绝——否则设备必然拒装。

> 请遵守被重签应用的许可协议。这个功能是为「装自己的构建」和「授权允许分发的应用」准备的。

## 给 agent 用

`hapd` 是给 LLM agent 和 CI 设计的。完整契约见 [AGENTS.md](AGENTS.md)。要点：

```bash
export HAPD_P12_PWD=...      # CI 里不要把密码写进命令行
hapd --json doctor           # -> {"ok": true, "checks": [...]}
hapd --json info app.hap     # -> bundle_name / version / permissions ...
hapd --dry-run deploy app.hap
hapd --json deploy app.hap   # -> {"out": ..., "bundle": ...}
```

退出码：`0` 成功、`1` doctor 发现问题、`2` 输入有问题、`3` 缺依赖、
`4` 签名/验签失败、`5` 安装失败、`6` 启动失败。

## 常见问题

| 报错 | 含义 | 解决 |
|---|---|---|
| `9568257` fail to verify pkcs7 file | 证书链根不被设备信任（多半是社区证书） | 改用 AGC 调试材料 |
| `9568322` | 包名与 Profile 的 bundle-name 不一致 | `--rename-bundle` 或新建 Profile |
| `9568289` | 申请的权限 Profile 没授权 | `--strip-unsupported` |
| `9568332` | 同包名已装且签名不同 | 先卸载再装 |
| `9568266` | 设备 UDID 不在 Profile 里 | 去 AGC 加设备、下新 Profile、重签 |
| `10106102` | 锁屏状态下拒绝 `aa start` | 解锁手机 |
| `verify certificate chain failed` | `.cer` 是根在前 | 已自动处理；确认没把证书文件改坏 |
| `hdc` 显示 `Unauthorized` | 没点手机上的授权弹窗 | 解锁手机，勾「始终允许」，`hdc kill` 再重连 |

## 安全

不要把 `*.p12`、`*.p7b`、`*.cer`、`*.csr` 提交进仓库——`.gitignore` 已覆盖。
密钥库密码建议用 `HAPD_P12_PWD` 而不是 `--password`，避免进入 shell 历史。

## 许可

MIT，见 [LICENSE](LICENSE)。
