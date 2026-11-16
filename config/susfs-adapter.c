// SPDX-License-Identifier: GPL-2.0
/* SUSFS v2.2 NON-GKI adapter for pinned KernelSU Next e5f5ec99.
 * Keep Next's LSM setuid hook, credential handling, and unmount implementation.
 * Filesystem port: simonpunk SUSFS, via Fansirsqi/raphael-kernel 2a723dc6.
 */
#include <linux/cred.h>
#include <linux/security.h>
#include <linux/string.h>
#include <linux/susfs.h>
#include <linux/workqueue.h>
#include "compat/susfs.h"
#include "policy/allowlist.h"
#include "selinux/selinux.h"

u32 susfs_ksu_sid;
u32 susfs_priv_app_sid;
extern bool ksu_kernel_umount_enabled;
extern struct work_struct susfs_extra_works;

bool susfs_is_current_ksu_domain(void)
{
	return is_ksu_domain();
}

bool susfs_is_current_init_domain(void)
{
	return is_init(current_cred());
}

void ksu_susfs_policy_loaded(void)
{
	security_secctx_to_secid(KERNEL_SU_CONTEXT, strlen(KERNEL_SU_CONTEXT),
				&susfs_ksu_sid);
	security_secctx_to_secid("u:r:priv_app:s0:c512,c768",
				strlen("u:r:priv_app:s0:c512,c768"),
				&susfs_priv_app_sid);
}

void ksu_susfs_after_setuid(uid_t new_uid)
{
	/* Same namespace-safety checks as Next's kernel_umount.c.
	 * Marking is also needed when there are no mounted filesystem modules.
	 * Never change the global namespace of a non-zygote su process.
	 */
	if (!ksu_kernel_umount_enabled || !is_zygote(current_cred()))
		return;
	if (!is_appuid(new_uid) && new_uid != WEBVIEW_ZYGOTE_UID &&
	    !is_isolated_process(new_uid))
		return;
	if (!ksu_uid_should_umount(new_uid) && !is_isolated_process(new_uid))
		return;
	susfs_set_current_proc_umounted();
#ifdef CONFIG_KSU_SUSFS_SUS_PATH
	schedule_work(&susfs_extra_works);
#endif
}

void ksu_susfs_post_fs_data(void)
{
	/* on_post_fs_data() has a once-only guard; policy and /data are ready. */
	susfs_start_sdcard_monitor_fn();
}

void ksu_susfs_reboot(unsigned int cmd, void __user **arg)
{
	/* Caller checks SUSFS_MAGIC and real uid 0 before reaching this API.
	 * SUSFS returns status in the userspace command structure.
	 */
	switch (cmd) {
#ifdef CONFIG_KSU_SUSFS_SUS_PATH
	case CMD_SUSFS_ADD_SUS_PATH:
		susfs_add_sus_path(arg); break;
	case CMD_SUSFS_ADD_SUS_PATH_LOOP:
		susfs_add_sus_path_loop(arg); break;
#endif
#ifdef CONFIG_KSU_SUSFS_SUS_MOUNT
	case CMD_SUSFS_HIDE_SUS_MNTS_FOR_NON_SU_PROCS:
		susfs_set_hide_sus_mnts_for_non_su_procs(arg); break;
#endif
#ifdef CONFIG_KSU_SUSFS_SUS_KSTAT
	case CMD_SUSFS_ADD_SUS_KSTAT:
	case CMD_SUSFS_ADD_SUS_KSTAT_STATICALLY:
		susfs_add_sus_kstat(arg); break;
	case CMD_SUSFS_UPDATE_SUS_KSTAT:
		susfs_update_sus_kstat(arg); break;
#endif
#ifdef CONFIG_KSU_SUSFS_SPOOF_UNAME
	case CMD_SUSFS_SET_UNAME:
		susfs_set_uname(arg); break;
#endif
#ifdef CONFIG_KSU_SUSFS_ENABLE_LOG
	case CMD_SUSFS_ENABLE_LOG:
		susfs_enable_log(arg); break;
#endif
#ifdef CONFIG_KSU_SUSFS_SPOOF_CMDLINE_OR_BOOTCONFIG
	case CMD_SUSFS_SET_CMDLINE_OR_BOOTCONFIG:
		susfs_set_cmdline_or_bootconfig(arg); break;
#endif
#ifdef CONFIG_KSU_SUSFS_OPEN_REDIRECT
	case CMD_SUSFS_ADD_OPEN_REDIRECT:
		susfs_add_open_redirect(arg); break;
#endif
#ifdef CONFIG_KSU_SUSFS_SUS_MAP
	case CMD_SUSFS_ADD_SUS_MAP:
		susfs_add_sus_map(arg); break;
#endif
	case CMD_SUSFS_ENABLE_AVC_LOG_SPOOFING:
		susfs_set_avc_log_spoofing(arg); break;
	case CMD_SUSFS_SHOW_ENABLED_FEATURES:
		susfs_get_enabled_features(arg); break;
	case CMD_SUSFS_SHOW_VARIANT:
		susfs_show_variant(arg); break;
	case CMD_SUSFS_SHOW_VERSION:
		susfs_show_version(arg); break;
	default:
		break;
	}
}
