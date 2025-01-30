# analogLib Callbacks

puts "Loading callbacks from [info script]"

set ::bQuietMode false
set ::gdTOLERANCE 1E-6

namespace eval analogLib {

	namespace eval presistor {
		namespace eval polyCoefE {
			set sMin 0
			set sMax 20
			set dMfgGrid 1
			set bTrim true
			set bInteger true
		}
	}
	namespace eval pvcvs {
		namespace eval polyCoef {
			set sMin 0
			set sMax 20
			set dMfgGrid 1
			set bTrim true
			set bInteger true
		}
		namespace eval polyCoefE {
			set sMin 0
			set sMax 20
			set dMfgGrid 1
			set bTrim true
			set bInteger true
		}		
	}
	namespace eval pvcvs2 {
		namespace eval polyCoef {
			set sMin 0
			set sMax 20
			set dMfgGrid 1
			set bTrim true
			set bInteger true
		}
		namespace eval polyCoefE {
			set sMin 0
			set sMax 20
			set dMfgGrid 1
			set bTrim true
			set bInteger true
		}		
	}
	namespace eval pvcvs3 {
		namespace eval polyCoef {
			set sMin 0
			set sMax 20
			set dMfgGrid 1
			set bTrim true
			set bInteger true
		}
		namespace eval polyCoefE {
			set sMin 0
			set sMax 20
			set dMfgGrid 1
			set bTrim true
			set bInteger true
		}		
	}			
	
	namespace eval vcvs {
		namespace eval orderE {
			set sMin 1
			set sMax 3
			set dMfgGrid 1
			set bTrim true
			set bInteger true
		}
		namespace eval polyCoefE {
			set sMin 0
			set sMax 20
			set dMfgGrid 1
			set bTrim true
			set bInteger true
		}
	}

	#******************************************************************************
	# Function Name    : gDiffValues
	# Parameters       : dExpected - Expected Value
	#                    dCalculated - Calculated Value
	# Description      : Checks to see if the values are the same within the
	#                     specified tolerance
	# Returns          : False if the values are the same within the specified
	#                     tolerance, true otherwise
	#******************************************************************************
	#  Revision History
	#   05/22/2008 - NJW - Created function.
	#******************************************************************************
	proc gDiffValues {dExpected dCalculated} {
		global gdTOLERANCE

		set dTemp  [expr abs($dExpected-$dCalculated)]
		if {$dExpected != 0 } {
			set dTemp [expr $dTemp/$dExpected]
		}
		return [expr ($dTemp > $gdTOLERANCE)]
	}

	#******************************************************************************
	# Function Name    : gNearestMultiple
	# Parameters       : nValue - Value
	#                    nFactor - Multiple
	# Description      : The value rounded to the nearest nFactor multiple.
	# Returns          : The rounded value.
	#******************************************************************************
	#  Revision History
	#   11/20/2007 - NJW - Created function.
	#******************************************************************************
	proc gNearestMultiple {nValue nFactor} {
		set dValue [stod $nValue]
		set dFactor [stod $nFactor]
		set dHalfFactor [expr { $dFactor / 2.0 } ]
		if { $dValue >= 0 } {
			set dValue [expr { $dValue + $dHalfFactor } ]
		} else {
			set dValue [expr { $dValue - $dHalfFactor } ]
		}
		return [expr { floor($dValue / $dFactor) * $dFactor } ]
	}

	#******************************************************************************
	# Function Name    : NumtoString
	# Parameters       : dVal - value
	#                    bInteger - Display as integer
	# Description      : Converts the value string handling integer if needed.
	# Returns          : The value as a string.
	#******************************************************************************
	#  Revision History
	#   12/26/2007 - NJW - Created function.
	#******************************************************************************
	proc NumtoString { dVal {bInteger false} } {

		if { $bInteger } {
			set sResult [format "%d" [expr int($dVal)]]
		} else {
			set sResult [dtos $dVal]
		}
		return $sResult
	}

	#******************************************************************************
	# Function Name    : GetValueIfNumber
	# Parameters       : sValue - Value
	#							sVarName - Variable to store the value in.
	# Description      : It gets the value of the property and indicates whether it
	#                     is a number or equation.
	# Returns          : False if the value is a pure number,
	#                     true otherwise
	#******************************************************************************
	#  Revision History
	#   01/05/2010 - NJW - Created function.
	#******************************************************************************
	proc GetValueIfNumber { sValue sVarName } {
		upvar 1 $sVarName dVar
		set bNotVariable 1
		if { $sValue != "" } {
			set nLen [string length $sValue]
			# Find the start of the non-numbers
			if { [regexp -indices {[0-9.]+} $sValue nLocation ] } {
				set nStart [expr [lindex $nLocation 1] + 1]
				if { $nStart < $nLen } {
					set bNotVariable 0
					if { [expr $nLen - $nStart] > 1 } {
						set sSuffix [string range $sValue $nStart end]
						if { [string compare -nocase $sSuffix "meg" ] == 0 } {
							set bNotVariable 1
						}
					} else {
						set cChar [string index $sValue $nStart]
						if { [regexp {[afgkmnptux]+} $cChar] == 1 } {
							set bNotVariable 1
						}
					}
				}
			} else {
				set bNotVariable 0
			}
			if { $bNotVariable } {
				set dVar [stod $sValue]
			}
		} else {
			set bNotVariable 0
		}
		return $bNotVariable
	}

	#******************************************************************************
	# Function Name    : GetPropertyValueIfNumber
	# Parameters       : sPropertyName - Property name
	#                    sVarName - Variable to stroe the value in.
	# Description      : It gets the value of the property and indicates whether it
	#                     can be evaluated, so we don't do a callback check on a
	#                     property that references a .PARAM.
	# Returns          : False if the value contained a non-evaluated result,
	#                     true otherwise
	#******************************************************************************
	#  Revision History
	#   01/05/2010 - NJW - Created function.
	#******************************************************************************
	proc GetPropertyValueIfNumber { sPropertyName sVarName } {
		upvar 1 $sVarName dVar
		set bNotVariable 0
		if { [ property get -exists $sPropertyName] } {
			set sValue [property get -evaluated $sPropertyName]
			set bNotVariable [GetValueIfNumber $sValue "dVar"]
		}
		return $bNotVariable
	}

	proc CheckProp { sPropName } {

		set sDevice [property get -system -name "MasterCell"]

		set sVarBase ::analogLib::${sDevice}::${sPropName}
		set sVarName "${sVarBase}::sMin"
		# Check if the variable exists.
		if { [namespace which -variable $sVarName] != "" } {
			upvar 0 $sVarName sMin
			set sVarName "${sVarBase}::sMax"
			if { [namespace which -variable $sVarName] != "" } {
				upvar 0 $sVarName sMax
				set sVarName "${sVarBase}::bTrim"
				if { [namespace which -variable $sVarName] != "" } {
					upvar 0 $sVarName bTrim
					set sVarName "${sVarBase}::bInteger"
					if { [namespace which -variable $sVarName] != "" } {
						upvar 0 $sVarName bInteger
						set sVarName "${sVarBase}::dMfgGrid"
						if { [namespace which -variable $sVarName] != "" } {
							upvar 0 $sVarName dMfgGrid
							set sDimensionName $sPropName
							set sPropDesc "${sPropName}.Description"
							if { [property get -exists -name $sPropDesc ] } {
								set sValue [property get -name $sPropDesc]
								if { $sValue != "" } {
									set sDimensionName $sValue
								}
							}
							set sResult [CheckSpecificDimension $sDimensionName $sPropName $sMin $sMax $dMfgGrid $bTrim $bInteger]
							#PrintVars {sResult}
							return $sResult
						}
					}
				}
			}
		}
	}

	#******************************************************************************
	# Function Name    : CheckSpecificDimension
	# Parameters       : sDimensionName
	#                    sPropertyName
	#                    sMinimumDimension
	#                    sMaximumDimension
	#                    dMfgGrid
	#                    bInteger
	#                    sProcName
	# Description      : Check if the property is on grid and within range.
	# Returns          : String indicating the error if any.
	#******************************************************************************
	#  Revision History
	#   11/20/2007 - NJW - Created function.
	#******************************************************************************
	proc CheckSpecificDimension { sDimensionName sPropertyName sMinimumDimension sMaximumDimension dMfgGrid { bTrim true } { bInteger false} { sProcName "" } } {

		set bCheckMin 1
		if { $sMinimumDimension == "" } {
			set bCheckMin 0
		}

		set bCheckMax 1
		if { $sMaximumDimension == "" } {
			set bCheckMax 0
		}

		set dMinimumDimension [stod $sMinimumDimension]
		set dMaximumDimension [stod $sMaximumDimension]
		set dDimension 0
		if { [GetPropertyValueIfNumber $sPropertyName "dDimension"] } {
			if { $dMfgGrid != "" } {
				set dSnappedDimension [gNearestMultiple $dDimension $dMfgGrid]
				if { [gDiffValues $dDimension $dSnappedDimension] } {
					set sSnappedDimension [NumtoString $dSnappedDimension $bInteger]
					set sMsg "$sDimensionName is not on the manufacturing grid.  $sDimensionName has been snapped to $sSnappedDimension."
					if { !$::bQuietMode } {
						workspace dialog -prompt $sMsg -warning
						#tk_messageBox -message $sMsg  -type ok -icon error
					}
					puts "Warning: ${sMsg}"
					property set $sPropertyName -value $sSnappedDimension
					set dDimension $dSnappedDimension
				}
			}

			set nMinMaxBoth 0
			if { ($bCheckMin != 0) && ($bCheckMax != 0) } {
				set nMinMaxBoth 2
			} elseif { ($bCheckMin == 0) } {
				set nMinMaxBoth 1
			}

			set sMsg ""
			if { ($nMinMaxBoth == 0) && ($dDimension < $dMinimumDimension) } {
				set sMinDimension [NumtoString $dMinimumDimension $bInteger]
				set sMsg "$sDimensionName is too small.\n$sMinDimension <= $sDimensionName"
			} elseif { ($nMinMaxBoth == 1) && ($dDimension > $dMaximumDimension) } {
				set sMaxDimension [NumtoString $dMaximumDimension $bInteger]
				set sMsg "$sDimensionName is too big.\n$sDimensionName <= $sMaxDimension"
			} elseif { ($nMinMaxBoth == 2) && (($dDimension < $dMinimumDimension) || ($dDimension > $dMaximumDimension)) } {
				set sMinDimension [NumtoString $dMinimumDimension $bInteger]
				set sMaxDimension [NumtoString $dMaximumDimension $bInteger]
				set sMsg "$sDimensionName is out of range.\n$sMinDimension <= $sDimensionName <= $sMaxDimension"
			}
			if { $sMsg != "" } {
				if { $bTrim } {
					if { $dDimension < $dMinimumDimension } {
						set sValue [NumtoString $dMinimumDimension $bInteger]
						property set $sPropertyName -value $sValue
						append sMsg "\nResetting value to $sValue."
					} elseif { $dDimension > $dMaximumDimension } {
						property set $sPropertyName -value [NumtoString $dMaximumDimension $bInteger]
						append sMsg "\nResetting value to $sValue."
					}
				}
				if { !$::bQuietMode } {
					workspace dialog -prompt $sMsg -error
					#tk_messageBox -message $sMsg -type ok -icon error
				}
				set sReturnMsg [string map {"\n" " "} $sMsg]
				puts "Error: ${sReturnMsg}"
				return ""
			}
		}

		if { $sProcName != "" } {
			return [eval $sProcName ]
		}
	}

	proc IsDefault { sVar } {
		if { [property get -exists -name $sVar] && [property get -islocal -name $sVar] } {
			return $sVar
		} else {
			return ""
		}
	}

	proc GetNetlistInstanceName { sECP } {
		set sPrefix ""
		if { ![string equal $sECP "spectre"] } {
			set sPrefixPropName "${sECP}.namePrefix"
			if { [property get -exists -name $sPrefixPropName] } {
				set sPrefix	[property get -name $sPrefixPropName]
			} else {
				set sPrefixPropName "${sECP}.PREFIX"
				if { [property get -exists -name $sPrefixPropName] } {
					set sPrefix	[property get -name $sPrefixPropName]
				}
			}
		}
		set sInstanceName $sPrefix
		append sInstanceName [property get -system -name "Name"]

		return $sInstanceName
	}

	proc GetNetlistPinsNodes { lTermOrder sECP } {

		set lAllNets ""
	   foreach sPin $lTermOrder {
	      foreach sNetName [test bundle $sPin] {
	         set lAllNets [concat $lAllNets [annotate port $sNetName -net]]
	         # database connects -pin $sNetName -shownet -instance $sInstanceName]
	      }
	   }

		if { [string equal $sECP "spectre"] } {
			set lAllNets "(${lAllNets})"
		}

		return $lAllNets
	}

	proc GetNetlistGetTermOrder { sECP } {

		set sInstanceName [property get -system -name "Name"]
		set sPrefixPropName "${sECP}.termOrder"
		if { [property get -exists -name $sPrefixPropName] } {
			set lTermOrder [property get -name $sPrefixPropName]
		} else {
			set sPrefixPropName "${sECP}.PINORDER"
			if { [property get -exists -name $sPrefixPropName] } {
				set lTermOrder [property get -name $sPrefixPropName]
			} else {
				set lTermOrder [database connects -showpin -instance $sInstanceName]
			}
		}
		return $lTermOrder
	}

	proc _nl_GetPropValue { sProp sDefault } {
		set sResult $sDefault
		if { [property get -exists -name $sProp] } {
			set sResult [property get -name $sProp]
		}
		return $sResult
	}

proc _vcvs_hspiceD_nlp { simulator } {

	set sECP "hspiceD"
	set sInstanceName [GetNetlistInstanceName $sECP]
	set lTermOrder [GetNetlistGetTermOrder $sECP]
	
	set sEldoType [_nl_GetPropValue "eldoType" "linear"]
	switch $sEldoType {
		"linear" {
			set lParams {egain maxm minm absol tc1 tc2 scale absol}
		}
		"polynomial" {
			set lParams {egain maxm minm absol tc1 tc2 scale absol}
			set nOrder [_nl_GetPropValue "orderE" 1]
			switch $ {
				2 {
					set lExtraNodes {pcp2 pcn2}
				}
				3 {
					set lExtraNodes {pcp2 pcn2 pcp3 pcn3}
				}
			}

			
		}
		"pwl" {
					
		}
		"and" {
					
		}
		"nand" {
					
		}
		"or" {
					
		}
		"nor" {
					
		}
		"delay" {
					
		}
		"value" {
					
		}
		"table" {
					
		}
		"integration" {
					
		}
		"derivation" {
					
		}
		"sdomain_fns" {
					
		}
		"sdomain_pz" {
					
		}
		"freq" {
					
		}
		"transformer" {
					
		}
		"op-amp" {
					
		}
	}
	
	
	if { [property get -exists -name "eldoType"] } {
		
	}

#	for()
#	set sCoefficents "" ; for {set x 0} {$x<$polyCoefE} {incr x} { append sCoefficients " pn${x}" }
#	
#eldoType
#"linear" "polynomial" "pwl" "and" "nand" "or" "nor" "delay" "value" "table" "integration" "derivation" "sdomain_fns" "sdomain_pz" "freq" "transformer" "op-amp"
#
#eldoType orderE pcp2 pcn2 pcp3 pcn3 egain polyCoefE pn10 pn11 pn12 pn13 pn14 pn15 pn16 pn0 pn1 pn2 pn3 pn4 pn5 pn6 pn7 pn8 pn9 pn17 pn18 pn19 pn20
#	
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


}

puts "   Finished loading callbacks from [info script]"