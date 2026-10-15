; The engine runs apart from the app window, so stop it before files are replaced or removed.
; Services started by StackPad are separate processes and keep running.
!macro NSIS_HOOK_PREINSTALL
  nsExec::Exec 'taskkill /F /IM StackPadEngine.exe'
!macroend

; Agents and terminals call `StackPad.exe pad list`, so the install folder joins the user PATH.
; The registry value is edited as written, keeping entries such as %USERPROFILE%\bin unexpanded.
!macro NSIS_HOOK_POSTINSTALL
  nsExec::Exec `powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command "$$d='$INSTDIR'.TrimEnd('\'); $$k=[Microsoft.Win32.Registry]::CurrentUser.CreateSubKey('Environment'); $$p=[string]$$k.GetValue('Path','',[Microsoft.Win32.RegistryValueOptions]::DoNotExpandEnvironmentNames); $$parts=@($$p -split ';' | Where-Object { $$_ }); if (-not ($$parts | Where-Object { $$_.TrimEnd('\') -ieq $$d })) { $$k.SetValue('Path', (@($$parts) + $$d) -join ';', [Microsoft.Win32.RegistryValueKind]::ExpandString) }"`
  SendMessage 0xFFFF 0x1A 0 "STR:Environment" /TIMEOUT=5000
!macroend

!macro NSIS_HOOK_PREUNINSTALL
  nsExec::Exec 'taskkill /F /IM StackPadEngine.exe'
  Delete "$SMSTARTUP\StackPad.lnk"
!macroend

!macro NSIS_HOOK_POSTUNINSTALL
  nsExec::Exec `powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command "$$d='$INSTDIR'.TrimEnd('\'); $$k=[Microsoft.Win32.Registry]::CurrentUser.CreateSubKey('Environment'); $$p=[string]$$k.GetValue('Path','',[Microsoft.Win32.RegistryValueOptions]::DoNotExpandEnvironmentNames); $$parts=@($$p -split ';' | Where-Object { $$_ -and $$_.TrimEnd('\') -ine $$d }); $$k.SetValue('Path', $$parts -join ';', [Microsoft.Win32.RegistryValueKind]::ExpandString)"`
  SendMessage 0xFFFF 0x1A 0 "STR:Environment" /TIMEOUT=5000
!macroend
