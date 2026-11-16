"""Port frozen non-GKI hooks onto Next v3.4.2, preserving release UAPI files."""
import hashlib
import json
import pathlib
import shutil
import subprocess
import sys

root = pathlib.Path(sys.argv[1]).resolve()
legacy = pathlib.Path(sys.argv[2]).resolve()
ksu = root / 'drivers/staging/kernelsu'
assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ksu).decode().strip() == '4c706b5938665866ebe16944a481a7b91e3396af'
assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=legacy).decode().strip() == '8af3d4fec33be32fa5d3f8dae4f380fac45bf2cd'
uapi_before = {p.relative_to(ksu).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in (ksu / 'uapi').rglob('*') if p.is_file()}
paths = ['Kbuild', 'Kconfig', 'Makefile', 'compat/kernel_compat.c', 'compat/kernel_compat.h',
         'feature/sucompat.c', 'feature/sucompat.h', 'feature/selinux_hide.c', 'feature/selinux_hide.h',
         'feature/kernel_umount.c', 'infra/file_wrapper.c',
         'infra/seccomp_cache.c', 'infra/seccomp_cache.h', 'infra/su_mount_ns.c',
         'manager/pkg_observer.c', 'manager/pkg_observer_defs.h', 'include/util.h',
         'hook/hook_manager.c', 'hook/hook_manager.h',
         'hook/lsm_hooks.c', 'hook/setuid_hook.c', 'hook/setuid_hook.h', 'hook/syscall_table_hook.h',
         'runtime/ksud_integration.c', 'runtime/ksud.h', 'include/arch.h',
         'selinux/selinux.c', 'selinux/selinux.h', 'selinux/rules.c',
         'selinux/sepolicy.c', 'selinux/sepolicy.h']
for name in paths:
    dst = ksu / 'kernel' / name
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(legacy / 'kernel' / name, dst)


def replace(path, old, new):
    p = ksu / 'kernel' / path
    s = p.read_text(encoding='utf-8')
    if s.count(old) != 1:
        raise RuntimeError((path, old[:70], s.count(old)))
    p.write_text(s.replace(old, new), encoding='utf-8', newline='\n')


replace('Kbuild', 'kernelsu-objs := core/init.o',
        'KSU_VERSION_OVERRIDE := 33355\nKSU_VERSION_TAG_OVERRIDE := v3.4.2-raphael\n'
        'kernelsu-objs := core/init.o\nkernelsu-objs += feature/module_blacklist.o\n'
        'kernelsu-objs += feature/shell_su_adb_only.o\nkernelsu-objs += infra/symbol_resolver.o')
replace('Kbuild', 'ccflags-y += -I$(KSU_KERNEL_DIR) -I$(KSU_KERNEL_DIR)/include',
        'ccflags-y += -I$(KSU_KERNEL_DIR) -I$(KSU_KERNEL_DIR)/include\n'
        'ccflags-y += -include $(KSU_KERNEL_DIR)/compat/kernel_compat.h')
replace('compat/kernel_compat.h', '#include <linux/version.h>',
        '#include <linux/version.h>\n#include <linux/poll.h>\n'
        '#if LINUX_VERSION_CODE < KERNEL_VERSION(4, 16, 0)\n'
        'typedef unsigned int __poll_t;\n'
        '#ifndef EPOLLIN\n#define EPOLLIN POLLIN\n#define EPOLLRDNORM POLLRDNORM\n'
        '#define EPOLLHUP POLLHUP\n#endif\n#endif\n'
        '#ifndef fallthrough\n#define fallthrough __attribute__((__fallthrough__))\n#endif')
replace('include/arch.h', '#define PT_REGS_PARM1(x) (__PT_REGS_CAST(x)->__PT_PARM1_REG)',
        '#define PT_REGS_PARM1(x) (__PT_REGS_CAST(x)->__PT_PARM1_REG)\n'
        '#define PT_REGS_SYSCALL_PARM1(x) PT_REGS_PARM1(x)')
replace('sulog/event.c', '#include <linux/minmax.h>', '#include <linux/kernel.h>')
replace('sulog/event.c', '#include <linux/uaccess.h>',
        '#include <linux/uaccess.h>\n#include <linux/timekeeping.h>\n'
        '#if LINUX_VERSION_CODE < KERNEL_VERSION(4, 19, 0)\n'
        '#define ktime_get_boottime_ts64 get_monotonic_boottime\n#endif')
# Keep the release's user-pointer handling and command implementations.
# Only replace the kprobe entry with the equivalent built-in syscall entry.
p = ksu / 'kernel/supercall/supercall.c'
s = p.read_text(encoding='utf-8')
begin = s.index('static int reboot_handler_pre(')
commands = s.index('    /* Check if this is a request to install KSU fd */', begin)
end = s.index('\nstatic struct kprobe reboot_kp', commands)
s = (s[:begin] +
     'int ksu_handle_sys_reboot(int magic1, int magic2, unsigned int cmd, void __user **arg)\n'
     '{\n    unsigned long arg4 = (unsigned long)*arg;\n'
     '    unsigned long reply = arg4;\n'
     '    if (magic1 != KSU_INSTALL_MAGIC1)\n        return 0;\n\n' +
     s[commands:end] +
     '\nvoid __init ksu_supercalls_init(void)\n{\n    ksu_supercall_dump_commands();\n}\n'
     '\nvoid __exit ksu_supercalls_exit(void)\n{\n    ksu_supercall_cleanup_state();\n}\n')
assert 'void __user **ppptr = (void __user **)arg4;' in s
assert 'register_kprobe' not in s
p.write_text(s, encoding='utf-8', newline='\n')
replace('core/init.c', '#include "hook/syscall_hook_manager.h"', '#include "hook/hook_manager.h"')
replace('core/init.c', '#include "hook/syscall_hook.h"',
        'extern void ksu_lsm_hook_init(void);\nextern void ksu_lsm_hook_exit(void);\n'
        'struct user_arg_ptr;\n'
        'extern int ksu_handle_execveat_ksud(int *, struct filename **, struct user_arg_ptr *, struct user_arg_ptr *, int *);\n'
        'extern int ksu_handle_execveat_sucompat(int *, struct filename **, void *, void *, int *);\n'
        'int ksu_handle_execveat(int *fd, struct filename **filename, void *argv, void *envp, int *flags)\n'
        '{\n\tksu_handle_execveat_ksud(fd, filename, (struct user_arg_ptr *)argv, (struct user_arg_ptr *)envp, flags);\n'
        '\treturn ksu_handle_execveat_sucompat(fd, filename, argv, envp, flags);\n}')
replace('core/init.c', '\tksu_syscall_hook_init();', '\t/* Built-in manual VFS hooks: no syscall table patching. */')
replace('selinux/selinux.h', 'bool is_zygote(const struct cred* cred);',
        'bool is_zygote(const struct cred* cred);\nbool is_adbd(const struct cred *cred);')
replace('selinux/selinux.c', 'static u32 cached_init_sid __read_mostly = 0;',
        'static u32 cached_init_sid __read_mostly = 0;\nstatic u32 cached_adbd_sid __read_mostly;')
replace('selinux/selinux.c', '    err = security_secctx_to_secid(KSU_FILE_CONTEXT, strlen(KSU_FILE_CONTEXT),',
        '    err = security_secctx_to_secid("u:r:adbd:s0", strlen("u:r:adbd:s0"), &cached_adbd_sid);\n'
        '    if (err)\n        cached_adbd_sid = 0;\n\n'
        '    err = security_secctx_to_secid(KSU_FILE_CONTEXT, strlen(KSU_FILE_CONTEXT),')
replace('selinux/selinux.c', 'bool is_zygote(const struct cred *cred)',
        'bool is_adbd(const struct cred *cred)\n{\n'
        '    return is_sid_match(cred, cached_adbd_sid, "u:r:adbd:s0");\n}\n\n'
        'bool is_zygote(const struct cred *cred)')
# The release's allowlist checks shell_su_adb_only only for SHELL_UID.
# Manual sucompat calls that same authorization function; do not add a
# second unconditional ancestor check that would block non-shell apps.
# 4.14 releases filters with put_seccomp_filter(), not the newer
# seccomp_filter_release(). Preserve the release's credential/accounting
# fixes, replacing only this function with the version-aware legacy helper.
p = ksu / 'kernel/policy/app_profile.c'
s = p.read_text(encoding='utf-8')
compat_profile = (legacy / 'kernel/policy/app_profile.c').read_text(encoding='utf-8')
start = s.index('static void disable_seccomp(void)')
end = s.index('int escape_with_root_profile(void)', start)
compat_start = compat_profile.index('void disable_seccomp(void)')
compat_end = compat_profile.index('int escape_with_root_profile(void)', compat_start)
s = s[:start] + compat_profile[compat_start:compat_end] + s[end:]
p.write_text(s, encoding='utf-8', newline='\n')
replace('hook/setuid_hook.c', 'extern void disable_seccomp(struct task_struct *tsk);',
        'extern void disable_seccomp(void);')
p = ksu / 'kernel/hook/setuid_hook.c'
s = p.read_text(encoding='utf-8')
assert s.count('disable_seccomp(current);') == 2
p.write_text(s.replace('disable_seccomp(current);', 'disable_seccomp();'), encoding='utf-8', newline='\n')
p = ksu / 'kernel/runtime/ksud_integration.c'
s = p.read_text(encoding='utf-8')
s = '#include "policy/feature.h"\n' + s
assert 1 <= s.count('setup_ksu_cred();') <= 4
s = s.replace('setup_ksu_cred();', 'setup_ksu_cred();\n\t\t\t\tksu_feature_apply_forced();')
p.write_text(s, encoding='utf-8', newline='\n')
# A built-in LSM has no unregister operation. This port requires CONFIG_KSU=y.
p = ksu / 'kernel/hook/lsm_hooks.c'
p.write_text(p.read_text(encoding='utf-8') + '\nvoid __exit ksu_lsm_hook_exit(void) {}\n', encoding='utf-8', newline='\n')
# The legacy hook manager provides marking compatibility; use its declarations.
replace('policy/app_profile.c', '#include "hook/tp_marker.h"', '#include "hook/hook_manager.h"')
replace('supercall/dispatch.c', '#include "hook/tp_marker.h"', '#include "hook/hook_manager.h"')
# Task syscall marks are a dynamic-hook facility. Manual hooks need no marks.
p = ksu / 'kernel/hook/hook_manager.h'
s = p.read_text(encoding='utf-8')
anchor = '\n#endif\n\n#endif'
assert s.count(anchor) == 1
s = s.replace(anchor, '\n#else\n'
    'static inline void ksu_mark_all_process(void) {}\n'
    'static inline void ksu_unmark_all_process(void) {}\n'
    'static inline void ksu_mark_running_process(void) {}\n'
    'static inline void ksu_set_task_tracepoint_flag(struct task_struct *t) {}\n'
    'static inline void ksu_clear_task_tracepoint_flag_if_needed(struct task_struct *t) {}\n'
    'static inline int ksu_get_task_mark(pid_t pid) { return -EOPNOTSUPP; }\n'
    'static inline int ksu_set_task_mark(pid_t pid, bool mark) { return -EOPNOTSUPP; }\n'
    '#endif\n\n#endif')
p.write_text(s, encoding='utf-8', newline='\n')
replace('supercall/dispatch.c', '#ifdef CONFIG_HAVE_SYSCALL_TRACEPOINTS',
        '#if defined(CONFIG_KSU_MANUAL_HOOK)\n    strscpy(cmd.mode, "Manual", sizeof(cmd.mode));\n'
        '#elif defined(CONFIG_HAVE_SYSCALL_TRACEPOINTS)')
# Old SELinux policy_rwlock readers spin with preemption disabled. Keep that
# contract on the writer too, and use non-sleeping allocations while locked.
p = ksu / 'kernel/selinux/rules.c'
s = p.read_text(encoding='utf-8')
start = '\t/*\n\t * HACK: write_lock() is held with preempt enabled.'
for end, replacement in [
    ('\tgoto out_flush;', '\twrite_lock(lock);\n\tapply_kernelsu_rules_fn((void *)db);\n\twrite_unlock(lock);\n\tgoto out_flush;'),
    ('\tgoto out_done;', '\twrite_lock(lock);\n\tret = handle_sepolicy_fn((void *)&ctx);\n\twrite_unlock(lock);\n\tgoto out_done;'),
]:
    begin = s.index(start)
    finish = s.index(end, begin) + len(end)
    s = s[:begin] + replacement + s[finish:]
assert 'HACK: write_lock() is held with preempt enabled' not in s
p.write_text(s, encoding='utf-8', newline='\n')
p = ksu / 'kernel/selinux/sepolicy.c'
s = p.read_text(encoding='utf-8')
s = s.replace('GFP_KERNEL', 'ksu_sepolicy_gfp()')
s = ('#include <linux/preempt.h>\n#include <linux/gfp.h>\n'
     'static inline gfp_t ksu_sepolicy_gfp(void)\n'
     '{ return in_atomic() || irqs_disabled() ? GFP_ATOMIC : GFP_KERNEL; }\n' + s)
p.write_text(s, encoding='utf-8', newline='\n')
uapi_after = {p.relative_to(ksu).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in (ksu / 'uapi').rglob('*') if p.is_file()}
assert uapi_before == uapi_after
assert 'KERNEL_SU_UAPI_VERSION = 5;' in (ksu / 'uapi/supercall.h').read_text()
subprocess.run(['git', 'add', '-N'] + ['kernel/' + name for name in paths], cwd=ksu, check=True)
evidence = root.parent / 'evidence'
evidence.mkdir(exist_ok=True)
(evidence / 'release-port.json').write_text(json.dumps({'release_tag': 'v3.4.2',
    'release_commit': '4c706b5938665866ebe16944a481a7b91e3396af',
    'manual_hook_reference': '8af3d4fec33be32fa5d3f8dae4f380fac45bf2cd',
    'copied_compatibility_files': paths, 'release_uapi_files_unchanged': uapi_after,
    'release_supercall_implementation_retained': True,
    'compatibility_function_overrides': ['policy/app_profile.c:disable_seccomp'],
    'uapi_version': 5}, indent=2), encoding='utf-8')
print('Prepared Next v3.4.2 with frozen non-GKI hook port; release UAPI 5 files unchanged')
