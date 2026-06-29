#!/bin/bash -e
# Pin the Raspberry Pi kernel to the 6.12 LTS series.
#
# WHY: Raspberry Pi OS Trixie's default kernel moved to the 6.18.x series,
# which regressed the lan78xx driver (EEE / TX-LPI behaviour changed when
# lan78xx was converted to phylink in 6.17). On the Pi 3B+ this kills wired
# ethernet — the link flaps and never carries traffic:
#   lan78xx ... eth0: kevent 0 may have been dropped
#   lan78xx ... eth0: Link is Down
# See raspberrypi/linux#7436 (OPEN). The last-known-good kernel from that
# thread is 6.12.75, and the whole 6.12 LTS line is still in the Trixie
# archive. We hold the image there until #7436 is fixed upstream.
#
# The base pi-gen stages already installed the 6.18.x kernel + metapackages,
# so this script installs the 6.12 LTS kernels, removes the 6.18.x ones (so
# raspi-firmware regenerates /boot/firmware/kernel8.img from 6.12), holds the
# 6.12 packages, and pins the 6.18 line / metapackages to never reinstall.
#
# ⚠️  UNVERIFIED ON HARDWARE in this commit — must boot on a real Pi 3B and
#     Pi 3B+ (wired) before merge. The pre-publish CI gate in
#     build-fiestapi.yml asserts the pin took (no 6.18 kernel, 6.12 present,
#     Pi-3 boot files exist) but cannot prove the board actually networks.

# Last-known-good LTS kernel per raspberrypi/linux#7436. Bump within the 6.12
# line only; do NOT advance to 6.18.x until that issue is resolved.
KVER="6.12.75+rpt"

on_chroot <<EOF
set -eu

# 1. Block the 6.18.x kernel line and the metapackages that drag it back in.
cat > /etc/apt/preferences.d/fiestapi-pin-kernel <<'PIN'
# FiestaPi: hold the kernel at the 6.12 LTS line. The 6.18.x series breaks
# Pi 3B+ wired ethernet (raspberrypi/linux#7436). Priority -1 = never install.
# Remove this file + unhold the 6.12 packages once #7436 is fixed upstream.
Package: linux-image-6.18.* linux-headers-6.18.* linux-image-rpi-v8 linux-image-rpi-2712 linux-headers-rpi-v8 linux-headers-rpi-2712
Pin: release *
Pin-Priority: -1
PIN

apt-get update -qq

# 2. Install the explicit 6.12 LTS kernels (both flavours: v8 = Pi 2/3/Zero2,
#    2712 = Pi 4/5) so every supported board boots a known-good kernel.
apt-get install -y --no-install-recommends \
    "linux-image-${KVER}-rpi-v8" \
    "linux-image-${KVER}-rpi-2712"

# 3. Remove the 6.18.x kernels and the metapackages depending on them, so
#    raspi-firmware picks the 6.12 kernel as the highest installed version
#    for each flavour when it regenerates the boot partition.
apt-get purge -y 'linux-image-6.18.*' linux-image-rpi-v8 linux-image-rpi-2712 || true
apt-get autoremove -y --purge || true

# 4. Force raspi-firmware to regenerate /boot/firmware/kernel*.img + initramfs
#    from the now-only 6.12 kernel.
apt-get install --reinstall -y raspi-firmware

# 5. Hold the 6.12 kernels so a stray apt upgrade can't move them.
apt-mark hold "linux-image-${KVER}-rpi-v8" "linux-image-${KVER}-rpi-2712"

# 6. Fail the build loudly if the pin didn't take — better a failed image
#    build than a silently-shipped broken-ethernet image.
if dpkg-query -W -f='\${Package}\n' 'linux-image-6.18*' 2>/dev/null | grep -q .; then
    echo "pin-kernel: ERROR — a 6.18.x kernel is still installed after pinning" >&2
    exit 1
fi
if ! dpkg-query -W -f='\${Package}\n' "linux-image-${KVER}-rpi-v8" 2>/dev/null | grep -q .; then
    echo "pin-kernel: ERROR — 6.12 v8 kernel not installed" >&2
    exit 1
fi
test -f /boot/firmware/kernel8.img \
    || { echo "pin-kernel: ERROR — /boot/firmware/kernel8.img missing (Pi 3 won't boot)" >&2; exit 1; }

echo "pin-kernel: kernel held at ${KVER} (v8 + 2712); 6.18.x removed."
EOF
