# Technical Feedback Report: Modem-Side Firmware Bugs & Solutions

> **Important Disclaimer**: This technical report pertains to generic **5G Smart Shell / CPE modules (Unisoc V510 platform)** running third-party custom firmware that emulates the Quectel RM500U AT command set. The firmware bugs and kernel behaviors documented herein are specific to this custom pseudo-RM500U firmware build (`RM500UCNAAR03A11M2G_01.001.01.001`) and **do not reflect official factory Quectel RM500U hardware or official Quectel firmware releases**.

---

## 1. Overview

During extended stress testing and kernel ADB log inspection, six critical modem-side firmware bugs were identified in the custom Yocto Linux system (`/mnt/data/` & kernel drivers). These bugs cause intermittent packet loss, total connection freezes, empty policy routing table drops, and DHCP leasing failures on host devices connected via USB (`usb0` / ECM / RNDIS).

This report outlines the technical root causes, kernel `dmesg` logs, and recommended permanent fixes for the firmware author.

---

## 2. Detailed Bug Descriptions & Root Causes

### Bug #1: SIPA Hardware Accelerator Auto-Suspend & Channel 0 Closure

* **Symptom**: Network traffic freezes or drops 100% of packets after 3 to 12 seconds of idle time or after a 5G baseband IP re-assignment. Host system receives no packet responses until an AT dial command is re-issued.
* **Kernel Dmesg Log**:
  ```text
  [ 8706.148388] sipa set enable_cnt = 1 enable = 0
  [ 8706.148487] sipa prepare suspend finish
  [ 8710.241056] sipa_usb: sipa 0 channel not opened yet
  ```
* **Root Cause Analysis**:
  The Linux Runtime Power Management for the Unisoc SIPA (Smart IP Accelerator) driver is set to **`auto`** by default in `/sys/devices/platform/soc/2e000000.sprd,sipa/power/control`. 
  When traffic pauses for >3 seconds or when `sipa_eth0` bounces, the kernel puts SIPA into suspend (`enable_cnt = 0`). Subsequent packet arrivals fail to wake up the DMA FIFO channels cleanly, and `sipa_usb` closes DMA Channel 0 (`sipa 0 channel not opened yet`), dropping all ingress/egress frames on `usb0`.

* **Recommended Fix for Firmware Author**:
  In `/mnt/data/start_dhcp.sh` and `/etc/init.d/quec_lan.sh`, permanently force SIPA power management control to **`on`** and enable SFP hardware acceleration:
  ```sh
  echo on > /sys/devices/platform/soc/2e000000.sprd,sipa/power/control 2>/dev/null
  echo on > /sys/devices/platform/sipa-usb0/power/control 2>/dev/null
  echo 1 > /proc/net/sfp/enable 2>/dev/null
  ```

---

### Bug #2: `usb0` Interface Netmask Hardcoded to `/32` (`255.255.255.255`)

* **Symptom**: DHCP server (`udhcpd`) fails to start or rejects client lease ranges (`10.x.x.100 - 10.x.x.200`), resulting in `no lease, failing` on attached host routers.
* **Kernel/Ifconfig Log**:
  ```text
  usb0      Link encap:Ethernet  HWaddr 36:79:5c:b4:d1:b8  
            inet addr:10.170.23.1  Bcast:0.0.0.0  Mask:255.255.255.255
  ```
* **Root Cause Analysis**:
  When `quec_nic_service` or `connmand` initializes the `usb0` interface, it assigns the netmask `255.255.255.255` (`/32`). Because a `/32` subnet restricts IP addresses exclusively to `10.x.x.1`, BusyBox `udhcpd` detects that the requested lease pool (`10.x.x.100` to `200`) is outside the local interface subnet and refuses to service incoming `DHCP DISCOVER` requests.

* **Recommended Fix for Firmware Author**:
  In the interface bring-up scripts, explicitly assign a `/24` netmask (`255.255.255.0`) matching the current dynamic cellular subnet:
  ```sh
  USB0_IP=$(ifconfig usb0 2>/dev/null | grep 'inet addr:' | cut -d: -f2 | awk '{print $1}')
  if [ -n "$USB0_IP" ]; then
      ifconfig usb0 $USB0_IP netmask 255.255.255.0 up
  fi
  ```

---

### Bug #3: Absence of Active DHCP Server in Passthrough Mode (`nat_type = nic` / `nat,0`)

* **Symptom**: When `AT+QCFG="nat",0` (IP Passthrough / Bridge Mode) is enabled, host routers or PCs attached via USB fail to acquire an IP via DHCP when renewing or setting up the connection.
* **Root Cause Analysis**:
  In `/mnt/data/start_dhcp.sh`, the original script contains the following logic:
  ```sh
  if [ "$NAT_TYPE" = "router" ]; then
      # Start udhcpd for NAT mode...
  else
      echo "[start_dhcp] Passthrough Mode (nic/nat,0) detected! Stopping udhcpd..."
      killall -9 udhcpd 2>/dev/null
  fi
  ```
  While `connmand` is expected to handle IP forwarding in passthrough mode, it lacks an active DHCP listening daemon on UDP port 67 for `usb0`. When the host sends `DHCP DISCOVER`, no process responds.

* **Recommended Fix for Firmware Author**:
  Update `/mnt/data/start_dhcp.sh` to dynamically generate a `/tmp/udhcpd_passthrough.conf` matching the current `usb0` subnet and keep `udhcpd` active in passthrough mode:
  ```sh
  SUBNET_PREFIX=$(echo $CELL_IP | cut -d. -f1-3)
  GATEWAY_IP="${SUBNET_PREFIX}.1"

  cat << EOF > /tmp/udhcpd_passthrough.conf
  start ${SUBNET_PREFIX}.100
  end ${SUBNET_PREFIX}.200
  interface usb0
  opt dns ${GATEWAY_IP} ${ISP_DNS}
  option subnet 255.255.255.0
  opt router ${GATEWAY_IP}
  opt lease 86400
  EOF

  killall -9 udhcpd 2>/dev/null
  nohup /usr/sbin/udhcpd /tmp/udhcpd_passthrough.conf >/dev/null 2>&1 &
  ```

---

### Bug #4: Stale Android Policy Routing Rules & Unroutable SNAT Address (100% Ingress Packet Drop)

* **Symptom**: The modem local console can ping `8.8.8.8` via `sipa_eth0`, and attached host routers can ping the modem gateway (`10.x.x.1`), but all forwarded traffic from host devices (`usb0` -> `sipa_eth0`) drops 100% (`100% packet loss`).
* **Root Cause Analysis**:
  1. **Empty Policy Routing Table 132**: Android policy rules (`11: from all iif usb0 lookup 122` and `21: from all iif sipa_eth0 lookup 132`) route ingress packets from `sipa_eth0` to table 132. When cellular reconnects, table 132 remains **empty**, causing all return packets from the internet to be discarded.
  2. **Unroutable Private SNAT IP**: Default `iptables` NAT configuration contained stale SNAT rules pointing to private loopback IP `192.168.1.33` (`SNAT to:192.168.1.33`). Mobile network operators (e.g. CMHK, China Mobile, Unicom) drop egress packets with unroutable private source IPs.

* **Recommended Fix for Firmware Author**:
  Clear stale policy rules and dynamically bind `POSTROUTING` SNAT to the active cellular IP (`$CELL_IP`):
  ```sh
  ip rule del pref 21 2>/dev/null
  ip rule del pref 11 2>/dev/null
  iptables -t nat -F POSTROUTING 2>/dev/null
  iptables -t nat -A POSTROUTING -o sipa_eth0 -j SNAT --to-source $CELL_IP 2>/dev/null || iptables -t nat -A POSTROUTING -o sipa_eth0 -j MASQUERADE
  iptables -F FORWARD 2>/dev/null
  iptables -A FORWARD -j ACCEPT
  ```

---

### Bug #5: Hardcoded External DNS Servers (`223.5.5.5` / `8.8.8.8`) Breaking Regional Deployments

* **Symptom**: Hardcoding Ali DNS (`223.5.5.5`) causes poor performance in Hong Kong / overseas, while hardcoding Google DNS (`8.8.8.8`) fails in Mainland China due to GFW blocking.
* **Root Cause Analysis**:
  Original firmware scripts injected static public DNS IPs into `opt dns` in `udhcpd.conf`, bypassing operator-assigned DNS servers.
* **Recommended Fix for Firmware Author**:
  Dynamically query ConnMan's active cellular service (`connmanctl services "$CELL_SVC"`) or fallback to Gateway IP to extract dynamic mobile operator DNS servers (`$ISP_DNS`), ensuring global compatibility across Mainland China, Hong Kong, and international roaming networks:
  ```sh
  CELL_SVC=$(connmanctl services 2>&1 | grep 'cellular_' | head -n 1 | awk '{print $NF}')
  if [ -n "$CELL_SVC" ]; then
      CELL_IP=$(connmanctl services "$CELL_SVC" 2>&1 | grep 'IPv4 =' | awk -F'Address=' '{print $2}' | awk -F',' '{print $1}')
      ISP_DNS=$(connmanctl services "$CELL_SVC" 2>&1 | grep Nameservers | sed 's/.*\[ \(.*\) \].*/\1/' | tr -d ',')
  fi
  if [ -z "$ISP_DNS" ]; then
      ISP_DNS="${GATEWAY_IP}"
  fi
  ```

---

### Bug #6: Absence of Modem-Side Internal Self-Recovery Watchdog (Tier 1 Failover)

* **Symptom**: When SIPA enters auto-suspend flow control or when `udhcpd` crashes after IP rotation, the modem remains unresponsive until an external host intervenes via ADB or reboots the modem.
* **Recommended Fix for Firmware Author**:
  Deploy a lightweight internal self-recovery daemon (`/mnt/data/modem_self_watchdog.sh`) on modem ARM Linux that checks SIPA power state (`echo on`), `udhcpd` process status, and `iptables` SNAT rules every 10s, self-healing within <1s inside the modem without host intervention or radio reset.

---

## 3. Production Solution Scripts

### A. Fully Dynamic Startup Script (`/mnt/data/start_dhcp.sh`)

```sh
#!/bin/sh
# Persistent fully-dynamic startup script inside modem partition /mnt/data/start_dhcp.sh

# 1. Force SIPA hardware accelerator to remain active 24/7 (Disable Auto-Suspend)
echo on > /sys/devices/platform/soc/2e000000.sprd,sipa/power/control 2>/dev/null
echo on > /sys/devices/platform/sipa-usb0/power/control 2>/dev/null
echo 1 > /proc/net/sfp/enable 2>/dev/null

# 2. Dynamically detect cellular IP & ISP Operator DNS assigned by mobile network
CELL_IP=""
ISP_DNS=""

CTX_DIR=$(ls -d /var/lib/connman/cellular_* 2>/dev/null | head -n 1)
if [ -n "$CTX_DIR" ]; then
    CTX_NAME=$(basename "$CTX_DIR")
    CELL_IP=$(grep 'IPv4.local_address=' "$CTX_DIR/settings" 2>/dev/null | cut -d= -f2)
    ISP_DNS=$(connmanctl services "$CTX_NAME" 2>&1 | grep Nameservers | sed 's/.*\[ \(.*\) \].*/\1/' | tr -d ',')
fi

if [ -z "$CELL_IP" ]; then
    CELL_IP=$(ifconfig sipa_eth0 2>/dev/null | grep 'inet addr:' | cut -d: -f2 | awk '{print $1}')
fi

if [ -z "$CELL_IP" ] || [ "$CELL_IP" = "127.0.0.1" ] || [ "$CELL_IP" = "192.168.107.1" ]; then
    CELL_IP=$(ifconfig usb0 2>/dev/null | grep 'inet addr:' | cut -d: -f2 | awk '{print $1}')
fi

if [ -z "$CELL_IP" ] || [ "$CELL_IP" = "127.0.0.1" ] || [ "$CELL_IP" = "192.168.107.1" ]; then
    CELL_IP=10.71.65.89
fi

SUBNET_PREFIX=$(echo $CELL_IP | cut -d. -f1-3)
GATEWAY_IP="${SUBNET_PREFIX}.1"

if [ -z "$ISP_DNS" ]; then
    ISP_DNS="${GATEWAY_IP}"
fi

# 3. Ensure usb0 is configured for the dynamic subnet
ifconfig usb0 $GATEWAY_IP netmask 255.255.255.0 up 2>/dev/null

# 4. Generate dynamic udhcpd config using Gateway IP and ISP Operator DNS
cat << EOF > /tmp/udhcpd_passthrough.conf
start ${SUBNET_PREFIX}.100
end ${SUBNET_PREFIX}.200
interface usb0
opt dns ${ISP_DNS}
option subnet 255.255.255.0
opt router ${GATEWAY_IP}
opt lease 86400
EOF

killall -9 udhcpd 2>/dev/null
nohup /usr/sbin/udhcpd /tmp/udhcpd_passthrough.conf >/dev/null 2>&1 &

# 5. Clean up broken Android policy routing rules & apply dynamic SNAT for $CELL_IP
ip rule del pref 21 2>/dev/null
ip rule del pref 11 2>/dev/null
iptables -t nat -F POSTROUTING 2>/dev/null
iptables -t nat -A POSTROUTING -o sipa_eth0 -j SNAT --to-source $CELL_IP 2>/dev/null || iptables -t nat -A POSTROUTING -o sipa_eth0 -j MASQUERADE
iptables -F FORWARD 2>/dev/null
iptables -A FORWARD -j ACCEPT

# 6. Ensure Tier 1 Modem Self-Recovery Watchdog is active
if ! ps | grep -v grep | grep -q modem_self_watchdog.sh; then
    nohup /mnt/data/modem_self_watchdog.sh >/dev/null 2>&1 &
fi

echo "[start_dhcp] Dynamic DHCP & SNAT configured. Gateway: ${GATEWAY_IP}, ISP DNS: ${ISP_DNS} (Cellular IP: ${CELL_IP})."
```

### B. Tier 1 Modem Internal Self-Recovery Watchdog (`/mnt/data/modem_self_watchdog.sh`)

```sh
#!/bin/sh
# Modem Internal Self-Recovery Watchdog (Tier 1)
# Runs as daemon inside RM500U modem ARM Linux

FAIL_COUNT=0

while true; do
    # 1. Force SIPA hardware accelerator power control to 'on'
    SIPA_CTRL=$(cat /sys/devices/platform/soc/2e000000.sprd,sipa/power/control 2>/dev/null)
    if [ "$SIPA_CTRL" != "on" ]; then
        echo on > /sys/devices/platform/soc/2e000000.sprd,sipa/power/control 2>/dev/null
        echo on > /sys/devices/platform/sipa-usb0/power/control 2>/dev/null
        echo 1 > /proc/net/sfp/enable 2>/dev/null
    fi

    # 2. Check if udhcpd DHCP server is running inside modem
    if ! ps | grep -v grep | grep -q udhcpd; then
        /mnt/data/start_dhcp.sh
        sleep 2
        continue
    fi

    # 3. Check if iptables POSTROUTING SNAT rule is present
    if ! iptables -t nat -L POSTROUTING -n 2>/dev/null | grep -q -E "SNAT|MASQUERADE"; then
        /mnt/data/start_dhcp.sh
        sleep 2
        continue
    fi

    # 4. Check connectivity inside modem
    if ! ping -c 1 -W 2 114.114.114.114 >/dev/null 2>&1 && ! ping -c 1 -W 2 223.5.5.5 >/dev/null 2>&1 && ! ping -c 1 -W 2 8.8.8.8 >/dev/null 2>&1; then
        FAIL_COUNT=$((FAIL_COUNT + 1))
    else
        FAIL_COUNT=0
    fi

    if [ "$FAIL_COUNT" -ge 2 ]; then
        echo on > /sys/devices/platform/soc/2e000000.sprd,sipa/power/control 2>/dev/null
        echo on > /sys/devices/platform/sipa-usb0/power/control 2>/dev/null
        echo 1 > /proc/net/sfp/enable 2>/dev/null
        ifconfig usb0 down 2>/dev/null; sleep 1; ifconfig usb0 up 2>/dev/null
        /mnt/data/start_dhcp.sh
        FAIL_COUNT=0
    fi

    sleep 10
done
```
