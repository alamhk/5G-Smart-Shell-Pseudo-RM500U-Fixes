#!/usr/bin/env python3
"""
rm500u_direct_at.py - Generic Direct LibUSB AT Tool for Unisoc V510 / Pseudo-RM500U
Compatible with FreeBSD, OPNsense, OpenWrt, Linux and macOS.

Features:
- Zero external Python pip dependencies (uses built-in ctypes + system libusb).
- Direct bulk communication with USB Interface 4 (EP OUT 0x04, EP IN 0x85).
- Bypasses missing OS serial driver /dev/cuaU* or /dev/ttyUSB* kernel nodes.
- Built-in multi-process file locking.
- Supports single AT command execution, interactive shell, status query, and PDU re-dial.
"""

import sys
import os
import time
import fcntl
import ctypes
import argparse
import re

# Device USB Identity (Quectel RM500U / Unisoc V510 ECM Mode)
DEFAULT_VID = 0x2C7C
DEFAULT_PID = 0x0900
DEFAULT_INTF = 4
DEFAULT_EP_OUT = 0x04
DEFAULT_EP_IN = 0x85

LOCK_FILE = '/tmp/rm500u_libusb.lock'

# Load System LibUSB Library
def load_libusb():
    candidates = [
        '/usr/lib/libusb.so',          # FreeBSD standard
        '/usr/local/lib/libusb.so',    # FreeBSD local
        '/usr/lib/libusb-1.0.so.0',    # Linux / OpenWrt
        '/usr/lib64/libusb-1.0.so.0',  # Linux 64-bit
        'libusb-1.0.dylib',            # macOS
        'libusb.so'                    # Fallback
    ]
    for path in candidates:
        try:
            return ctypes.CDLL(path)
        except OSError:
            continue
    raise RuntimeError("Could not locate system libusb library. Please ensure libusb is installed.")

libusb = load_libusb()

class libusb_device_handle(ctypes.Structure): pass

libusb.libusb_init.argtypes = [ctypes.POINTER(ctypes.c_void_p)]
libusb.libusb_init.restype = ctypes.c_int
libusb.libusb_open_device_with_vid_pid.argtypes = [ctypes.c_void_p, ctypes.c_uint16, ctypes.c_uint16]
libusb.libusb_open_device_with_vid_pid.restype = ctypes.POINTER(libusb_device_handle)
libusb.libusb_claim_interface.argtypes = [ctypes.POINTER(libusb_device_handle), ctypes.c_int]
libusb.libusb_claim_interface.restype = ctypes.c_int
libusb.libusb_release_interface.argtypes = [ctypes.POINTER(libusb_device_handle), ctypes.c_int]
libusb.libusb_release_interface.restype = ctypes.c_int
libusb.libusb_bulk_transfer.argtypes = [
    ctypes.POINTER(libusb_device_handle),
    ctypes.c_ubyte,
    ctypes.c_char_p,
    ctypes.c_int,
    ctypes.POINTER(ctypes.c_int),
    ctypes.c_uint
]
libusb.libusb_bulk_transfer.restype = ctypes.c_int
libusb.libusb_close.argtypes = [ctypes.POINTER(libusb_device_handle)]

ctx = ctypes.c_void_p()
if libusb.libusb_init(ctypes.byref(ctx)) != 0:
    raise RuntimeError("Failed to initialize libusb context.")


class DirectModemAT:
    def __init__(self, vid=DEFAULT_VID, pid=DEFAULT_PID, intf=DEFAULT_INTF,
                 ep_out=DEFAULT_EP_OUT, ep_in=DEFAULT_EP_IN):
        self.vid = vid
        self.pid = pid
        self.intf = intf
        self.ep_out = ep_out
        self.ep_in = ep_in

    def _acquire_lock(self):
        try:
            fd = os.open(LOCK_FILE, os.O_CREAT | os.O_RDWR, 0o666)
            fcntl.flock(fd, fcntl.LOCK_EX)
            return fd
        except Exception:
            return None

    def _release_lock(self, fd):
        if fd is not None:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
                os.close(fd)
            except Exception:
                pass

    def _drain(self, handle):
        trans = ctypes.c_int()
        buf = ctypes.create_string_buffer(4096)
        while True:
            r = libusb.libusb_bulk_transfer(handle, self.ep_in, buf, 4096, ctypes.byref(trans), 20)
            if r != 0 or trans.value == 0:
                break

    def send_at(self, cmd_str, timeout=2.5):
        lock_fd = self._acquire_lock()
        try:
            handle = libusb.libusb_open_device_with_vid_pid(ctx, self.vid, self.pid)
            if not handle:
                return f"ERROR: Device (VID 0x{self.vid:04X}, PID 0x{self.pid:04X}) not found."
            
            try:
                ret = libusb.libusb_claim_interface(handle, self.intf)
                if ret != 0:
                    return f"ERROR: Cannot claim interface {self.intf} (libusb code {ret})."

                try:
                    self._drain(handle)
                    cmd = (cmd_str.strip() + "\r\n").encode('ascii')
                    trans = ctypes.c_int()
                    wret = libusb.libusb_bulk_transfer(handle, self.ep_out, cmd, len(cmd), ctypes.byref(trans), 500)
                    if wret != 0:
                        return f"ERROR: Bulk write failed with code {wret}."

                    buf = ctypes.create_string_buffer(4096)
                    output = []
                    start = time.time()
                    last_rx_time = None
                    got_payload = False

                    # Allow longer window for asynchronous dialing commands
                    max_timeout = 8.0 if ("QNETDEVCTL" in cmd_str.upper() or "CGACT" in cmd_str.upper()) else timeout

                    while True:
                        now = time.time()
                        if now - start > max_timeout:
                            break

                        # If payload arrived and channel is silent for 0.3s, complete
                        if last_rx_time and (now - last_rx_time >= 0.3):
                            if got_payload or any(('OK' in x or 'ERROR' in x) for x in output):
                                break

                        r = libusb.libusb_bulk_transfer(handle, self.ep_in, buf, 4096, ctypes.byref(trans), 50)
                        if r == 0 and trans.value > 0:
                            chunk = bytes(buf.raw[:trans.value]).decode('utf-8', errors='ignore')
                            output.append(chunk)
                            last_rx_time = time.time()
                            clean = chunk.replace(cmd_str.strip(), "").strip()
                            if clean:
                                got_payload = True
                        elif r != 0 and r != -7: # -7 is timeout
                            break

                    full_text = "".join(output)
                    cmd_clean = cmd_str.strip()
                    idx = full_text.find(cmd_clean)
                    if idx != -1:
                        full_text = full_text[idx + len(cmd_clean):]

                    res = full_text.strip()
                    return res if res else ("OK" if any('OK' in x for x in output) else "(No response from modem)")
                finally:
                    libusb.libusb_release_interface(handle, self.intf)
            finally:
                libusb.libusb_close(handle)
        finally:
            self._release_lock(lock_fd)

    def redial(self):
        """Execute full PDU Session Reset & Re-dial sequence."""
        print("[1/2] Disconnecting PDU session (AT+QNETDEVCTL=1,0,0)...")
        r1 = self.send_at("AT+QNETDEVCTL=1,0,0", timeout=2.0)
        print("Response:", r1)
        time.sleep(0.6)
        print("[2/2] Re-dialing and saving state (AT+QNETDEVCTL=1,3,0)...")
        r2 = self.send_at("AT+QNETDEVCTL=1,3,0", timeout=4.0)
        print("Response:", r2)
        return r2


def main():
    parser = argparse.ArgumentParser(description="Direct LibUSB AT Tool for Unisoc V510 / Pseudo-RM500U")
    parser.add_argument("command", nargs="*", default=["status"], help="AT command to execute (default: status)")
    parser.add_argument("--vid", type=lambda x: int(x, 0), default=DEFAULT_VID, help="USB Vendor ID (default: 0x2C7C)")
    parser.add_argument("--pid", type=lambda x: int(x, 0), default=DEFAULT_PID, help="USB Product ID (default: 0x0900)")
    parser.add_argument("--intf", type=int, default=DEFAULT_INTF, help="USB Interface (default: 4)")
    parser.add_argument("--redial", action="store_true", help="Execute PDU session disconnect & re-dial sequence")
    parser.add_argument("-i", "--interactive", action="store_true", help="Enter interactive AT terminal")

    args = parser.parse_args()
    modem = DirectModemAT(vid=args.vid, pid=args.pid, intf=args.intf)

    if args.redial:
        modem.redial()
        return

    if args.interactive:
        print("Entering interactive AT console (Type 'exit' or 'quit' to leave):")
        while True:
            try:
                cmd = input("AT> ").strip()
                if not cmd:
                    continue
                if cmd.lower() in ["exit", "quit"]:
                    break
                resp = modem.send_at(cmd)
                print(resp)
                print()
            except (KeyboardInterrupt, EOFError):
                break
        return

    cmd = " ".join(args.command)
    if cmd == "status":
        print("=== Modem Status Check ===")
        for q in ["AT", "AT+CPIN?", "AT+CSQ", "AT+COPS?", "AT+QNETDEVSTATUS=1", "AT+SPENGMD=0,6,0", "AT+SPENGMD=0,14,1"]:
            print(f"--- [{q}] ---")
            print(modem.send_at(q))
            print()
    else:
        print(modem.send_at(cmd))


if __name__ == "__main__":
    main()
