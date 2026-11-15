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
   | `slim_level` | `safe` | `none` / `safe`（裁 DEBUG_FS、FTRACE、SQUASHFS、MHI、PCI、LZO）/ `plus`（再裁 MMC、LMK、uclamp、CoreSight，风险自负） |
   | `dtb_mode` | `dtb_2005` | `dtb_2005`=用 2005 设备树（保住 EAS 488/1024、能量表、频表、UFS/glink QoS）；`tree_dtb`=用树自己的 |
   | `flash_dtbo` | false | true 时才额外刷树编出的 dtbo |
4. 产物：Actions run 里的 artifact `raphael-ksunext-anykernel3` → 里面就是一个 **卡刷 zip**。

## 出包前自动校验（不通过直接失败，不会给你坏包）

- `save_allow_list write version failed`（**旧官方 KernelSU 独有串**）必须 **0** → 保证没有旧 KSU 残留；
- `ksu_handle_sys_read|hook_manager`（**KernelSU-Next 钩子**）必须 **>0**；
- 打印 `Linux version`、`CONFIG_KSU=y`、SUSFS 配置状态。

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
