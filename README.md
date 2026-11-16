# Raphael — Rikka 4.14.336 + Next v3.4.2 + SUSFS

当前构建分支：`rikka-2005-release-susfs`。固定 Rikka `222b8d42`、Next 正式版 v3.4.2 `4c706b59`（UAPI 5），移植官方冻结 legacy 参考中的必要 4.14 手动钩子与兼容代码。SUSFS 使用 v2.2.0 NON-GKI 文件系统移植；提供 `next-susfs` 目标包与同基底的 `next` 对照包。此构建包含移植修改，不是官方原样发行镜像。

实际手机日志已证实此前“设备内部出现问题”来自 VINTF 内核配置不匹配；本次编译满足采集矩阵的 193 项要求。关闭 KSU_DEBUG / SUSFS 日志，不在 uname 追加 next/susfs。构建失败也保留日志、配置、源码差异；成功另保留对应 vmlinux、System.map 和 boot 重打包检查。详见 [当前接口与启动问题复盘](docs/20261116-启动提示与管理器接口复盘.md)。

以下内容保留为早期 SOVIET 工作流及上一版 legacy 构建的历史说明；其中版本、推荐 APK、默认配置和交付分支不适用于当前构建。

<details><summary>历史工作流说明（不作为当前刷入指南）</summary>

> **2026-11-16 最终交付分支：`rikka-2005-package`。** 此分支包含最终修正的完整编译、校验和打包脚本。`build-rikka.yml` 使用固定 Rikka 4.14.336 源码和 KernelSU Next legacy 提交，产出 `next` 与关闭 KSU 的 `control` 两个包；`package-rikka.yml` 记录本次复用已编译镜像完成校验打包的过程。下面旧的 SOVIET + 2005-slim 工作流保留作历史记录；本次交付以新工作流为准。验收、boot 备份和失败取证步骤见 [失败复盘与验收](docs/失败复盘与验收.md)。源码基底：[Rikka 固定提交](https://github.com/jianyi520/kernel_xiaomi_raphael-rikka/commit/222b8d42dde3f13973357cae50359fa2aca8239d)；root：[Next legacy 固定提交](https://github.com/KernelSU-Next/KernelSU-Next/commit/e5f5ec998de88b9fc43c62cff8f7ae12d3f4800a)。

A reproducible GitHub Actions pipeline that compiles a Xiaomi SM8150 (`raphael` / `raphaels` / `raphaelin`) Linux 4.14 kernel from open-source sources and packages it into a flashable **AnyKernel3** ZIP.

The default configuration targets a *lean* kernel that mirrors the tuning and trimming choices found in the popular "2005"-style raphael kernels, while integrating a current-generation **KernelSU-Next** root solution (and **SUSFS**, when the source tree provides it).

---

## 1. What this repository produces

A single artifact per run:

```
raphael-2005slim-ksunext-<timestamp>-<slim_level>.zip
```

This ZIP is an AnyKernel3 installer that:

* replaces only the kernel region of the `boot` partition;
* leaves the ramdisk, header cmdline and vbmeta/AVB state untouched;
* contains **no Magisk boot-patching logic** (no `skip_initramfs` hex patch, no DTB verity/AVB removal, no vbmeta flag modification);
* performs a supervised cleanup of legacy KernelSU user-space data (see §7).

---

## 2. Pipeline overview

```
workflow_dispatch
        │
        ├─ install build dependencies (bc/bison/flex/libssl/libelf/ccache/…)
        ├─ fetch AOSP clang r547379 (crDroid prebuilt, cached)
        ├─ clone the kernel source tree (default: SOVIET-ANDROID/kernel_xiaomi_raphael@16.0-SUSFS, Linux 4.14.357)
        ├─ optional: update the in-tree KernelSU-Next to a pinned tag/commit
        ├─ configure: raphael_defconfig + features fragment + optional slim fragment
        ├─ build: make O=out ARCH=arm64 LLVM=1 LLVM_IAS=1 CC="ccache clang" -j
        ├─ verify KernelSU integration (hard gate)
        ├─ report post-build configuration status
        ├─ package: Image + 2005 device tree → Image.gz-dtb → AnyKernel3 ZIP
        └─ upload artifact
```

The default source tree already contains:

* `drivers/kernelsu/` — KernelSU-Next (`config KSU`, `default y`);
* `fs/susfs.c` — SUSFS;
* `arch/arm64/configs/raphael_defconfig` — buildable raphael configuration.

No official (legacy) KernelSU directory exists in that tree (`drivers/staging/kernelsu`, `KernelSU/kernel`, `drivers/KernelSU` are absent).

---

## 3. Requirements

* A GitHub account with Actions enabled (public repositories include free runners).
* No local toolchain is required.
* Expected runtime: 40–80 minutes for a cold build; substantially faster once the clang and source caches are warm.

---

## 4. Usage

1. Push this repository to GitHub (fork or create a new repository and push these files):

   ```bash
   git remote add origin git@github.com:<account>/gha-builder.git
   git push -u origin main
   ```

2. Open **Actions → Build raphael kernel (2005-slim + KernelSU-Next) → Run workflow**.

3. Keep the defaults for a "2005-like" kernel, or adjust the inputs (see §5).

4. When the run completes, download the artifact **`raphael-ksunext-anykernel3`** and flash the contained ZIP from a custom recovery.

> Note: *Re-run jobs* replays the workflow file at the commit that originally triggered the run. To pick up changes to the workflow, start a **new** run via *Run workflow*.

---

## 5. Workflow inputs

| Input | Default | Description |
|---|---|---|
| `kernel_repo` | `https://github.com/SOVIET-ANDROID/kernel_xiaomi_raphael` | Kernel source repository. LineageOS/crDroid `android_kernel_xiaomi_sm8150` trees also build, but do not ship KernelSU integration. |
| `kernel_branch` | `16.0-SUSFS` | Source branch (4.14.357). Alternatives: `15-susfs` (4.14.353), `16.0` / `15.0` (no root integration). |
| `ksu_commit` | *(empty)* | Optional KernelSU-Next tag or commit. When set, `drivers/kernelsu/setup.sh` updates the in-tree integration before building. |
| `slim_level` | `safe` | `none`: no trimming. `safe`: disable `MODULES`, `DEBUG_FS`, `FTRACE`, `SQUASHFS`, `MHI_BUS`, `PCI`, `LZO`. `plus`: additionally disable `MMC`, `ANDROID_LOW_MEMORY_KILLER`, `UCLAMP_TASK`, `CORESIGHT`. |
| `dtb_mode` | `dtb_2005` | `dtb_2005`: append `dtb/2005-dtb.bin` after `Image.gz` (preserves the reference EAS/thermal/frequency/UFS tuning). `tree_dtb`: use the device tree produced by the source tree. |
| `flash_dtbo` | `false` | When `true`, the tree-built `dtbo.img` is included and `flash_dtbo` is inserted after `flash_boot`. Disabled by default to avoid replacing ROM-specific overlays. |
| `debug_ramoops` | `false` | Debug aid: appends `dtb/2005-dtb-ramoops.bin` instead of `dtb/2005-dtb.bin`. The variant adds a `ramoops` reserved-memory node (0xa1600000, 8 MiB, copied from the reference 4.14.357 device tree) so that a failed boot leaves a retrievable console log in `pstore`. |

---

## 6. Configuration fragments

| File | Applied by default | Purpose |
|---|---|---|
| `config/features-2005.config` | yes | Enables `TCP_CONG_BBR` and `TCP_CONG_WESTWOOD` (present in the reference kernel, disabled in the upstream defconfig). |
| `config/slim-safe.config` | yes when `slim_level=safe` | Disables `MODULES`, `DEBUG_FS`, `FTRACE`, `SQUASHFS`, `MHI_BUS`, `PCI`, `LZO`. |
| `config/slim-plus.config` | only when `slim_level=plus` | Additionally disables `MMC`, `ANDROID_LOW_MEMORY_KILLER`, `UCLAMP_TASK`, `CORESIGHT`. |
| `config/extra-kallsyms.config` | no (opt-in) | Enables `KALLSYMS` (the upstream defconfig disables it). Add it to `FRAGS` in the workflow if symbol resolution is required. |

Fragments are merged with `scripts/kconfig/merge_config.sh -m -O out out/.config <fragments>` followed by `olddefconfig`.

---

## 7. KernelSU verification (CI hard gate)

The Image produced by this tree is stripped and `CONFIG_KALLSYMS=n`, therefore **function and symbol names are not present in the binary**. Verification therefore uses configuration and behavioural markers:

| Check | Criterion |
|---|---|
| Integration enabled | `CONFIG_KSU=y` present in `out/.config` |
| Current-generation KernelSU | Image contains the `su_compat`, `kernel_umount` and `mnt_ns magic` markers (legacy v0.8-era integrations do not) |
| Hook mode | `CONFIG_KSU_MANUAL_HOOK=y` is reported (the tree has no `CONFIG_KPROBES`, so KernelSU-Next is integrated through manual hooks) |
| SUSFS | Number of `CONFIG_KSU_SUSFS*` entries is reported |
| Cross-check | When `out/vmlinux` exists, the count of `ksu_*` / `kernelsu_*` symbols is reported |

A failed gate aborts the run before packaging, so an improperly integrated kernel is never published as an artifact.

---

## 8. Flashing and user-space cleanup

The installer replaces the kernel region only. After a successful `flash_boot`, `anykernel.sh` invokes `tools/ksucleanup.sh`.

| Target | Action |
|---|---|
| `/data/adb/ksu` | moved to `/data/adb/ksu-legacy-backup-<timestamp>/ksu` (legacy allowlist, image files, etc.) |
| `/data/adb/ksud` | moved to the same backup directory |
| `modules_update.img`, `ksud.old`, `ksu.old` | moved to the same backup directory when present |
| `/data/adb/modules` | **untouched** |

Legacy and current KernelSU releases share the `/data/adb/ksu` path but use incompatible on-disk formats; without this cleanup a freshly installed KernelSU-Next manager can appear installed yet be unable to grant root.

Behaviour notes:

* The cleanup **moves** data rather than deleting it, so it is reversible:
  ```bash
  mv /data/adb/ksu-legacy-backup-*/ksu  /data/adb/ksu
  mv /data/adb/ksu-legacy-backup-*/ksud /data/adb/ksud
  ```
* It can be disabled by setting `do.ksucleanup=0` in `ak3/anykernel.sh`.
* The manager application itself is not modified by the installer. After flashing, uninstall the legacy KernelSU manager and install the **KernelSU-Next** manager (the kernel verifies the manager APK signature, so managers from other projects are not recognised).

Recommended procedure:

1. Back up the current boot partition (`dd if=/dev/block/bootdevice/by-name/boot of=/sdcard/boot_backup.img` or a TWRP boot backup).
2. Flash the artifact ZIP in a custom recovery.
3. Verify with `uname -r` (expect a `4.14.357-…` kernel; the default tree uses `EXTRAVERSION = -openela`, so the string is typically `4.14.357-openela…`, with the exact suffix determined by `setlocalversion`) and install the matching manager.
4. To roll back, flash the previous kernel ZIP, or `fastboot flash boot <backup image>`.

---

## 9. Repository layout

```
.github/workflows/build-raphael.yml   CI pipeline
ak3/                                  AnyKernel3 template (Magisk patching removed)
  anykernel.sh                        installer entry point (device checks, cleanup hook)
  tools/ak3-core.sh                   AnyKernel3 core (modified)
  tools/ksucleanup.sh                 legacy KernelSU user-space cleanup
  tools/*                             busybox / magiskboot / fec / …  (AnyKernel3 toolset)
  META-INF/…                          recovery entry files
config/                               kernel configuration fragments
dtb/2005-dtb.bin                      reference device tree (447,435 bytes)
dtb/2005-dtb-ramoops.bin              same tree + ramoops node (debug builds, 447,732 bytes)
scripts/pack.sh                       packaging: Image + DTB → Image.gz-dtb → ZIP
scripts/selftest.sh                   local validation of packaging and cleanup logic
```

---

## 10. Local validation (no compilation required)

```bash
bash scripts/selftest.sh [/path/to/Image]
```

The self-test covers four areas:

1. shell syntax of `anykernel.sh`, `ksucleanup.sh` and `pack.sh`;
2. cleanup logic against a simulated `/data/adb` (backup creation, removal from the original location, `/data/adb/modules` preserved, `do.ksucleanup=0` and `=1` both honoured);
3. packaging in `dtb_2005` mode (ZIP integrity, gzip stream, appended DTB, absence of Magisk patch code, presence of the cleanup call);
4. `flash_dtbo` insertion (dtbo packaged and `flash_dtbo;` inserted exactly once).

Packaging can also be exercised directly:

```bash
KERNEL_IMG=/path/to/Image DTB_MODE=dtb_2005 TAG=local bash scripts/pack.sh
```

---

## 11. Relationship to the reference "2005" kernel

The reference kernel in this project is `4.14.336-Rikka-V2-2005-remake`. Excluding rooting and boot-patching topics, differences fall into four categories:

### 11.1 Upstream version

| | Reference | Default source tree |
|---|---|---|
| Linux stable | 4.14.336 | 4.14.357 (+21 stable releases) |

### 11.2 Compile-time features

The reference values were measured from the shipped Image; the source-tree values were read from `raphael_defconfig`.

| Option | Reference | Source tree | Alignment |
|---|---|---|---|
| `MODULES` | n | default y | targeted by `slim-safe`/plus |
| `FTRACE` | n | default y | targeted by `slim-safe`/plus |
| `DEBUG_FS`, `MMC`, `PCI`, `MHI_BUS`, `CORESIGHT`, `SQUASHFS`, `LZO`, LMK | n | default n | already identical |
| `UCLAMP_TASK` | n | y | `plus` only (retained in `safe` deliberately) |
| `WIREGUARD`, `NTFS_FS`, `EROFS_FS`, `EXFAT_FS`, `NET_SCH_FQ_CODEL`, `ZRAM`, SELinux | y | y | already identical |
| `TCP_CONG_BBR`, `TCP_CONG_WESTWOOD` | y | n | enabled by `features-2005` |
| `KALLSYMS` | indeterminate from binary | n | opt-in via `extra-kallsyms` |
| `IKCONFIG` | n | y | retained (useful for post-flash inspection) |

The CI run prints the **actual** post-build values of these options, so alignment is verifiable per build rather than assumed.

### 11.3 Device tree and runtime tuning

With `dtb_mode=dtb_2005` the reference device tree is appended verbatim, preserving:

* EAS `capacity-dmips-mhz` (488 / 1024) and per-CPU `freq-energy-model`;
* recalculated `energy-costs` `busy-cost-data` tables;
* `qcom,cpufreq-table-0/4/7`;
* UFS `pm-qos-cpu-group-latency-us` (100 µs × 8 groups) and glink/cdsp `qos-latency-us` (67);
* GPU `opp-690000000`, `rpmh-regulator-ldoa13` (2,704,000 µV), disabled `jtagmm` nodes, removed CoreSight nodes;
* the reference `/chosen/bootargs`.

### 11.4 Not reproducible

* Private source-level changes made by the reference authors. The shipped images are stripped, have no symbol table (`CONFIG_KALLSYMS=n`), and no matching configuration is available, so a function-level reconstruction is not possible from the binaries alone.
* The reference boot header command line (`console=… buildvariant=userdebug`). The installer deliberately preserves the command line of the target ROM.
* Code-generation differences caused by different compiler builds (reference: clang 18.1.0rc + LLD; pipeline: r547379).

---

## 12. Diagnosing a boot hang

A flash that leaves the device at the OEM boot logo ("stuck at Mi") can originate from several layers. Classify the symptom first, then collect evidence.

### 12.1 Stage classification

| Symptom | Layer | Typical cause |
|---|---|---|
| Logo appears, then immediate reboot / black screen, no USB reaction | Kernel decompression or early init | kernel image/DTB incompatible, truncated image, wrong payload layout |
| Stuck at logo, device enumerated by `fastboot` but not `adb`, no kernel log | Early kernel init before console | DTB/SoC variant mismatch, memory reservation conflict |
| Boot proceeds, hangs at second stage or at boot animation | Userspace | missing vendor modules, manager/module conflict, SELinux policy |

### 12.2 Evidence collection

| Source | Availability | Command |
|---|---|---|
| `pstore` / `ramoops` console log | only if the booted DTB declares a `ramoops` reservation; build with `debug_ramoops=true` | `ls -l /sys/fs/pstore/` then `cat /sys/fs/pstore/console-ramoops*` |
| `/proc/last_kmsg` | not present in these kernels | — |
| Recovery `dmesg` | reflects the **recovery** kernel, not the flashed one | do not use for attribution |
| UART / `earlycon` | requires a modified boot cmdline | out of scope for this installer |
| Empty `fastboot boot` test | isolates image content from partition writes | `fastboot boot <boot image>` |

### 12.3 Known risk factors for this pipeline

| Risk | Detail | Mitigation |
|---|---|---|
| **SoC variant mismatch** | `dtb/2005-dtb.bin` contains a single FDT with `qcom,msm-id = <339 0x20000>` (SM8150 v2). The reference ROM boot image carries four variants (SM8150 v1/v2, SM8150P v1/v2). On an SM8150P device (`msm-id 361`) or a v1 part there is no matching entry. | check `cat /sys/devices/soc0/machine`; use `dtb_mode=tree_dtb` (the source tree's DTBs cover 339 and 361) |
| No `ramoops` in the reference DTB | the reference DTBs declare no `ramoops` reservation, so no post-mortem log is written | build with `debug_ramoops=true` |
| `MODULES=n` (slim levels) | Android 13-era ROMs may ship loadable modules under `/vendor/lib/modules` or a `vendor_dlkm` partition; a monolithic kernel cannot load them | inspect `ls /vendor/lib/modules`; if non-empty use `slim_level=none` |
| KernelSU integration mismatch | `ksu_commit` pinned to a tag incompatible with the tree | leave `ksu_commit` empty (tree version) when bisecting |
| Image write / AVB | repacked image rejected or wrong partition written | verify `fastboot boot` and the flash target; the installer writes `boot` only |

### 12.4 Bisection matrix

| Attempt | `dtb_mode` | `slim_level` | Purpose |
|---|---|---|---|
| 1 | `tree_dtb` | `none` | most conservative: tree-matched DTB, no configuration trimming |
| 2 | `dtb_2005` | `none` | isolates the reference tuning from configuration trimming |
| 3 | `tree_dtb` | `safe` | isolates trimming from the DTB |
| 4 | default | default | full "2005-like" configuration |

Change one dimension per attempt; a booting build narrows the cause to the dimension that changed.

## 13. Third-party components

| Component | Purpose | Upstream |
|---|---|---|
| SOVIET-ANDROID `kernel_xiaomi_raphael` | default kernel source (4.14.357) | GitHub |
| KernelSU-Next | kernel-side root integration | GitHub |
| SUSFS | syscall/path hiding additions | GitLab (simonpunk) |
| AnyKernel3 (osm0sis) and toolset | installer framework, `magiskboot`, `busybox` | XDA / GitHub |
| AOSP clang r547379 (crDroid prebuilt) | build toolchain | GitLab |

Third-party binaries bundled under `ak3/tools/` retain their original licenses. The scripts and workflow in this repository are provided as-is, without warranty; flashing modified boot images can render a device unbootable, so keep a boot backup.

</details>
