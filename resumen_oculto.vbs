' Lanza el parte del dia SIN VENTANA.
'
' Sin esto, cada noche a las 23:30 apareceria una consola negra un segundo.
' El 0 es "oculto" y el False es "no esperes a que termine".
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
carpeta = fso.GetParentFolderName(WScript.ScriptFullName)
sh.Run """" & carpeta & "\resumen_servicio.bat""", 0, False
