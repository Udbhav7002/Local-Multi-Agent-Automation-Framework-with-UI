---
name: macOS System Admin
description: Expert commands and workflows for controlling macOS hardware and system settings via CLI.
---

# macOS System Admin Instructions

When the user asks you to control or check macOS system settings, DO NOT USE THE GUI. Use the following expert CLI commands.

## Audio Control
- Check current volume: `osascript -e 'output volume of (get volume settings)'`
- Set volume to 50%: `osascript -e 'set volume output volume 50'`
- Mute volume: `osascript -e 'set volume with output muted'`
- Unmute volume: `osascript -e 'set volume without output muted'`

## Network & Connectivity
- List available Wi-Fi networks: `networksetup -listallhardwareports` (Find Wi-Fi device name, usually en0), then `/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport -s`
- Check current Wi-Fi network: `networksetup -getairportnetwork en0`
- Turn Wi-Fi off: `networksetup -setairportpower en0 off`
- Turn Wi-Fi on: `networksetup -setairportpower en0 on`

## Power & Hardware
- Check battery status and health: `pmset -g batt`
- Prevent sleep for 1 hour: `caffeinate -t 3600 &`
- Check CPU usage (top 5): `top -l 1 -n 5 -s 0 | grep -E "^PID| %CPU"`

## Appearance
- Enable Dark Mode: `osascript -e 'tell application "System Events" to tell appearance preferences to set dark mode to true'`
- Enable Light Mode: `osascript -e 'tell application "System Events" to tell appearance preferences to set dark mode to false'`

CRITICAL INSTRUCTION: When applying these commands, always output a `run_command` action with the exact command above.
