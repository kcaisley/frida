puts "Loading em_port netlist procedure from [info script]"

# check sparameter format
proc isTouchStone {} {

	set sFileFormat [property get -name "modelFileType"]
	if { [string equal -nocase $sFileFormat "SMatrixIO"] || \
		  [string equal -nocase $sFileFormat "TSTONEFILE"] } {
		return true
	} elseif { [string equal -nocase $sFileFormat "CITIFILE"] } {
		return false
	}
	return false
}

proc GetInstanceName { sSimulator } {
	set sInstanceName [property get -name "Name" -system]
	if { $sSimulator == "eldo" } {
		set sPrefix [property get -name "eldoD.namePrefix"]
		set sInstanceName "${sPrefix}${sInstanceName} Fblock param:"
	}
	return $sInstanceName
}

proc get_pins {simulator} {

	set pinNum [property get -name p]
	if {${pinNum} < 1} {
		set sErrorMsg "pin number less than 1"
		simulation set_netlisting_error_code -error $sErrorMsg
	}

	set tmpPins {}
	for {set i 1} {$i <= ${pinNum}} {incr i} {
		set pin p$i
		set net [database connects -pin $pin -shownet]
		set tmpPins "${tmpPins}$net "
		set pin m$i
		set net [database connects -pin $pin -shownet]
		set tmpPins "${tmpPins}$net "
	}

	set tmpPins [string trimright ${tmpPins} " "]
	set pins {}

	if {${simulator}=="spectre"} {
		set pins "(${tmpPins})"
	}
	if {${simulator}=="eldo"} {
		set pins "+ pin: ${tmpPins}"
	}

	return ${pins}
}

proc GetSParmFileName { sSimulator } {

	set sAnalysisName [string trim [lindex [split [property get -name "modelFile"] /] 2] "emdata_"]
	set sCellName [property get -name "MasterCell" -system]

	set sParamFile {}

	if { $sSimulator== "spectre" } {
		set sParamFile "nport file="
	}
	if { $sSimulator == "eldo" } {
		set sParamFile "+ string: "
	}

	if { [string first "Linux" [workspace version]] >= 0 } {
		append sParamFile [test tpath getforui [file join  ".." "${sCellName}_${sAnalysisName}"]]
	} else {
		append sParamFile "${sCellName}_${sAnalysisName}"
	}

	if { [isTouchStone] } {
		append sParamFile {.ts}
	} else {
		append sParamFile {.cti}
	}
	return $sParamFile
}

proc get_parameters {simulator} {

	set parametersDict [dict create]
	set instParameters []
	set propMappingList []
	set propMappingDict [dict create]

	if {${simulator}=="spectre"} {
		set instParameters [split [string trim [string trim [property get -name spectre.instParameters] (] )]]
		set propMappingList [lreplace [split [string trim [string trim [property get -name spectre.propMapping] (] )]] 0 0]
	}

	if {${simulator}=="eldo"} {
		set instParameters [split [string trim [string trim [property get -name eldoD.instParameters] (] )]]
		set propMappingList [lreplace [split [string trim [string trim [property get -name eldoD.propMapping] (] )]] 0 0]
	}


	if { [expr [llength $propMappingList] % 2] } {
		set sErrorMsg "the $simulator propMapping properties should be even number"
		simulation set_netlisting_error_code -error $sErrorMsg
	} else {
		for {set i 0} {$i < [expr [llength $propMappingList] / 2] } {incr i} {
			dict set propMappingDict [lindex $propMappingList [expr $i * 2]] [lindex $propMappingList [expr $i * 2 + 1]]
		}
	}

	set value {}
	set eldoParamWhiteList {m idx_m no_delay groupfit symmetry force_passivity force_refit \
		extrap_to_dc force_touch_dc pole_reduction high_precision maxcol maxrow idx_f noise \
		single_reference_node spline_interpolation}

	foreach p $instParameters {

		#~ Eldo: skip parameters that are not in the white list
		if {${simulator}=="eldo" && [lsearch $eldoParamWhiteList [string tolower $p]] == -1} {
			continue
		}

		# the property is in propMapping list
		if { [lsearch [dict keys $propMappingDict] $p] != -1 } {
			set propMappingValue [dict get $propMappingDict $p]
			if { [property get -name $propMappingValue -exist] == 1 && \
				 [property get -name $propMappingValue -islocal] == 1} {
				set value [property get -name $propMappingValue]
				if {$value ne ""} {
					dict set parametersDict $p $value
				}
			}
		} else {
		# the property is not in propMapping list
			if { [property get -name $p -exist] == 1 && \
				 [property get -name $p -islocal] == 1} {
				set value [property get -name $p]
				if {$value ne ""} {
					dict set parametersDict $p $value
				}
			}
		}
	}

	set paramString {}
	dict for {theKey theValue} $parametersDict {
		if {${simulator}=="spectre"} {
			set paramString "$paramString $theKey=$theValue"
		}

		if {${simulator}=="eldo"} {
			set paramString "$paramString+ $theKey=$theValue\n"
		}
	}

	return $paramString
}

proc ConvertSioFile {} {

	# Validation
	# Make sure the Model File Type is correct.
	set sFileFormat [property get -name "modelFileType"]
	if { ![string equal -nocase $sFileFormat "SMatrixIO"] && \
		  ![string equal -nocase $sFileFormat "TSTONEFILE"] && \
		  ![string equal -nocase $sFileFormat "CITIFILE"] } {
		set sErrorMsg "$sFileFormat is not supported. Please choose touchstone or citi format."
		simulation set_netlisting_error_code -error "${sErrorMsg}"
		return "SIM_ERROR: ${sErrorMsg}"
		
	}

	# check if environment variable HPEESOF_DIR exist
	if { ![info exists ::env(HPEESOF_DIR)] } {
		set sErrorMsg "environment variable HPEESOF_DIR is not set and is required. Please set this environment variable."
		simulation set_netlisting_error_code -error "${sErrorMsg}"
		return "SIM_ERROR: ${sErrorMsg}"
	}

	set sTestBench [workspace getactive -testbench]
	set sTopLibrary [workspace getactive -toplevel_design]
	set sTopCell [workspace getactive -toplevel_cell]
	set sTopView [workspace getactive -toplevel_view]

	#~ sio file path
	set sLibPath  [database path -library $sTopLibrary]
	set sModelRelPath [property get -name "modelFile"]
	set sModelPath [file join $sLibPath ".." $sModelRelPath]

	#~ result file path
	set sResultRelPath [property get -name "$sTestBench.General.Results" -evaluated \
		-host view -library $sTopLibrary -cell $sTopCell -view $sTopView]
	set sResultPath [file join $sLibPath $sResultRelPath]

	set sAnalysisName [string trim [lindex [split [property get -name modelFile] /] 2] "emdata_"]
	set cellName [property get -name MasterCell -system]

	set sParamFile "${cellName}_${sAnalysisName}"
	
	if {[isTouchStone]} {
		append sOut { -t }
		append sParamFile {.ts}
	} else {
		append sOut { -c }
		append sParamFile {.cti}
	}

	if { [string first "Linux" [workspace version]] >= 0 } {
			set cmdFile [file join /tmp "sio_2_touchstone.sh"]
			set outfile [open $cmdFile w]

			set sOut "#!/usr/bin/bash"
			set sOut [string trim $sOut]
			puts $outfile $sOut

			#~ Remove Z: from the path
			set newResultpath [test tpath getforui ${sResultPath}]
			set newModelPath [test tpath getforui ${sModelPath}]

			# set sOut {LD_LIBRARY_PATH=$(echo $HPEESOF_DIR/Momentum/*/linux_x86_64/lib):$LD_LIBRARY_PATH $HPEESOF_DIR/bin/siodump -t }
			# append sOut "${newResultpath}/${sParamFile} ${newModelPath}/data.000.sio"
			set sOut {LD_LIBRARY_PATH=$HPEESOF_DIR/lib/linux_x86_64:$LD_LIBRARY_PATH $HPEESOF_DIR/bin/siodump -t}

			append sOut " ${newResultpath}/${sParamFile} ${newModelPath}/data.000.sio > " {/tmp/siodump_results.txt 2>&1}
			puts -nonewline $outfile $sOut
			close $outfile

			#~ Remove ^M a the end of each line
			exec cmd /c start /unix /usr/bin/sed -i "s/\r//g" $cmdFile
			exec cmd /c start /unix /usr/bin/chmod +x $cmdFile
			exec cmd /c start /unix $cmdFile

			set nResultsfile [open "/tmp/siodump_results.txt" r]
	} else {
			set cmd [test tpath getforui [file join $::env(HPEESOF_DIR) bin siodump.exe]]
			set cmd_shortname [file attributes $cmd -shortname]
			
			set sioFile [test tpath getforui [file join ${sModelPath} data.000.sio]]
			set sCmdOutputFile [file join ${sResultPath} "siodump_results.txt"]
			
			set testBench [workspace getactive -testbench]
			set topCell [workspace getactive -toplevel_cell]
			set sResultsHDLPath [test tpath getforui [file join ${sResultPath} ${topCell}]]_$testBench.HDL
			puts $sResultsHDLPath
			if {![file isdirectory $sResultsHDLPath]} {
				file mkdir $sResultsHDLPath
			}
			
			# copy sparameter file to .HDL folder, for AFS simulation
			set sAFSParamFile [test tpath getforui [file join ${sResultsHDLPath} ${sParamFile}]]
			set cmd "$cmd_shortname -t $sAFSParamFile $sioFile  >  $sCmdOutputFile 2>&1"
			exec cmd /k $cmd
			
			# copy sparameter file result folder, for ELDO simulation
			set sEldoParamFile [test tpath getforui [file join ${sResultPath} ${sParamFile}]]
			puts "parameter file: $sEldoParamFile"
			set cmd "$cmd_shortname -t $sEldoParamFile $sioFile  >>  $sCmdOutputFile 2>&1"
			exec cmd /k $cmd
			
			set nResultsfile [open $sCmdOutputFile r]
	}

	set sData [read $nResultsfile]
	close $nResultsfile
	if {$sData != ""} {
		set sErrorMsg "Error: $sData"
		simulation set_netlisting_error_code -error "${sErrorMsg}"
		return $sErrorMsg
	}
}

proc _em_nport_general {simulator} {

	set sInstanceName [GetInstanceName $simulator]

	set pins [get_pins $simulator]

	set sParamFile [GetSParmFileName $simulator]

	set parameters [get_parameters $simulator]

	set netlist {}
	if {${simulator}=="spectre"} {
		set netlist "$netlist$sInstanceName $pins $sParamFile $parameters"
	}

	if {${simulator}=="eldo"} {
		set netlist "$netlist$sInstanceName\n"
		if {$parameters ne ""} {
			set netlist "$netlist$parameters"
		}
		set netlist "$netlist$sParamFile\n"
		set netlist "$netlist$pins"
	}

	return $netlist
}

proc _em_nport_eldo {} {
	set sErrorMsg [ConvertSioFile]
	if {$sErrorMsg != ""} {
		return $sErrorMsg
	}
	return [_em_nport_general eldo]
}

proc _em_nport_spectre {} {
	set sErrorMsg [ConvertSioFile]
	if {$sErrorMsg != ""} {
		return $sErrorMsg
	}
	return [_em_nport_general spectre]
}
puts "\tLoaded em_port netlist procedure."
