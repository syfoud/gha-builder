"""Small, checked integration changes for the pinned Rikka source only."""
import pathlib
import sys

root = pathlib.Path(sys.argv[1]).resolve()

def replace(path, old, new):
    p = root / path
    s = p.read_text()
    if s.count(old) != 1:
        raise RuntimeError(f'{path}: expected one match, got {s.count(old)}')
    p.write_text(s.replace(old, new))

# Report the real final configuration, rather than an unrelated defconfig.
replace('kernel/Makefile',
        '$(obj)/config_data.gz: arch/arm64/configs/sm8150-perf_defconfig FORCE',
        '$(obj)/config_data.gz: .config FORCE')

# Restore Android's perf_event_paranoid=3 functionality, removed from this
# source although its defconfig still requests SECURITY_PERF_EVENTS_RESTRICT.
# Adapted from Google's ANDROID security,perf patch (Iff5bff4fc1042e85866df9faa01bce8d04335ab8).
replace('security/Kconfig', 'config SECURITY\n',
        'config SECURITY_PERF_EVENTS_RESTRICT\n'
        '\tbool "Restrict unprivileged use of performance events"\n'
        '\tdepends on PERF_EVENTS\n'
        '\thelp\n'
        '\t  Set kernel.perf_event_paranoid to 3 by default. No unprivileged\n'
        '\t  perf_event_open calls are allowed unless this sysctl is lowered.\n\n'
        'config SECURITY\n')
replace('kernel/events/core.c',
        'int sysctl_perf_event_paranoid __read_mostly = 2;',
        '#ifdef CONFIG_SECURITY_PERF_EVENTS_RESTRICT\n'
        'int sysctl_perf_event_paranoid __read_mostly = 3;\n'
        '#else\nint sysctl_perf_event_paranoid __read_mostly = 2;\n#endif')
replace('include/linux/perf_event.h',
        'static inline int perf_is_paranoid(void)',
        'static inline bool perf_paranoid_any(void)\n'
        '{\n\treturn sysctl_perf_event_paranoid > 2;\n}\n\n'
        'static inline int perf_is_paranoid(void)')
replace('kernel/events/core.c',
        '\t/* Do we allow access to perf_event_open(2) ? */',
        '\tif (perf_paranoid_any() && !capable(CAP_SYS_ADMIN))\n'
        '\t\treturn -EACCES;\n\n'
        '\t/* Do we allow access to perf_event_open(2) ? */')

# Existing Rikka manual hooks cover exec, access, stat, read and input.
# Do not enter the KSU Kbuild (which performs backports) in the control build.
replace('drivers/staging/Makefile',
        'obj-y\t\t\t\t+= kernelsu/kernel/',
        'obj-$(CONFIG_KSU)\t\t+= kernelsu/kernel/')

# The modern userspace protocol additionally needs the reboot supercall,
# before the normal CAP_SYS_BOOT permission check.
replace('kernel/reboot.c',
        'SYSCALL_DEFINE4(reboot, int, magic1, int, magic2, unsigned int, cmd,',
        '#ifdef CONFIG_KSU\n'
        'extern int ksu_handle_sys_reboot(int magic1, int magic2, unsigned int cmd, void __user **arg);\n'
        '#endif\n\n'
        'SYSCALL_DEFINE4(reboot, int, magic1, int, magic2, unsigned int, cmd,')
replace('kernel/reboot.c',
        '\t/* We only trust the superuser with rebooting the system. */',
        '#ifdef CONFIG_KSU\n'
        '\tksu_handle_sys_reboot(magic1, magic2, cmd, &arg);\n'
        '#endif\n\n'
        '\t/* We only trust the superuser with rebooting the system. */')

# init reads init.rc using fstat plus read; reflect the appended rc size.
for name, fdtype, stattype, copyfn, handler in [
    ('newfstat', 'unsigned int', 'stat', 'cp_new_stat', 'ksu_handle_newfstat_ret'),
    ('fstat64', 'unsigned long', 'stat64', 'cp_new_stat64', 'ksu_handle_fstat64_ret'),
]:
    old = (f'SYSCALL_DEFINE2({name}, {fdtype}, fd, struct {stattype} __user *, statbuf)\n'
           '{\n\tstruct kstat stat;\n\tint error = vfs_fstat(fd, &stat);\n\n'
           f'\tif (!error)\n\t\terror = {copyfn}(&stat, statbuf);\n\n\treturn error;\n}}')
    new = (f'#ifdef CONFIG_KSU\nextern void {handler}({fdtype} *fd, struct {stattype} __user **statbuf);\n#endif\n'
           + old.replace('\n\treturn error;', '\n#ifdef CONFIG_KSU\n'
                         f'\tif (!error)\n\t\t{handler}(&fd, &statbuf);\n#endif\n\treturn error;'))
    replace('fs/stat.c', old, new)

# The manual exec call passes a struct user_arg_ptr, not a kernel argv array.
# Avoid interpreting user pointers as kernel strings in the optional su log.
sucompat_path = 'drivers/staging/kernelsu/kernel/feature/sucompat.c'
sucompat_text = (root / sucompat_path).read_text()
if 'sucompat_argv' in sucompat_text:
    replace(sucompat_path,
            'const char *const *sucompat_argv = (const char *const *)__never_use_argv;',
            'const char *const *sucompat_argv = NULL; /* manual hook: user_arg_ptr is not kernel argv */')
else:
    assert 'void *__never_use_argv' in sucompat_text
print('Applied checked Rikka manual-hook integration and truthful IKCONFIG fix')
