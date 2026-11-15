#!/sbin/sh
# ksucleanup.sh —— 旧 KernelSU(官方线) 用户态残留清理（备份后移除，可回滚）
# 背景: 本包内核集成 KernelSU-Next，与官方 KernelSU 共用 /data/adb/ksu 路径，
#       但 allowlist / ksud 格式不同，旧数据会导致新管理器"能装但授权无效"。
# 用法: . tools/ksucleanup.sh; ksu_cleanup_legacy
# 可覆盖: ADBDIR(默认 /data/adb)、KSU_TS(时间戳)、KSU_CLEANUP(1/0)

ksu_cleanup_legacy() {
  ADBDIR="${ADBDIR:-/data/adb}";
  KSU_TS="${KSU_TS:-$(date +%Y%m%d-%H%M%S 2>/dev/null || echo unknown)}";
  # 开关来源: 刷机时读 anykernel.sh 的 do.ksucleanup；本地测试可用 KSU_CLEANUP 覆盖
  if [ -n "${home:-}" ] && [ -f "${home}/anykernel.sh" ]; then
    ENABLED="$(file_getprop "${home}/anykernel.sh" do.ksucleanup 2>/dev/null || true)";
    [ -n "$ENABLED" ] || ENABLED=1;
  else
    ENABLED="${KSU_CLEANUP:-1}";
  fi;

  if [ "$ENABLED" != "1" ]; then
    ui_print " " "KernelSU 残留清理已关闭 (do.ksucleanup=0)";
    return 0;
  fi;

  if [ ! -d "$ADBDIR" ]; then
    ui_print " " "未挂载 /data，跳过 KernelSU 残留清理";
    return 0;
  fi;

  BAK="$ADBDIR/ksu-legacy-backup-$KSU_TS";
  ui_print " " "清理旧 KernelSU 用户态残留（备份到 $BAK）";

  if [ -e "$ADBDIR/ksu" ]; then
    mkdir -p "$BAK";
    if mv -f "$ADBDIR/ksu" "$BAK/ksu" 2>/dev/null; then
      ui_print "   /data/adb/ksu -> $BAK/ksu";
    else
      ui_print "   !! 无法移动 /data/adb/ksu";
    fi;
  fi;

  if [ -e "$ADBDIR/ksud" ]; then
    mkdir -p "$BAK";
    if mv -f "$ADBDIR/ksud" "$BAK/ksud" 2>/dev/null; then
      ui_print "   /data/adb/ksud -> $BAK/ksud";
    else
      ui_print "   !! 无法移动 /data/adb/ksud";
    fi;
  fi;

  for f in modules_update.img ksud.old ksu.old; do
    if [ -e "$ADBDIR/$f" ]; then
      mkdir -p "$BAK";
      mv -f "$ADBDIR/$f" "$BAK/" 2>/dev/null;
    fi;
  done;

  ui_print " " "注意: 请卸载旧的 KernelSU 管理器，再安装 KernelSU-Next 管理器";
  ui_print " " "回滚方法: mv $BAK/ksu $ADBDIR/ksu ; mv $BAK/ksud $ADBDIR/ksud";
  return 0;
}