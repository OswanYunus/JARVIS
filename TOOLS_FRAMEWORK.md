# J.A.R.V.I.S Tools Framework (50+ Tools)

## Why 50+ Tools?
Each tool represents a **specific action** J.A.R.V.I.S can take. More tools = more automation = smarter AI.

---

## 1. **System Management (12 tools)**
- `uninstall_app` (winget) — Uninstall software
- `install_app` — Install software from winget
- `list_installed_apps` — Query installed software
- `restart_computer` — Reboot system
- `shutdown_computer` — Graceful shutdown
- `lock_screen` — Lock Windows
- `hibernate` — Put PC in hibernation
- `sleep_mode` — Sleep mode
- `logout_user` — Log out current user
- `create_restore_point` — System restore point
- `check_disk_health` — Run disk diagnostic (SMART)
- `update_windows` — Check for Windows updates

**Example pattern:**
```python
def run_restart_computer(tool_call):
    reason = tool_call.get("reason", "Requested by user")
    os.system(f'shutdown /r /t 10 /c "{reason}"')  # 10 second delay
    return {"tool": "restart_computer", "message": "Restart scheduled in 10 seconds..."}
```

---

## 2. **File & Folder Management (10 tools)**
- `create_file` (exists)
- `delete_file` — Delete file safely (ask first)
- `move_file` — Move file to destination
- `copy_file` — Copy file
- `rename_file` — Rename file/folder
- `create_folder` — Create directory
- `delete_folder` — Delete folder (recursive option)
- `empty_recycle_bin` — Clear trash
- `zip_files` — Compress files
- `unzip_files` — Extract archives

**Fuzzy example:**
```python
def find_best_file_match(filename, search_path="C:/"):
    matches = find_files_recursive(filename, search_path)
    best = difflib.get_close_matches(filename, matches, n=1, cutoff=0.7)
    return best[0] if best else None
```

---

## 3. **Security & Maintenance (12 tools)**
- `scan_malware` — Run Windows Defender scan
- `update_antivirus` — Update virus definitions
- `disable_startup_app` — Remove from startup
- `enable_startup_app` — Add to startup
- `clear_temp_files` — Delete %temp% folder
- `clear_cache` — Clear browser cache
- `clear_dns_cache` — Flush DNS
- `reset_network` — Reset TCP/IP stack
- `check_firewall` — Verify Windows Firewall status
- `view_running_processes` — List active processes
- `kill_process` — Force-kill process by name
- `monitor_cpu_usage` — Get CPU metrics

**Malware scan example:**
```python
def run_scan_malware(tool_call):
    result = subprocess.run(
        ["powershell", "-Command", "Start-MpScan -ScanType QuickScan"],
        capture_output=True, text=True, timeout=300
    )
    return {"tool": "scan_malware", "message": "Malware scan started. Check Windows Defender..."}
```

---

## 4. **Network Management (8 tools)**
- `check_internet_speed` — Test upload/download speed
- `ping_server` — Ping hostname/IP
- `show_wifi_networks` — List available Wi-Fi
- `connect_wifi` — Connect to Wi-Fi network
- `disconnect_wifi` — Disconnect from Wi-Fi
- `show_ip_address` — Display local/public IP
- `open_port` — Add firewall rule
- `close_port` — Remove firewall rule

---

## 5. **System Information (8 tools)**
- `get_system_info` — CPU, RAM, OS version
- `get_disk_usage` — Storage breakdown by drive
- `get_battery_status` — Battery % and health
- `get_network_info` — Network adapter details
- `list_usb_devices` — USB devices connected
- `get_installed_software` — All installed apps
- `check_driver_updates` — Outdated drivers
- `get_temperature` — CPU/GPU temperature

---

## 6. **Task Automation (5 tools)**
- `schedule_task` — Create Windows scheduled task
- `run_scheduled_task` — Execute task immediately
- `delete_scheduled_task` — Remove scheduled task
- `list_scheduled_tasks` — View all tasks
- `backup_files` — Backup to external drive

---

## 7. **Browser & Web (8 tools)** *(Already exist)*
- `open_browser_tab`
- `close_browser_tab`
- `clear_browser_data` — Delete cookies, history
- `download_file` — Download from URL
- `check_dns` — Resolve domain to IP
- `open_file_in_app` — Associate file with app
- `set_wallpaper` — Change desktop background
- `take_screenshot` — Capture screen to file

---

## 8. **Advanced Power User (7 tools)**
- `edit_registry` — Modify Windows Registry (dangerous!)
- `run_batch_script` — Execute .bat file
- `run_powershell_script` — Execute PowerShell script
- `mount_iso` — Mount ISO file
- `eject_usb` — Safely eject USB drive
- `compare_files` — Show diff between files
- `compress_partition` — Optimize drive

---

## Implementation Strategy

### Step 1: Add tool inference
```python
def infer_malware_scan_tool(message):
    lowered = message.lower()
    if any(w in lowered for w in ("scan", "virus", "malware", "threat")):
        if any(w in lowered for w in ("scan", "check", "run")):
            return {"tool": "scan_malware", "mode": "quick"}
    return None
```

### Step 2: Add tool runner
```python
def run_scan_malware(tool_call):
    # implementation
```

### Step 3: Register in `choose_tool()` priority order
```python
def choose_tool(message, model):
    malware_tool = infer_malware_scan_tool(message)
    if malware_tool:
        return malware_tool
    # ... rest of tools
```

### Step 4: Add to `run_tool()` dispatcher
```python
if t == "scan_malware":
    return run_scan_malware(tool_call)
```

### Step 5: Add to planner prompt
```python
'{"tool":"scan_malware","mode":"quick"}\n'
```

---

## Total Tools Summary
- Existing: 10 (create_file, open_browser_tab, uninstall_app, etc.)
- Ready to add: 40+ (frameworks above)
- **Total: 50+ tools**

---

## Which Tools Matter Most?

**Priority 1 (Do First):**
1. `install_app` + `list_installed_apps` (complements uninstall)
2. `scan_malware` (security critical)
3. `delete_file` (common request)
4. `get_system_info` (diagnostics)

**Priority 2 (Then Add):**
5. `restart_computer`
6. `clear_temp_files`
7. `list_scheduled_tasks`
8. `check_internet_speed`

**Priority 3 (Polish):**
- Remaining admin/maintenance tools
