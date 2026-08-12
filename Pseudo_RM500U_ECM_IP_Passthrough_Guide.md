# 5G Smart Shell (Pseudo-RM500U Custom Firmware) ECM Mode IP Passthrough Setup & Fix Guide

> **Important Disclaimer**: This technical guide pertains to generic **5G Smart Shell / CPE modules (Unisoc V510 platform)** running third-party custom firmware that emulates the Quectel RM500U AT command set. The firmware behaviors and fixes documented herein apply specifically to this custom pseudo-RM500U firmware and **do not represent official factory Quectel RM500U hardware or official Quectel firmware releases**.

---

## 1. Overview

This document provides a technical guide for setting up **IP Passthrough (Bridge) Mode** on 5G Smart Shell modules featuring custom RM500U emulation firmware (Unisoc V510 platform) and resolving common packet drop issues.

* **Hardware Platform**: Unisoc V510 5G Platform / 5G Smart Shell Module
* **Firmware Type**: Custom Third-Party Firmware (Pseudo-RM500U AT Emulation)
* **Target Operation Mode**: **ECM Mode + IP Passthrough / Bridge** (`AT+QCFG="usbnet",1` + `AT+QCFG="nat",0`)
* **Host Compatibility**: Linux / OpenWrt / Router / Windows Hosts connected via USB (`usb0` / ECM Network Adapter)

---

## 2. Technical Analysis: USB Protocol Modes under IP Passthrough (`nat,0`)

Through kernel log inspection (`dmesg` & SIPA driver state), different USB network protocols exhibit distinct behaviors under `AT+QCFG="nat",0`:

| USB Protocol Mode | AT Command | Passthrough Status (`nat,0`) | Kernel Dmesg Error & Cause |
| :--- | :--- | :--- | :--- |
| **RNDIS Mode** | `AT+QCFG="usbnet",0` | ❌ **100% Packet Loss** | `sipa_usb: sipa 0 channel not opened yet`<br>SIPA hardware accelerator channel 0 locks up and drops all ingress/egress packets. |
| **NCM Mode** | `AT+QCFG="usbnet",2` | ❌ **100% Packet Loss** | `SFP: get orig_src_mac fail`<br>SIPA hardware accelerator fails to resolve NCM Ethernet header MAC address and deletes forwarding entries. |
| **ECM Mode (Recommended)** | `AT+QCFG="usbnet",1` | ✅ **0% Loss / Full Speed** | `sipa: receiver 1 & 2 wake up thread`<br>SIPA hardware accelerator initializes properly, DMA FIFO channels open cleanly, and the modem DHCP server passes the WAN IP directly to the host client. |

> **Firmware Author Recommendation**: Vendor documentation for this pseudo-RM500U firmware specifically specifies `AT+QCFG="usbnet",1` (ECM) + `AT+QCFG="nat",0` (No NAT) as the primary tested passthrough configuration.

---

## 3. Step-by-Step Configuration Guide

### Step 1: AT Command Configuration

Connect to the module's serial AT port (`/dev/ttyUSB2` or Windows COM port) and issue the following commands:

```text
AT+QCFG="usbnet",1       ; Set USB protocol mode to CDC-ECM
AT+QCFG="nat",0          ; Set NAT mode to 0 (IP Passthrough / Bridge)
AT+QCFG="usbcfg",0x2c7c,0x0900,0,0,1,1,0,1  ; Keep ADB diagnostic port enabled
AT+CFUN=1,1              ; Reboot module to apply settings
```

---

### Step 2: Persistent NV Configuration Fix (`/mnt/data/quec_lan.ini`)

Connect to the module via ADB (`adb shell`) and ensure `/mnt/data/quec_lan.ini` has ARP learning enabled (`[host_mac] arp = 1`):

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

[boot_hook]
cmd = /mnt/data/start_dhcp.sh
```

---

### Step 3: Deployment of Dual-Mode Boot Script (`/mnt/data/start_dhcp.sh`)

Create `/mnt/data/start_dhcp.sh` inside the module's `/mnt/data/` partition to dynamically support both NAT (`nat,1`) and IP Passthrough (`nat,0`) modes:

```sh
#!/bin/sh
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
    echo "[start_dhcp] Passthrough Mode (nic/nat,0) detected! Yielding to ECM Passthrough..."
    killall -9 udhcpd 2>/dev/null
    iptables -t nat -F 2>/dev/null
fi
```

Set executable permissions:
```sh
chmod +x /mnt/data/start_dhcp.sh
```

---

### Step 4: Host Device Interface Configuration

On the host router / Linux system, configure the USB network interface (`usb0` / ECM adapter) as a standard DHCP client:

#### Linux / OpenWrt (`/etc/config/network`)
```ini
config interface 'wan'
	option device 'usb0'
	option proto 'dhcp'
```

#### Generic Linux Systemd Network / Ifupdown
```sh
ifconfig usb0 up
udhcpc -i usb0
# or dhclient usb0
```

---

## 4. Verification Checklist

1. **DHCP IP Assignment**:
   * The host `usb0` interface receives the Carrier Public / CGNAT WAN IP, Gateway, and DNS directly from the module via DHCP.
2. **Ping & Latency Test**:
   * Gateway Ping: **0% Packet Loss, < 1ms** response time.
   * Remote Ping (`223.5.5.5`): **0% Packet Loss, ~25-30ms** 5G latency.
3. **Reboot Resilience**:
   * Issuing `AT+CFUN=1,1` reboots the module cleanly, after which the host automatically re-acquires the WAN IP and restores connectivity without manual intervention.
