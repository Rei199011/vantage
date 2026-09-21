' Lanza los avisos SIN VENTANA, igual que el espejo.
'
' Una ventana que se ve es una ventana que se cierra sin querer: ya paso seis
' o siete veces con el espejo antes de montarlo asi.
'
' El 0 es "oculto" y el False es "no esperes a que termine".
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
carpeta = fso.GetParentFolderName(WScript.ScriptFullName)
sh.Run """" & carpeta & "\avisos_servicio.bat""", 0, False
