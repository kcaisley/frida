
;;;; original from ClioSoft:
;;let( (clioDir)
;;clioDir = getShellEnvVar("CLIOSOFT_DIR")
;;load((strcat clioDir "/scripts/cdsLibMgr.il"))
;;)

  let((clioDir)
     clioDir = getShellEnvVar("CLIOSOFT_DIR")
     when(clioDir
       println("Loading ClioSoft Library Manager files...")
	load((strcat clioDir "/scripts/cdsLibMgr.il"))
       println("Finished Loading ClioSoft Library Manager files.")
     )
  )


