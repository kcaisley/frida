# Topology Parameters

stage_count = 1 or 2
preamp_topo = diffpair or cmos
input_xtors = pmos or nmos 
preamp_power = dynamic or static
preamp_reset = none, vss, or vcm
latch_clock = independent or shared

# Topology Generation

stage_count determines if the preamp is a seperate diffpair / CMOS circuit (stage_count = 2), or if it is integrated into the latch stage (=1). The structure of these is mostly determined by the subsequent parameters, but the stage_count is needed because it determines whether the intermediate node is high impedance (as it's tied to input of second stage xtor gates) or low impedance (diff pair connected in series to source terminals of cross coupled latch)

preamp_topo determines the configuration of the preamp. If stage_count=1, the only valid setting is diffpair, and it's integrated into the subsequetn cross coupled latch. If stage_count=2, then the preamp can be either a 5T OTA (diffpair) or two non-cross coupled inverters.

input_xtors determines if the input pair in the preamp uses NMOS or PMOS transistors. This then affects it's subsequent connection to the latch. For some clairty, the preamp input nodes (gates of the amp devices) are inn and inp, and xp and xn for the intermediate nodes. xtail is the preamp tail node. The devices have an M prefix followed by P on N with then tail, amp, and bias for the current mirror sources at the top. When the input type is PMOS, the tail and amp transistors are PMOS, while the bias transistors are NMOS. And vice versa, when the input type is NMOS, the tail and amp transistors are NMOS, while the bias transistors are PMOS.

preamp_power determines if the preamp is connected to the power rails by a switch or a static supply voltage. If stage_count=1, the only valid setting is dynamic, and it's integrated into the subsequent cross coupled latch. If stage_count=2, then the preamp can be either a 5T OTA (diffpair) or two non-cross coupled inverters.


# Topology Generation
