# How to install Chess Trainer

*[Em português](HOW_TO_INSTALL.pt-BR.md) · [En español](HOW_TO_INSTALL.es.md)*

Chess Trainer is a free program that runs on your own computer. It needs no account and no
internet to play. These steps take about five minutes.

## 1. Download

Open the [Releases page](https://github.com/nielsencampos/chess-trainer/releases/latest) and, under
**Assets**, download the file for your computer:

| Your computer | File |
|---|---|
| Windows 10 or 11 | `chess-trainer-…-windows-x64.zip` |
| Mac with an Apple chip (M1, M2, M3…) | `chess-trainer-…-macos-arm64.zip` |
| Mac with an Intel processor | `chess-trainer-…-macos-intel.zip` |
| Linux (Ubuntu 22.04 or newer, or similar) | `chess-trainer-…-linux-x86_64.tar.gz` |

Not sure which Mac you have? Open the Apple menu → **About This Mac**. "Chip: Apple M…" means
Apple chip; "Processor: Intel" means Intel.

The download is about 100 to 300 MB, because it includes the Stockfish chess engine.

## 2. Install and open

### Windows

1. In your Downloads folder, right-click the zip file → **Extract All…** → **Extract**. Do not run
   the program from inside the zip.
2. Move the extracted `chess-trainer` folder somewhere you keep programs, such as your Documents
   folder.
3. Open the folder and double-click **chess-trainer.exe**.
4. The first time, Windows may show **"Windows protected your PC"** (SmartScreen). It appears because
   the program is new and not signed by a paid certificate, not because something is wrong with
   it. Click **More info**, then **Run anyway**. Windows remembers your choice.
5. To open it more easily next time: right-click **chess-trainer.exe** → **Show more options** →
   **Send to** → **Desktop (create shortcut)**.

If the window stays blank, install the free **Microsoft Edge WebView2 Runtime** from Microsoft's
website (Windows 11 and up-to-date Windows 10 already have it).

### macOS

1. Double-click the zip file in your Downloads folder (Safari may have unzipped it already). You get
   **Chess Trainer**.
2. Drag **Chess Trainer** to your **Applications** folder.
3. Double-click it. The first time, macOS says it cannot verify the app, because it is not
   notarized by Apple (that needs a paid developer account). To open it anyway:
   - **macOS 15 Sequoia or newer:** click **Done**. Open **System Settings** → **Privacy &
     Security**, scroll down to the message about "Chess Trainer" and click **Open Anyway**. Enter
     your password, then click **Open Anyway** again.
   - **macOS 14 Sonoma or older:** Control-click (or right-click) **Chess Trainer** in Applications →
     **Open** → **Open**.

   macOS remembers your choice; from then on it opens normally.

If macOS says the app **"is damaged and can't be opened"**, open the **Terminal** app and paste
this line, then press Return and open the app again:

```bash
xattr -dr com.apple.quarantine "/Applications/Chess Trainer.app"
```

### Linux

1. Unpack the file: double-click it in your file manager and extract it, or run
   `tar xzf chess-trainer-*-linux-x86_64.tar.gz`. You get a `chess-trainer` folder.
2. In a terminal, inside that folder, run:

   ```bash
   ./install.sh
   ```

   It copies the program to `~/.local/opt/chess-trainer` and adds **Chess Trainer** to your
   applications menu. It needs no administrator password.
3. Open **Chess Trainer** from the applications menu. You can also run `./chess-trainer` from the
   folder without installing.

If the window does not open on an X11 desktop, install the `libxcb-cursor0` package (for example
`sudo apt install libxcb-cursor0`).

## Where your games and lines are kept

Your saved games, imported games and your lines are in one file, `chess-trainer.duckdb`, in this
folder. The folder also holds the log (`chess-trainer.log`) and the screen preferences (theme,
language, board) in `webview`.

| System | Folder |
|---|---|
| Windows | `%LOCALAPPDATA%\chess-trainer` (paste it in the File Explorer address bar) |
| macOS | `~/Library/Application Support/chess-trainer` (in Finder: **Go** → **Go to Folder…**) |
| Linux | `~/.local/share/chess-trainer` |

The program and your data are kept apart: installing a new version or removing the program does not
touch your games.

### Back up

1. Close Chess Trainer.
2. Copy the whole `chess-trainer` folder above to a USB drive, a cloud folder or another disk.

To restore, close Chess Trainer and put the folder back in the same place. The database file works
on any system, so you can also use it to move your games to another computer. A database from the
Docker version (`data/chess-trainer.duckdb`) can be copied in the same way.

## Update

Download the new version and install it the same way, replacing the old program (Windows: replace
the folder; macOS: replace the app in Applications; Linux: run `./install.sh` from the new folder).
Your games stay where they are.

## Uninstall

1. Remove the program:
   - **Windows:** delete the `chess-trainer` folder and the desktop shortcut, if you made one.
   - **macOS:** drag **Chess Trainer** from Applications to the Trash.
   - **Linux:** run `~/.local/opt/chess-trainer/install.sh --uninstall`.
2. Only if you also want to erase your games and lines: delete the data folder listed above. This
   cannot be undone, so make a backup first if you may want them later.

## If something goes wrong

- Open only one Chess Trainer at a time.
- Chess Trainer uses port 47800 on your own computer. If another program uses it, Chess Trainer does
  not start; the reason is written in `chess-trainer.log` in the data folder.
- To report a problem, open an [issue](https://github.com/nielsencampos/chess-trainer/issues) and
  attach `chess-trainer.log`.

## The other way: Docker

If you already use Docker, you can run the same app without installing it: see
[Run in the README](README.md#run). It opens in your browser at <http://127.0.0.1:8000> and keeps
its data in the `data/` folder of the project.
