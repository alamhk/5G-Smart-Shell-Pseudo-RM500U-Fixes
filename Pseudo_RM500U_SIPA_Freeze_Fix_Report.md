# 5G Smart Shell (Pseudo-RM500U Custom Firmware) SIPA Hardware Accelerator Auto-Suspend Freeze Bug & Solution

> **Important Disclaimer**: This technical report pertains to generic **5G Smart Shell / CPE modules (Unisoc V510 platform)** running third-party custom firmware that emulates the Quectel RM500U AT command set. The firmware bugs and behaviors documented herein are specific to this custom pseudo-RM500U firmware build and **do not reflect official factory Quectel RM500U hardware or official Quectel firmware releases**.

---

## 1. Issue Overview

On 5G Smart Shell modules using the Unisoc V510 platform running custom pseudo-RM500U emulation firmware, the module network connection may randomly freeze or experience total packet loss after 3 to 12 seconds of network idle time. 

When network traffic pauses (e.g., while reading a web page or idle in a chat application) and resumes, initial packets are dropped or severely delayed, requiring a network interface restart or AT command re-initiation.

---

## 2. Kernel Log Analysis (`dmesg` Diagnosis)

Deep inspection of the module's internal Yocto Linux kernel logs (`dmesg`) revealed the exact sequence of events during a freeze:

```text
[10184.232674] c0 sipa_rm: sipa_rm_resource_producer_release SIPA_RM_RES_PROD_IPA state changed 2->0
[10184.232701] c0 sipa_rm: sipa_rm_resource_consumer_release SIPA_RM_RES_CONS_WWAN_DL state changed 2->0
[10184.232726] c0 sipa 2e000000.sprd,sipa: sipa set enable_cnt = 1 enable = 0
[10184.232776] c0 sipa recv fifo 23 need_fill_cnt = 6
[10184.232801] c0 sipa 2e000000.sprd,sipa: thread prepare suspend err
[10184.232814] c0 sipa 2e000000.sprd,sipa: sipa schedule_delayed_work
[10184.441185] c0 sipa 2e000000.sprd,sipa: sipa set enable_cnt = 0 enable = 0
[10184.441196] c0 sipa 2e000000.sprd,sipa: sipa prepare suspend finish
```

### Analysis of the Log Sequence:
1. **Idle Detection**: When packet traffic pauses for more than 3 seconds, the Unisoc SIPA Resource Manager (`sipa_rm`) triggers a resource release (`sipa_rm_resource_consumer_release`).
2. **Auto-Suspend Trigger**: The kernel SIPA driver executes `sipa set enable_cnt = 0 enable = 0` and completes power suspend (`sipa prepare suspend finish`).
3. **DMA Freeze**: Once SIPA hardware acceleration enters the suspended state (`enable = 0`), DMA FIFO channels between the 5G WWAN baseband driver (`sipa_eth0`) and the USB network interface (`usb0`) are powered down.
4. **Wakeup Failure / Stutter**: When new network packets arrive, SIPA attempts to wake up (`enable = 1`). However, hardware clock re-initialization stutters (`thread prepare suspend err`), leading to packet loss and system hangs.

---

## 3. Root Cause

The Linux Runtime Power Management (`sysfs power/control`) for the SIPA hardware block is configured to **`auto`** by default in this firmware build:

* Path: `/sys/devices/platform/soc/2e000000.sprd,sipa/power/control`
* Value: `auto`

When set to `auto`, the Linux kernel aggressively puts the SIPA hardware block into low-power suspend whenever DMA traffic pauses. In ECM / Passthrough modes, this power-saving state causes DMA FIFO desynchronization and connection freezes.

---

## 4. Permanent Solution & Fix

To resolve this issue, Linux Runtime PM for the SIPA hardware block must be forced to **`on`** (always powered and active).

### Step 1: Force Power-On via sysfs
Run the following commands inside the module (via ADB or internal script):

```sh
echo on > /sys/devices/platform/soc/2e000000.sprd,sipa/power/control
echo on > /sys/devices/platform/sipa-usb0/power/control
```

### Step 2: Make the Fix Persistent Across Reboots
Add the sysfs power control commands to the module's startup script (`/mnt/data/start_dhcp.sh`):

```sh
#!/bin/sh
# Force SIPA hardware accelerator to remain active 24/7 (Disable Auto-Suspend)
echo on > /sys/devices/platform/soc/2e000000.sprd,sipa/power/control 2>/dev/null
echo on > /sys/devices/platform/sipa-usb0/power/control 2>/dev/null

WAN_CFG_FILE=/mnt/data/quec_nic.ini
NAT_TYPE=$(rwini.sh $WAN_CFG_FILE nic nat_type 2>/dev/null)

if [ "$NAT_TYPE" = "router" ]; then
    echo "[start_dhcp] NAT Mode (router) detected, applying NAT fixes..."
    echo 0 > /proc/net/sfp/enable 2>/dev/null
    ifconfig usb0 192.168.106.1 netmask 255.255.255.0 up
    ip route del 192.168.106.0/24 dev sipa_usb0 2>/dev/null
    echo 1 > /proc/sys/net/ipv4/ip_forward
    iptables -I INPUT -i usb0 -j ACCEPT
    iptables -I FORWARD -j ACCEPT
    iptables -t nat -A POSTROUTING -j MASQUERADE
    killall -9 udhcpd 2>/dev/null
    /usr/sbin/udhcpd /mnt/data/udhcpd_usb0.conf
else
    echo "[start_dhcp] Passthrough Mode (nic/nat,0) detected! Stopping udhcpd..."
    killall -9 udhcpd 2>/dev/null
    iptables -t nat -F 2>/dev/null
fi
```

Make sure the script is executable:
```sh
chmod +x /mnt/data/start_dhcp.sh
```

---

## 5. Verification Results

After applying the fix, inspect `dmesg` in the module kernel:

```text
[ 27.361256] sipa set enable_cnt = 1 enable = 1
[ 27.361389] sipa: receiver 1 wake up thread
[ 27.361412] sipa: receiver 2 wake up thread
[ 27.361814] sipa set enable_cnt = 2 enable = 1
[ 27.361976] sipa_eth: SIPA LEAVE FLOWCTRL
```

### Key Verification Metrics:
1. **SIPA State**: `enable_cnt = 2 enable = 1` remains continuously active regardless of traffic idle duration.
2. **Auto-Suspend Log**: Zero instances of `sipa prepare suspend finish` or `thread prepare suspend err` in `dmesg`.
3. **Latency & Stability**: Continuous ICMP ping tests maintain **0% packet loss** with **11–17ms 5G latency** across extended idle and active periods.
