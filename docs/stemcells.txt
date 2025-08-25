# Copied and reformatting from the Appendix of PH Wei's 2021 Thesis 

Cadence Innovus Settings and Scripts
ALOE generates tcl scripts to interface with Cadence Innovus; the arguments of the scripts are either
read from a master text file or entered through the GUI, as discussed in Appendix B. Because the
user inputs are minimal, and ALOE lacks the timing library, the Innovus command usage in ALOE
is atypical of what is used in a common digital PnR flow. In the following codes, variables are
preceded with a “$” symbol. Codes A.1 and A.2 show how optional floorplan and pin sides can be
specified in Innovus without using a strict .io file that confines their absolute numbers and locations.
Code A.3 shows how ALOE automatically sets up non-default net widths and spacings for the two
sample nets. Multiple non-default rules can be automatically generated from the master input file.
Controlled by the evolutionary algorithm, the net weight generation script is shown in Code A.4,
where each net is assigned to its unique group.

Program Code A.1: Auto-generated floorplanning script in ALOE

floorPlan -r $aspect_ratio $total_utilization 0.0 0.0 0.0 0.0



Program Code A.2: Auto-generated pin side assignment in ALOE:

createPinGroup leftPin -cell $block_name \
-spacing 1 -optimizeOrder
addPinToPinGroup -pinGroup leftPin \
-cell $block_name \


-pin $pin_name
createPinGuide -pinGroup leftPin \
-cell $block_name \
-edge 0 \
-layer $layer_list



Program Code A.4: Auto-generated net weight assignment in ALOE.

add_ndr -name M2W2xS2x_M3W2xS2x_M4W2xS2x_M5W2xS2x \
-generate_via -width_multiplier {M2 2 M3 2 M4 2 M5 2} \
-spacing_multiplier {M2 2 M3 2 M4 2 M5 2}

setAttribute -net $net0 \
-non_default_rule M2W2xS2x_M3W2xS2x_M4W2xS2x_M5W2xS2x \
-bottom_preferred_routing_layer $routing_layer_bottom \


-preferred_routing_layer_effort high
setAttribute -net $net1 \
-non_default_rule M2W2xS2x_M3W2xS2x_M4W2xS2x_M5W2xS2x\
-bottom_preferred_routing_layer $routing_layer_bottom \
-preferred_routing_layer_effort high
Program Code A.3: Auto-generated net width assignment in ALOE.
createNetGroup $group_name
specifyNetWeight $net_name $net_weight



Because AMS circuit netlists tend to be smaller than their digital counterparts, we trade runtime
for optimal multiple-via dropping and highest technological compliance. Importantly, we need to
choose the extraction engine with the highest accuracy to enable the RC-based ranking. Code A.5
shows key settings that enables better-performing AMS layouts in Cadence Innovus. Code A.6
shows the swap cell function (3.6), executed with engineering-change-order (ECO) commands.



Program Code A.5: Key settings for physical-only AMS layouts in FinFET CMOS.APPENDIX A. CADENCE INNOVUS SETTINGS AND SCRIPTS
setDesignMode -process $process_node
setPlaceMode -coreEffort high \


-place_detail_color_aware_legal true
setNanoRouteMode -drouteAutoStop false \
-drouteExpAdvancedMarFix true \
-drouteFixAntenna true \
-drouteUseMultiCutViaEffort high \
-routeWithTimingDriven false \
-routeWithSiDriven false \
-routeAutoPinAccessForBlockPin true \
-routeConcurrentMinimizeViaCountEffort high \
-routeExpAdvancedTechnology true
setExtractRCMode -engine postRoute \
-effortLevel high \
-coupled true \
-qrcCmdFile $fqrc



Program Code A.6: Swap cell function:

proc swapCellsOnNet {netName tail} {
setEcoMode -updateTiming false
setEcoMode -LEQCheck false
setEcoMode -batchMode true
setEcoMode -honorFixedStatus false
setEcoMode -honorDontUse false
setEcoMode -honorDontTouch false
setEcoMode -refinePlace false
setEcoMode -replicatedModules true
deselectAll
selectInstOnNet $netName
foreach instPtr [dbGet selected] {
set instCellName [dbGet $instPtr.cell.name]
if ![string match *$tail $instCellName] {
set instName [dbGet $instPtr.name]
set tiedCell [concat $instCellName$tail]
ecoChangeCell -inst $instName -cell $tiedCell
unset tiedCell
unset instName
}
unset instCellName
}

deselectAll

}
proc swap_cells {args} {
parse_proc_arguments -args $args options
# Set default values
set $options(-net) "VDD"
set $options(-tail) "_tied"
# Swap cells
swapCellsOnNet $options(-net) $options(-tail)
}
define_proc_arguments swap_cells \
-info "Writes TCL scripts to run.\n" \
-define_args \
{{-net "net name" "none" string required}
{-tail "tied cell identifying string" "none" string optional}
}

