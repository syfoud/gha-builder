/* SPDX-License-Identifier: GPL-2.0 */
#ifndef RIKKA_KSU_SUSFS_ADAPTER_H
#define RIKKA_KSU_SUSFS_ADAPTER_H
#include <linux/types.h>
#include <linux/uaccess.h>
void ksu_susfs_policy_loaded(void);
void ksu_susfs_after_setuid(uid_t new_uid);
void ksu_susfs_reboot(unsigned int cmd, void __user **arg);
void ksu_susfs_post_fs_data(void);
#endif
