# raphael 内核构建器：2005 瘦身 + KernelSU-Next（开源重编）

用**开源源码**编出真正的「4.14 + KernelSU-Next（+SUSFS）+ 2005 瘦身/调参」内核，产出**可直接卡刷的 AnyKernel3 zip**。
不在本机编译，全部在 GitHub Actions 里完成。

## 为什么能成

默认源码 `SOVIET-ANDROID/kernel_xiaomi_raphael$16.0-SUSFS`（已核实）：
- `Makefile` = **4.14.357**（与 6.1 内核同上游版本）
- `drivers/kernelsu/` = **KernelSU-Next**（`Kconfig: config KSU default y`，无 KPROBES 时自动 `KSU_MANUAL_HOOK default y`）
- `fs/susfs.c` = **SUSFS 内置**
- `arch/arm64/configs/raphael_defconfig`，`CONFIG_WIREGUARD/CONFIG_NTFS_FS/CONFIG_EROFS_FS` 本来就有
- 无任何官方旧 KernelSU 目录：`drivers/staging/kernelsu`、`KernelSU/kernel`、`drivers/KernelSU` 均**不存在**


## 与 2005 内核（Rikka V2 / 4.14.336）的差异 & 落实矩阵

排除 Magisk 与 KSU 后，2005 与 SOVIET 树的差异分四类。`落实` 列说明 **本构建器出包后是否真的对齐**。

### A. 上游版本（不可"落实"，属升级）
| 项 | 2005 | SOVIET | 说明 |
|---|---|---|---|
| Linux 稳定版 | **4.14.336** | **4.14.357** | +21 个 stable 提交；构建器基于 357，不会回退 |

### B. 编译期特性（2005 侧由二进制实测得出，SOVIET 侧读 defconfig 核实）

| 配置项 | 2005（实测） | SOVIET raphael_defconfig | 是否落实 | 方式 |
|---|---|---|---|---|
| MODULES | **n**（无 vermagic/mod_unload 串） | 未提及 = 默认 **y** | ✅ 已补 `# CONFIG_MODULES is not set`（defconfig 里 0 个 `=m`，安全） | slim-safe/plus |
| FTRACE | **n**（saved_cmdlines/# tracer/tracing_thresh 全 0） | 未提及 = 默认 **y** | ✅ safe 档关闭 | slim-safe/plus |
| DEBUG_FS | **n**（debugfs_create_file/remove 全 0） | 未提及 = 默认 n（可能被 select） | ✅ 本来就一致；构建后打印确认 | — |
| MMC / PCI / MHI / CORESIGHT / SQUASHFS / LZO / LMK | **n** | 均未提及 = 默认 n | ✅ 本来就一致 | — |
| UCLAMP_TASK | **n**（uclamp 0 串） | **y** + `UCLAMP_TASK_GROUP=y` | ⚠ 仅 `plus` 档关闭；`safe` 档保留（uclamp 对调度有益，建议保留） | slim-plus |
| WIREGUARD / NTFS_FS / EROFS_FS / EXFAT_FS / FQ_CODEL / ZRAM / SELINUX | **y** | **y** | ✅ 本来就一致 | — |
| TCP_CONG_BBR | **y** | 未提及 = 默认 **n** | ✅ 新增 `config/features-2005.config` | features-2005 |
| TCP_CONG_WESTWOOD | **y** | `# ... is not set` | ✅ 同上 | features-2005 |
| KALLSYMS | 未知（二进制无法判定） | **明确 n** | ➖ 默认不动；需要时合并 `config/extra-kallsyms.config` | 可选 |
| IKCONFIG | **n** | **y**（有 `/proc/config.gz`） | ➖ 保留差异（便于刷后核对，无性能影响） | — |
| KPROBES | ？ | 默认 n → `KSU_MANUAL_HOOK` 自动 y | ➖ 不动（改它会破坏 KSU 集成方式） | — |

### C. 设备树 / 调参（builder 默认 100% 落实）

启用 `dtb_mode=dtb_2005` 时，构建器把 **2005 原版 DTB 原样追加**到 `Image.gz` 后 —— 不是"近似"，是同一份数据：

- EAS `capacity-dmips-mhz` 488/1024、8 个 CPU 的 `freq-energy-model`
- `energy-costs/core-cost0/1/2 busy-cost-data` 2005 重算表
- `cpucc qcom,cpufreq-table-0/4/7`
- UFS `pm-qos-cpu-group-latency-us` 100µs ×8 组、glink/cdsp `qos-latency-us` 67
- GPU `opp-690000000`、`rpmh-regulator-ldoa13` 2704000µV、jtagmm disabled、CoreSight 节点删除
- `/chosen/bootargs` 全套 flags

选 `dtb_mode=tree_dtb` 则用 SOVIET 树自己编出的 dtb（取值由树决定，不含 2005 调参）。

### D. 无法落实的部分（诚实边界）

1. **作者私有代码改动**（Rikka 在 sched/thermal/驱动层的私有 patch）：二进制里无法逐条还原，构建器不会假装有；
2. **2005 的 boot 头 cmdline**（`console=… / buildvariant=userdebug` 等）：刷机包只换内核区，cmdline 保留你 ROM 原样 —— 这是正确行为，不是缺失；
3. **代码生成级差异**：2005 用 clang 18.1.0rc + LLD，SOVIET CI 用 r547379 → 功能等价、但非字节等价。

### E. 如何验证"是否落实"

1. CI 出包会打印 **《2005 对齐状态》** 表（实际 `out/.config` 每项 y/n）+ `BBR ✔ / westwood ✔ / MODULES=n ✔` 三条提示；
2. 刷机后 `zcat /proc/config.gz | grep …` 可直接核对（SOVIET 开了 IKCONFIG）；
3. 内核串对比：`strings Image | grep -cE 'sdhci|mmc_blk' # 期望 1 以内`、`grep -c 'tcp_bbr' # 期望 >0`。

## 用法

1. 把本目录推到自己的 GitHub 仓库（任意私有/公开库）：
   ```bash
   git init && git add -A && git commit -m "builder"
   git remote add origin git@github.com:<你的>/raphael-kernel-builder.git
   git push -u origin main
   ```
2. Actions → **Build raphael kernel (2005-slim + KernelSU-Next)** → Run workflow
3. 参数：
   | 输入 | 默认 | 说明 |
   |---|---|---|
   | `kernel_repo` / `kernel_branch` | SOVIET / `16.0-SUSFS` | 也可换成 LineageOS/crDroid 的 `android_kernel_xiaomi_sm8150`（但那两棵没集成 KSU） |
   | `ksu_commit` | 空 | 填 tag/commit 会把树内 KernelSU-Next 更新到该版本（`drivers/kernelsu/setup.sh`） |
   | `slim_level` | `safe` | `none` / `safe`（裁 MODULES、DEBUG_FS、FTRACE、SQUASHFS、MHI、PCI、LZO）/ `plus`（再裁 MMC、LMK、uclamp、CoreSight，风险自负） |
   | `dtb_mode` | `dtb_2005` | `dtb_2005`=用 2005 设备树（保住 EAS 488/1024、能量表、频表、UFS/glink QoS）；`tree_dtb`=用树自己的 |
   | `flash_dtbo` | false | true 时才额外刷树编出的 dtbo |
4. 产物：Actions run 里的 artifact `raphael-ksunext-anykernel3` → 里面就是一个 **卡刷 zip**。

## 出包前自动校验（不通过直接失败，不会给你坏包）

判定依据修正过（第一次运行就栽在这里）：**Image 是 strip 的、且该树 `CONFIG_KALLSYMS=n`，函数名/符号名不会出现在二进制里**，所以：

- ❌ 不能用 `ksu_handle_*` / `hook_manager` 做判据（实测 6.1 与 2005 内核里都是 0 次）；
- ❌ `save_allow_list write version failed` 新版 KSU 也有（实测 6.1=1、2005=1），不能当"旧版残留"判据；

现在的校验：

| 检查 | 判据 |
|---|---|
| KSU 已开启 | `CONFIG_KSU=y` 必须在 `out/.config` |
| 是**新版** KSU | Image 里必须出现 `su_compat` / `kernel_umount` / `mnt_ns magic`（旧官方 v0.8 线没有这三个） |
| 钩子方式 | 打印 `CONFIG_KSU_MANUAL_HOOK=y`（该树无 KPROBES，只能 manual hook） |
| SUSFS | 打印 `CONFIG_KSU_SUSFS*` 项数 |
| 交叉验证 | 若 `out/vmlinux` 存在，统计其中 `ksu_*`/`kernelsu_*` 符号数 |

## 刷入包做了什么（旧 KSU 用户态残留清理写进脚本了）

- `anykernel.sh`：`do.ksucleanup=1`；`flash_boot` 成功后调用 `tools/ksucleanup.sh` 的 `ksu_cleanup_legacy`；
- 清理内容（**备份后移动**，不是删除）：
  - `/data/adb/ksu` → `/data/adb/ksu-legacy-backup-<时间戳>/ksu`（旧 allowlist、modules.img 等）
  - `/data/adb/ksud` → 同备份目录（旧管理器推的二进制）
  - 附带清理 `modules_update.img`、`ksud.old`、`ksu.old`
- 不解包/删除 `/data/adb/modules`（模块数据保留）；
- 管理器 app 不会被动（recovery 里不敢动 packages.xml），脚本会打印提示：
  刷完请**卸载旧 KernelSU 管理器**，再装 **KernelSU-Next 管理器**；
- 回滚：`mv /data/adb/ksu-legacy-backup-*/ksu /data/adb/ksu`（`ksud` 同理）；
- 关闭清理：改 `anykernel.sh` 里 `do.ksucleanup=0`。

## 本地自测（不需要编译，验证打包链路）

```bash
KERNEL_IMG=/path/to/Image DTB_MODE=dtb_2005 TAG=test bash scripts/pack.sh
# 或整体验证（会检查 zip 内容、anykernel.sh、清理函数）
bash scripts/selftest.sh
```

## 已知边界

- 这是**开源树重编**，不是 Rikka/MIUICX 的私有源码：6.1 的私有补丁（hwui 注入内核侧、dtbo 定制等）无法复现；
- `dtb_2005` 模式把 2005 DTB 追加在 `Image.gz` 后；若某外设异常，改 `tree_dtb` 再编一次对比即可；
- 树内 KernelSU-Next 版本较旧时，用 `ksu_commit` 输入更新到指定版本；管理器请用 **KernelSU-Next 管理器**（官方 KSU 管理器不认）。