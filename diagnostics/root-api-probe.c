// SPDX-License-Identifier: GPL-2.0
/* Read-only ABI probes. The nonstandard reboot magic values cannot reboot.
 * Compile with the unmodified Next v3.4.2 userspace UAPI headers.
 */
#define _GNU_SOURCE
#include <errno.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/syscall.h>
#include <unistd.h>
#include "uapi/supercall.h"

struct susfs_version_query {
    char version[16];
    int err;
};
_Static_assert(sizeof(struct ksu_get_info_cmd) == 16, "Next UAPI layout");
_Static_assert(sizeof(struct susfs_version_query) == 20, "SUSFS v2.2 layout");

int main(int argc, char **argv)
{
    int fd = -1, saved_errno;
    struct ksu_get_info_cmd info = {0};
    struct susfs_version_query susfs = {.err = -1};
    int require_susfs = argc == 2 && !strcmp(argv[1], "--require-susfs");
    if (argc == 2 && !strcmp(argv[1], "--selftest")) {
        printf("{\"compiled_uapi\":%u,\"get_info_size\":%zu,\"device_test\":false}\n",
               KERNEL_SU_UAPI_VERSION, sizeof(info));
        return KERNEL_SU_UAPI_VERSION == 5 ? 0 : 1;
    }
    if (getuid() != 0) {
        puts("{\"error\":\"run this read-only probe through su\",\"uid_is_root\":false}");
        return 2;
    }
    /* A normal reboot() error is expected; the hook replies through fd. */
    syscall(SYS_reboot, KSU_INSTALL_MAGIC1, KSU_INSTALL_MAGIC2, 0, &fd);
    saved_errno = errno;
    if (fd < 0) {
        printf("{\"error\":\"Next driver fd was not returned\",\"errno\":%d}\n", saved_errno);
        return 3;
    }
    if (ioctl(fd, KSU_IOCTL_GET_INFO, &info)) {
        printf("{\"error\":\"GET_INFO failed\",\"errno\":%d}\n", errno);
        close(fd);
        return 4;
    }
    close(fd);
    syscall(SYS_reboot, 0xDEADBEEF, 0xFAFAFAFA, 0x555e1, &susfs);
    susfs.version[sizeof(susfs.version) - 1] = 0;
    /* Emit only the known version string, never arbitrary data as JSON. */
    int present = susfs.err == 0 && !strcmp(susfs.version, "v2.2.0");
    printf("{\"uid_is_root\":true,\"ksu_version\":%u,\"uapi_version\":%u,"
           "\"expected_uapi\":5,\"susfs_2_2_0_present\":%s,\"susfs_status\":%d}\n",
           info.version, info.uapi_version, present ? "true" : "false", susfs.err);
    if (info.uapi_version != 5)
        return 5;
    return require_susfs && !present ? 6 : 0;
}
