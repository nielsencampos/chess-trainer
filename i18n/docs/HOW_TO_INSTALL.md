# {{install.title}}

{{languages}}

{{notice}}

{{install.intro}}

## {{install.download.title}}

{{install.download.text}}

| {{install.download.computer}} | {{install.download.file}} |
|---|---|
| {{install.download.windows}} | `chess-trainer-…-windows-x64-setup.exe` |
| {{install.download.macArm}} | `chess-trainer-…-macos-arm64.zip` |
| {{install.download.macIntel}} | `chess-trainer-…-macos-intel.zip` |
| {{install.download.linux}} | `chess-trainer-…-linux-x86_64.tar.gz` |

{{install.download.needs}}

{{install.download.whichMac}}

{{install.download.size}}

## {{install.open.title}}

### Windows

1. {{install.windows.run}}
2. {{install.windows.smartscreen}}
3. {{install.windows.installer}}
4. {{install.windows.open}}

{{install.windows.webview}}

{{install.windows.zip}}

### macOS

1. {{install.mac.unzip}}
2. {{install.mac.drag}}
3. {{install.mac.first}}
   - {{install.mac.sequoia}}
   - {{install.mac.sonoma}}

   {{install.mac.remembers}}

{{install.mac.damaged}}

```bash
xattr -dr com.apple.quarantine "/Applications/Chess Trainer.app"
```

### Linux

1. {{install.linux.unpack}}
2. {{install.linux.terminal}}

   ```bash
   ./install.sh
   ```

   {{install.linux.copies}}
3. {{install.linux.open}}

{{install.linux.x11}}

## {{install.data.title}}

{{install.data.text}}

| {{install.data.system}} | {{install.data.folder}} |
|---|---|
| Windows | {{install.data.windows}} |
| macOS | {{install.data.mac}} |
| Linux | `~/.local/share/chess-trainer` |

{{install.data.apart}}

### {{install.backup.title}}

1. {{install.backup.close}}
2. {{install.backup.copy}}

{{install.backup.restore}}

## {{install.update.title}}

{{install.update.text}}

## {{install.uninstall.title}}

1. {{install.uninstall.remove}}
   - {{install.uninstall.windows}}
   - {{install.uninstall.mac}}
   - {{install.uninstall.linux}}
2. {{install.uninstall.data}}

## {{install.trouble.title}}

- {{install.trouble.one}}
- {{install.trouble.port}}
- {{install.trouble.report}}

## {{install.docker.title}}

{{install.docker.text}}
