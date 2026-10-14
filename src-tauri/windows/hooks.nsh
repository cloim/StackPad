; The engine runs apart from the app window, so stop it before files are replaced or removed.
; Services started by StackPad are separate processes and keep running.
!macro NSIS_HOOK_PREINSTALL
  nsExec::Exec 'taskkill /F /IM StackPadEngine.exe'
!macroend

!macro NSIS_HOOK_PREUNINSTALL
  nsExec::Exec 'taskkill /F /IM StackPadEngine.exe'
  Delete "$SMSTARTUP\StackPad.lnk"
!macroend
