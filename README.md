# 5G Smart Shell (Pseudo-RM500U Custom Firmware) Fixes & Passthrough Guide

> **Project Notice**: This repository provides technical guides, kernel bug reports, and persistent fix scripts for **5G Smart Shell / CPE modules (Unisoc V510 platform)** running third-party custom firmware that emulates the Quectel RM500U AT command set.

---

## 📌 Project & Firmware Acknowledgments

* **Firmware Author**: **rA9**
* **Official Community QQ Channel**: [https://pd.qq.com/s/6a7enqayi?b=2](https://pd.qq.com/s/6a7enqayi?b=2)
* **Hardware Platform**: Unisoc V510 5G Platform / 5G Smart Shell CPE Module
* **Tested Firmware Build**: `RM500UCNAAR03A11M2G_01.001.01.001` (Yocto Linux 4.14.98 aarch64)

> **Important Disclaimer**: The firmware behaviors, kernel driver fixes, and scripts documented herein apply specifically to third-party custom pseudo-RM500U firmware builds and **do not represent official factory Quectel RM500U hardware or official Quectel firmware releases**.

---

## 📚 Documentation Index

This repository contains four comprehensive technical documents:

| Document | Topic & Description |
| :--- | :--- |
| 📄 **[Pseudo_RM500U_ECM_IP_Passthrough_Guide.md](Pseudo_RM500U_ECM_IP_Passthrough_Guide.md)** | Step-by-step setup guide for **ECM IP Passthrough / Bridge Mode** (`nat,0`), including persistent NV config fixes and host router integration. |
| 📄 **[Pseudo_RM500U_Firmware_Bugs_Report_For_Author.md](Pseudo_RM500U_Firmware_Bugs_Report_For_Author.md)** | Technical feedback report for firmware author **rA9** detailing the 3 modem-side bugs (SIPA auto-suspend, `/32` netmask, and passthrough DHCP server absence). |
| 📄 **[Pseudo_RM500U_RNDIS_DHCP_Bugfix_Report.md](Pseudo_RM500U_RNDIS_DHCP_Bugfix_Report.md)** | Technical report detailing root causes and persistent fix scripts for RNDIS NAT Mode (`nat,1`) DHCP leasing failures. |
| 📄 **[Pseudo_RM500U_SIPA_Freeze_Fix_Report.md](Pseudo_RM500U_SIPA_Freeze_Fix_Report.md)** | Analysis and solution for the Unisoc SIPA DMA Hardware Accelerator auto-suspend freeze bug (`power/control = auto`). |

---

## 🛠️ Quick Summary of Modem Partition Fix (`/mnt/data/start_dhcp.sh`)

To resolve idle freezes, netmask binding errors, and DHCP leasing failures in Passthrough mode (`nat,0`), update `/mnt/data/start_dhcp.sh` inside the module:

```sh
#!/bin/sh
# Persistent initialization script for Unisoc V510 5G Smart Shell Custom Firmware

# Fix #1: Lock SIPA PM control to 'on' (Prevent DMA Channel 0 Auto-Suspend)
echo on > /sys/devices/platform/soc/2e000000.sprd,sipa/power/control 2>/dev/null
echo on > /sys/devices/platform/sipa-usb0/power/control 2>/dev/null
echo 1 > /proc/net/sfp/enable 2>/dev/null

# Fix #2 & #3: Fix usb0 /24 netmask & launch dynamic passthrough udhcpd
USB0_IP=$(ifconfig usb0 2>/dev/null | grep 'inet addr:' | cut -d: -f2 | awk '{print $1}')

if [ -n "$USB0_IP" ]; then
    ifconfig usb0 $USB0_IP netmask 255.255.255.0 up 2>/dev/null
    SUBNET_PREFIX=$(echo $USB0_IP | cut -d. -f1-3)
    
    cat << EOF > /tmp/udhcpd_passthrough.conf
start ${SUBNET_PREFIX}.100
end ${SUBNET_PREFIX}.200
interface usb0
opt dns ${USB0_IP} 223.5.5.5
option subnet 255.255.255.0
opt router ${SUBNET_PREFIX}.1
opt lease 86400
EOF

    killall -9 udhcpd 2>/dev/null
    /usr/sbin/udhcpd /tmp/udhcpd_passthrough.conf 2>/dev/null
fi
```
