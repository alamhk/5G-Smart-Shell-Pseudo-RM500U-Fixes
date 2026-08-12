# 5G Smart Shell (Pseudo-RM500U Custom Firmware) RNDIS NAT Mode DHCP Bug Fix Report

> **Important Disclaimer**: This technical report pertains to generic **5G Smart Shell / CPE modules (Unisoc V510 platform)** running third-party custom firmware that emulates the Quectel RM500U AT command set. The firmware bugs and behaviors documented herein are specific to this custom pseudo-RM500U firmware build and **do not reflect official factory Quectel RM500U hardware or official Quectel firmware releases**.

---

## 1. Overview & System Specifications

- **Hardware Platform**: Unisoc V510 5G Platform / 5G Smart Shell Module
- **Firmware Type**: Custom Third-Party Firmware (Pseudo-RM500U AT Emulation)
- **Firmware Build**: `RM500UCNAAR03A11M2G_01.001.01.001` (Yocto Linux 4.14.98 aarch64)
- **Target Network Mode**: RNDIS + NAT Mode (`AT+QCFG="nat",1`)
- **Target Subnet**: `192.168.106.0/24` (Gateway: `192.168.106.1`, Client Range: `192.168.106.100` - `192.168.106.200`)
- **Host Devices**: Linux / Windows / Router Hosts connected via USB (`usb0` / RNDIS Adapter)

---

## 2. Problem Statement & Symptoms

When the custom pseudo-RM500U module was configured to NAT mode (`AT+QCFG="nat",1`), host devices connected via USB (`usb0` / RNDIS) failed to acquire an IP address via DHCP:
- Raw packet captures showed host `DHCP DISCOVER` packets exiting `usb0` (`0.0.0.0:68 > 255.255.255.255:67`), but **no `DHCP OFFER` or `DHCP ACK` returned** from the module.
- Host interfaces remained stuck at APIPA (`169.254.x.x`) or failed connectivity.

---

## 3. Root Cause Analysis (Discovered via ADB Root Inspection)

Connecting directly to the module's internal OS via ADB (`adb shell`, `uid=0(root)`) revealed **three critical firmware bugs** inside this custom Linux network stack:

### Bug #1: Invalid Gateway Configuration in NV Flash (`quec_lan.ini`)
In `/mnt/data/quec_lan.ini`, the gateway parameter was incorrectly set to `.0` (subnet network address):
```ini
[lanip]
gateway = 192.168.106.0  # BUG: Network address instead of host IP 192.168.106.1
```
Because the gateway IP was `.0`, Intel ConnMan (`connmand`) failed to bind its internal DHCP server listener properly.

### Bug #2: SIPA Hardware Accelerator Channel Lockup & Host ARP Disable
In `/mnt/data/quec_lan.ini`, host ARP binding was disabled:
```ini
[host_mac]
arp = 0  # BUG: Prevents SIPA hardware accelerator from binding host MAC
```
This caused the Unisoc V510 SIPA (Smart IP Accelerator) driver to continuously log errors in kernel `dmesg`:
```text
sipa_usb: sipa 0 channel not opened yet
```
Every incoming frame on `usb0` failed packet classification and was counted as an **RX error** (over 900+ accumulated RX errors on `usb0`).

### Bug #3: Duplicate Subnet Routing Table Conflict
Inside the module's Linux kernel, both `sipa_usb0` and `usb0` were assigned the exact same subnet route:
```text
192.168.106.0/24 dev sipa_usb0 scope link src 192.168.106.1
192.168.106.0/24 dev usb0 scope link src 192.168.106.1
```
When reply packets were generated for the client (`192.168.106.100`), the kernel routed egress packets out of `sipa_usb0` (the first route) instead of `usb0` (where the host was attached), resulting in **100% packet loss for ICMP ping and DHCP ACK responses**.

---

## 4. Technical Fix & Modifications Implemented

### Step 1: NV Flash Configuration Update (`/mnt/data/quec_lan.ini`)
Updated `/mnt/data/quec_lan.ini` inside the module's persistent storage:
```ini
[ethernet]
enable                         = 1

[usbnet]
enable                         = 1
multiusbnet                    = 1
cidoffset                      = 0

[lanip]
gateway                        = 192.168.106.1
netmask                        = 255.255.255.0

[host_mac]
arp                            = 1

[proxyarp]
enable                         = 0
```

### Step 2: Deployment of Custom Startup Fix Script (`/mnt/data/start_dhcp.sh`)
Created a dedicated initialization script `/mnt/data/start_dhcp.sh` inside the module:
```sh
#!/bin/sh
# 1. Disable faulty SIPA hardware acceleration bypass
echo 0 > /proc/net/sfp/enable 2>/dev/null

# 2. Assign gateway IP directly to usb0 interface
ifconfig usb0 192.168.106.1 netmask 255.255.255.0 up

# 3. Remove conflicting duplicate route on sipa_usb0
ip route del 192.168.106.0/24 dev sipa_usb0 2>/dev/null

# 4. Enable IPv4 forwarding & iptables NAT Masquerade
echo 1 > /proc/sys/net/ipv4/ip_forward
iptables -I INPUT -i usb0 -j ACCEPT
iptables -I FORWARD -j ACCEPT
iptables -t nat -A POSTROUTING -j MASQUERADE

# 5. Launch udhcpd bound directly to usb0
killall -9 udhcpd 2>/dev/null
/usr/sbin/udhcpd /mnt/data/udhcpd_usb0.conf
```

DHCP Configuration (`/mnt/data/udhcpd_usb0.conf`):
```ini
start 192.168.106.100
end 192.168.106.200
interface usb0
opt dns 192.168.106.1 223.5.5.5
option subnet 255.255.255.0
opt router 192.168.106.1
opt lease 86400
```

### Step 3: Permanent Boot Hook Integration (`/etc/init.d/quec_lan.sh`)
Remounted the read-only root filesystem (`mount -o remount,rw /`) and updated `/etc/init.d/quec_lan.sh` to trigger `/mnt/data/start_dhcp.sh &` upon module bootup, then remounted back to read-only (`mount -o remount,ro /`).

---

## 5. Verification & Test Results

### 1. Cold Reset Test via AT Command (`AT+CFUN=1,1`)
Issued `AT+CFUN=1,1` to serial port. The module performed a full cold reboot and re-enumerated on USB.

### 2. DHCP Leasing Verification
Upon bootup, the attached host system automatically received a DHCP lease:
- **IPv4 Address**: `192.168.106.100` (Preferred)
- **Subnet Mask**: `255.255.255.0`
- **Default Gateway**: `192.168.106.1`
- **DHCP Server**: `192.168.106.1`
- **DNS Server**: `192.168.106.1`, `223.5.5.5`

### 3. ICMP Ping Test (`ping 192.168.106.1`)
```text
Pinging 192.168.106.1 with 32 bytes of data:
Reply from 192.168.106.1: bytes=32 time<1ms TTL=64
Reply from 192.168.106.1: bytes=32 time<1ms TTL=64
Reply from 192.168.106.1: bytes=32 time<1ms TTL=64
Reply from 192.168.106.1: bytes=32 time<1ms TTL=64

Ping statistics for 192.168.106.1:
    Packets: Sent = 4, Received = 4, Lost = 0 (0% loss),
Approximate round trip times in milli-seconds:
    Minimum = 0ms, Maximum = 0ms, Average = 0ms
```

---

## 6. Summary & Conclusion

The RNDIS `nat,1` mode DHCP failure was caused by custom firmware bugs inside this pseudo-RM500U Yocto Linux system (`gateway=.0`, SIPA `arp=0`, and duplicate route conflict). 

By fixing the internal configuration, bypassing faulty hardware SIPA channel locks, and deploying a persistent startup hook in `/mnt/data/` and `/etc/init.d/quec_lan.sh`, the 5G Smart Shell module now **persistently assigns DHCP IP leases and provides full 0% loss bidirectional IP connectivity across cold reboots**.
