"""Apply the reviewed SUSFS filesystem port without replacing the Next framework."""
import pathlib
import shutil
import subprocess
import sys

root = pathlib.Path(sys.argv[1]).resolve()
builder = pathlib.Path(__file__).resolve().parent.parent
ksu = root / 'drivers/staging/kernelsu/kernel'


def replace(path, old, new, expected=1):
    p = ksu / path
    s = p.read_text(encoding='utf-8')
    if s.count(old) != expected:
        raise RuntimeError(f'{path}: expected {expected} matches, got {s.count(old)}')
    p.write_text(s.replace(old, new), encoding='utf-8', newline='\n')


subprocess.run(['git', 'apply', '--check', '--whitespace=nowarn', str(builder / 'patches/rikka-susfs-2.2.0.patch')], cwd=root, check=True)
subprocess.run(['git', 'apply', '--whitespace=nowarn', str(builder / 'patches/rikka-susfs-2.2.0.patch')], cwd=root, check=True)
# The reference's first stat hunk also declares ReSukiSU inline hooks.
# Rikka already has Next manual hooks using a user filename pointer.
stat_path = root / 'fs/stat.c'
stat_text = stat_path.read_text(encoding='utf-8')
foreign_decls = ('#ifdef CONFIG_KSU_SUSFS\n'
    'extern struct static_key_true ksu_is_init_rc_hook_enabled;\n'
    'extern void ksu_handle_vfs_fstat(int fd, loff_t *kstat_size_ptr);\n'
    'extern struct static_key_true ksu_su_compat_enabled;\n'
    'extern bool __ksu_is_allow_uid_for_current(uid_t uid);\n'
    'extern int ksu_handle_stat(int *dfd, struct filename **filename, int *flags);\n'
    '#endif // #ifdef CONFIG_KSU_SUSFS\n')
assert stat_text.count(foreign_decls) == 1
stat_path.write_text(stat_text.replace(foreign_decls, ''), encoding='utf-8', newline='\n')
for source, target in [('susfs-adapter.c', 'compat/susfs.c'), ('susfs-adapter.h', 'compat/susfs.h'),
                       ('susfs.Kconfig', 'compat/susfs.Kconfig')]:
    shutil.copyfile(builder / 'config' / source, ksu / target)
replace('Kbuild', 'kernelsu-objs := core/init.o',
        'kernelsu-objs := core/init.o\nifeq ($(CONFIG_KSU_SUSFS),y)\n'
        'kernelsu-objs += compat/susfs.o\nendif')
replace('Kconfig', '\nendmenu',
        '\nsource "drivers/staging/kernelsu/kernel/compat/susfs.Kconfig"\n\nendmenu')
for path in ['core/init.c', 'hook/setuid_hook.c', 'runtime/boot_event.c',
             'selinux/rules.c', 'supercall/supercall.c']:
    p = ksu / path
    s = p.read_text(encoding='utf-8')
    p.write_text('#ifdef CONFIG_KSU_SUSFS\n#include <linux/susfs.h>\n#include "compat/susfs.h"\n#endif\n' + s,
                 encoding='utf-8', newline='\n')
replace('core/init.c', '\t\tksu_ksud_init();',
        '#ifdef CONFIG_KSU_SUSFS\n\t\tsusfs_init();\n#endif\n\t\tksu_ksud_init();')
replace('feature/kernel_umount.c', 'static bool ksu_kernel_umount_enabled = true;',
        'bool ksu_kernel_umount_enabled = true;')
replace('hook/setuid_hook.c', '    ksu_handle_umount(old_uid, new_uid);',
        '    ksu_handle_umount(old_uid, new_uid);\n#ifdef CONFIG_KSU_SUSFS\n'
        '\tksu_susfs_after_setuid(new_uid);\n#endif')
replace('runtime/boot_event.c', 'ksu_selinux_hide_handle_post_fs_data();',
        'ksu_selinux_hide_handle_post_fs_data();\n#ifdef CONFIG_KSU_SUSFS\n'
        '\tksu_susfs_post_fs_data();\n#endif')
replace('selinux/rules.c', '\treset_avc_cache();\n#endif\n}',
        '\treset_avc_cache();\n#endif\n#ifdef CONFIG_KSU_SUSFS\n'
        '\tksu_susfs_policy_loaded();\n#endif\n}')
replace('supercall/supercall.c', '    if (magic1 != KSU_INSTALL_MAGIC1)',
        '#ifdef CONFIG_KSU_SUSFS\n\tif (magic1 == KSU_INSTALL_MAGIC1 && magic2 == SUSFS_MAGIC && current_uid().val == 0) {\n'
        '\t\tksu_susfs_reboot(cmd, arg);\n\t\treturn 0;\n\t}\n#endif\n'
        '    if (magic1 != KSU_INSTALL_MAGIC1)')
replace('policy/app_profile.c', '#include <linux/capability.h>',
        '#include <linux/capability.h>\n#ifdef CONFIG_KSU_SUSFS\n#include <linux/susfs_def.h>\n#endif')
replace('policy/app_profile.c', '    commit_creds(cred);',
        '    commit_creds(cred);\n#ifdef CONFIG_KSU_SUSFS\n'
        '    susfs_clear_current_proc_umounted();\n'
        '    susfs_clear_current_proc_umounted_for_zygote_next();\n'
        '    susfs_clear_current_proc_no_su();\n#endif', expected=2)
subprocess.run(['git', 'add', '-N', 'fs/susfs.c', 'include/linux/susfs.h',
                'include/linux/susfs_def.h'], cwd=root, check=True)
subprocess.run(['git', 'add', '-N', 'kernel/compat/susfs.c', 'kernel/compat/susfs.h',
                'kernel/compat/susfs.Kconfig'], cwd=ksu.parent, check=True)
print('Applied SUSFS v2.2.0 filesystem port and checked Next-only adapter')
