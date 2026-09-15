' Lanza el espejo SIN VENTANA.
'
' La tarea programada podria llamar al .bat directamente, pero entonces
' aparece una consola negra en cada inicio de sesion -- y una ventana que se
' ve es una ventana que se cierra sin querer. Ya paso seis o siete veces.
'
' El 0 es "oculto" y el False es "no esperes a que termine".
Set sh = CreateObject("WScript.Shell")
sh.Run """" & CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName) & "\espejo_servicio.bat""", 0, False
