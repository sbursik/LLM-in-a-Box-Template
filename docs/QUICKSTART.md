# Quickstart

## Windows
1. Double-click `WINDOWS-start_server.bat`.
2. A server window opens and the browser should launch.
3. Log in at the local URL shown in the server window.

## macOS
1. Double-click `START-HERE.command` from Finder.
2. The browser should launch to the local URL.
3. Note: First time only, you may need to make it executable:
   `chmod +x START-HERE.command MACOS-LINUX-start_server.sh`

## Linux
1. Open Terminal and go to the USB root folder.
2. Make the script executable (first run only):
   `chmod +x MACOS-LINUX-start_server.sh`
3. Run the server:
   `./MACOS-LINUX-start_server.sh`
4. The browser should launch to the local URL.

## Optional flags
- Fixed port: `python app/launcher/launch.py --port 8000`
- No browser auto-open: `python app/launcher/launch.py --no-browser`
