#!/bin/bash
# pi-gen stage prerun: invoked before the substages run.
# Standard pi-gen pattern — copy rootfs from previous stage.
set -e
if [ ! -d "${ROOTFS_DIR}" ]; then
    copy_previous
fi
