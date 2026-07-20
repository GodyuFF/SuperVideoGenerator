' SuperVideoGenerator — silent desktop launcher (double-click like an .exe)
' Hides the console; Electron window is the UI.
Option Explicit
Dim sh, fso, root, desktopDir, nodeCmd, rc
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")

root = fso.GetParentFolderName(WScript.ScriptFullName)
desktopDir = root & "\apps\desktop"
sh.CurrentDirectory = desktopDir

' Prefer LocalAppData mirror for Electron binary download on first run
If Trim(sh.ExpandEnvironmentStrings("%ELECTRON_MIRROR%")) = "%ELECTRON_MIRROR%" Or _
   Trim(sh.ExpandEnvironmentStrings("%ELECTRON_MIRROR%")) = "" Then
  sh.Environment("PROCESS")("ELECTRON_MIRROR") = "https://npmmirror.com/mirrors/electron/"
End If
sh.Environment("PROCESS")("BROWSER") = "none"
sh.Environment("PROCESS")("DESKTOP_WEB_URL") = "http://localhost:5173"

nodeCmd = "cmd /c node start-electron.cjs"
' 0 = hide window, True = wait so we can surface failures
rc = sh.Run(nodeCmd, 0, True)
If rc <> 0 Then
  MsgBox "SuperVideoGenerator failed to start (exit " & rc & ")." & vbCrLf & _
    "Check: .venv, Node.js, and network for Electron download." & vbCrLf & _
    "Or run launch-desktop.bat for logs.", vbCritical, "SuperVideoGenerator"
End If
