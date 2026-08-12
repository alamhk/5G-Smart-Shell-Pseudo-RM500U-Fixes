# 5G Smart Shell (Pseudo-RM500U Custom Firmware) Fixes & Passthrough Guide
# 5G 智慧殼 / 5G 智能壳 (Pseudo-RM500U 改版韌體/固件) 修復與 IP 直通指南

[English](#english) | [繁體中文](#繁體中文) | [简体中文](#简体中文)

---

<a name="english"></a>
## 🌐 English

> **Project Notice**: This repository provides technical guides, kernel bug reports, and persistent fix scripts for **5G Smart Shell / CPE modules (Unisoc V510 platform)** running third-party custom firmware that emulates the Quectel RM500U AT command set.

### 📌 Project & Firmware Acknowledgments

* **Firmware Author**: **rA9**
* **Upstream Base Project**: [1orz/project-cpe](https://github.com/1orz/project-cpe)
* **Official Community QQ Channel**: [https://pd.qq.com/s/6a7enqayi?b=2](https://pd.qq.com/s/6a7enqayi?b=2)
* **Diagnostics, ADB Analysis & Bugfixes**: Powered by **Google Antigravity AI** (Advanced Agentic Coding Team)
* **Hardware Platform**: Unisoc V510 5G Platform / 5G Smart Shell CPE Module
* **Tested Firmware Build**: `RM500UCNAAR03A11M2G_01.001.01.001` (Yocto Linux 4.14.98 aarch64)

> **Important Disclaimer**: The firmware behaviors, kernel driver fixes, and scripts documented herein apply specifically to third-party custom pseudo-RM500U firmware builds and **do not represent official factory Quectel RM500U hardware or official Quectel firmware releases**.

### 📚 Documentation Index

| Document | Topic & Description |
| :--- | :--- |
| 📄 **[Pseudo_RM500U_Cellular_IP_Rotation_and_Fast_Recovery_Report.md](Pseudo_RM500U_Cellular_IP_Rotation_and_Fast_Recovery_Report.md)** | Technical analysis of frequent cellular IP rotation/handovers, AT command mechanics (`state=0` vs `state=1`), and sub-second fast recovery (<1s). |
| 📄 **[Pseudo_RM500U_ECM_IP_Passthrough_Guide.md](Pseudo_RM500U_ECM_IP_Passthrough_Guide.md)** | Step-by-step setup guide for **ECM IP Passthrough / Bridge Mode** (`nat,0`), including persistent NV config fixes and host router integration. |
| 📄 **[Pseudo_RM500U_Firmware_Bugs_Report_For_Author.md](Pseudo_RM500U_Firmware_Bugs_Report_For_Author.md)** | Technical feedback report for firmware author **rA9** detailing the 3 modem-side bugs (SIPA auto-suspend, `/32` netmask, and passthrough DHCP server absence). |
| 📄 **[Pseudo_RM500U_RNDIS_DHCP_Bugfix_Report.md](Pseudo_RM500U_RNDIS_DHCP_Bugfix_Report.md)** | Technical report detailing root causes and persistent fix scripts for RNDIS NAT Mode (`nat,1`) DHCP leasing failures. |
| 📄 **[Pseudo_RM500U_SIPA_Freeze_Fix_Report.md](Pseudo_RM500U_SIPA_Freeze_Fix_Report.md)** | Analysis and solution for the Unisoc SIPA DMA Hardware Accelerator auto-suspend freeze bug (`power/control = auto`). |

---

<a name="繁體中文"></a>
## 🇭🇰 繁體中文

> **項目說明**：本專案提供針對 **5G 智慧殼 / CPE 模組（紫光展銳 Unisoc V510 晶片平台）** 運行第三方模擬 Quectel RM500U AT 指令集改版韌體嘅技術指南、內核 Bug 分析報告與持久化修復腳本。

### 📌 致謝與社群資訊

* **韌體作者**：**rA9**
* **上遊開源專案**：[1orz/project-cpe](https://github.com/1orz/project-cpe)
* **官方 QQ 頻道連結**：[https://pd.qq.com/s/6a7enqayi?b=2](https://pd.qq.com/s/6a7enqayi?b=2)
* **深度診斷、ADB 分析與修復**：由 **Google Antigravity AI** (Advanced Agentic Coding Team) 全程協助與分析
* **硬體平台**：紫光展銳 Unisoc V510 5G 晶片 / 5G 智慧殼模組
* **測試韌體版本**：`RM500UCNAAR03A11M2G_01.001.01.001` (Yocto Linux 4.14.98 aarch64)

> **重要聲明**：本專案記載之韌體行為、內核驅動修復與腳本僅適用於第三方改版 Pseudo-RM500U 韌體，**不代表 Quectel 移遠原廠 RM500U 硬體或原廠官方韌體**。

### 📚 技術文件索引

| 文件名稱 | 主題與內容說明 |
| :--- | :--- |
| 📄 **[Pseudo_RM500U_Cellular_IP_Rotation_and_Fast_Recovery_Report.md](Pseudo_RM500U_Cellular_IP_Rotation_and_Fast_Recovery_Report.md)** | **頻繁基站 IP 輪換與秒級恢復指南**：分析基站 IP 漂移機制、AT 指令 `<state>=0` 與 `<state>=1` 8秒退避差異，及 0.2 秒極速救網對策。 |
| 📄 **[Pseudo_RM500U_ECM_IP_Passthrough_Guide.md](Pseudo_RM500U_ECM_IP_Passthrough_Guide.md)** | **ECM 模式 IP 直通 / Bridge 橋接模式** (`nat,0`) 設定指南，含 NV 參數修正與路由器對接說明。 |
| 📄 **[Pseudo_RM500U_Firmware_Bugs_Report_For_Author.md](Pseudo_RM500U_Firmware_Bugs_Report_For_Author.md)** | 專門反饋給作者 **rA9** 嘅 Modem 側三大 Bug 報告（SIPA 硬體休眠、`/32` 子網掩碼及直通 DHCP 服務缺失）。 |
| 📄 **[Pseudo_RM500U_RNDIS_DHCP_Bugfix_Report.md](Pseudo_RM500U_RNDIS_DHCP_Bugfix_Report.md)** | **RNDIS NAT 模式** (`nat,1`) DHCP 無法派發 IP 嘅底層原因分析與持久化修復報告。 |
| 📄 **[Pseudo_RM500U_SIPA_Freeze_Fix_Report.md](Pseudo_RM500U_SIPA_Freeze_Fix_Report.md)** | 紫光 SIPA DMA 硬體加速器 Auto-Suspend 閒置假死 Bug (`power/control = auto`) 深度分析與解決方案。 |

---

<a name="简体中文"></a>
## 🇨🇳 简体中文

> **项目说明**：本项目提供针对 **5G 智能壳 / CPE 模块（紫光展锐 Unisoc V510 芯片平台）** 运行第三方模拟移远 Quectel RM500U AT 指令集改版固件的技术指南、内核 Bug 分析报告与持久化修复脚本。

### 📌 致谢与社区信息

* **固件作者**：**rA9**
* **上游开源项目**：[1orz/project-cpe](https://github.com/1orz/project-cpe)
* **官方 QQ 频道链接**：[https://pd.qq.com/s/6a7enqayi?b=2](https://pd.qq.com/s/6a7enqayi?b=2)
* **深度诊断、ADB 分析与修复**：由 **Google Antigravity AI** (Advanced Agentic Coding Team) 全程协助与分析
* **硬件平台**：紫光展锐 Unisoc V510 5G 芯片 / 5G 智能壳模块
* **测试固件版本**：`RM500UCNAAR03A11M2G_01.001.01.001` (Yocto Linux 4.14.98 aarch64)

> **重要声明**：本项目记载之固件行为、内核驱动修复与脚本仅适用于第三方改版 Pseudo-RM500U 固件，**不代表 Quectel 移远原厂 RM500U 硬件或原厂官方固件**。

### 📚 技术文档索引

| 文档名称 | 主题与内容说明 |
| :--- | :--- |
| 📄 **[Pseudo_RM500U_Cellular_IP_Rotation_and_Fast_Recovery_Report.md](Pseudo_RM500U_Cellular_IP_Rotation_and_Fast_Recovery_Report.md)** | **频繁基站 IP 轮换与秒级恢复指南**：分析基站 IP 漂移机制、AT 指令 `<state>=0` 与 `<state>=1` 8秒退避差异，及 0.2 秒极速救网对策。 |
| 📄 **[Pseudo_RM500U_ECM_IP_Passthrough_Guide.md](Pseudo_RM500U_ECM_IP_Passthrough_Guide.md)** | **ECM 模式 IP 直通 / Bridge 桥接模式** (`nat,0`) 设置指南，含 NV 参数修正与主路由器对接说明。 |
| 📄 **[Pseudo_RM500U_Firmware_Bugs_Report_For_Author.md](Pseudo_RM500U_Firmware_Bugs_Report_For_Author.md)** | 专门反馈给作者 **rA9** 的 Modem 侧三大 Bug 报告（SIPA 硬件休眠、`/32` 子网掩码及直通 DHCP 服务缺失）。 |
| 📄 **[Pseudo_RM500U_RNDIS_DHCP_Bugfix_Report.md](Pseudo_RM500U_RNDIS_DHCP_Bugfix_Report.md)** | **RNDIS NAT 模式** (`nat,1`) DHCP 无法分配 IP 的底层原因分析与持久化修复报告。 |
| 📄 **[Pseudo_RM500U_SIPA_Freeze_Fix_Report.md](Pseudo_RM500U_SIPA_Freeze_Fix_Report.md)** | 紫光 SIPA DMA 硬件加速器 Auto-Suspend 空闲假死 Bug (`power/control = auto`) 深度分析与解决方案。 |

---

## 🛠️ Modem 侧持久化修复脚本 / Modem Fix Script (`/mnt/data/start_dhcp.sh`)

```sh
#!/bin/sh
# 5G Smart Shell (Unisoc V510 Pseudo-RM500U) Modem Partition Initialization Script

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
