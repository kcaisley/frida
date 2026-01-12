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


    latch_external                           latch_internal
    ---------------------------------------------------------
a)    direct connection (share clked hi rst)        clocked hi reset
c)    clocked  powergate (no reset)                 signalled lo reset
d)    signalled powergate, signalled reset (low)    signalled lo reset
e)    N/A                                           clocked lo reset, signalled powergate
f)    N/A                                           signaled lo reset, signaled powergate


Also, not shown in the picture are latch_external configurations where:
      clocked powergate, clocked reset
      clocked powergate, signalled reset
      signaled powergate, but no reset)
      signaled powergate (but no reset)

Also, on the the latch_internal a configuration not listed is:
      clocked power gate, signalled reset
      
Note that the four of those could existe in a clocked or signaled latch internal rsearch, except for [clocked powergate, clocked reset] 
      
So in otherwords, the powergate (a power gate) can be (signaled or clocked), and can be positioned as a pullup/down in the latch internal node, or can be external. If the powergate is external, then a the latch external reset can either be [signalled, clocked, or noreset].

And regardless of the powergate position, the latch_internal always needs a reset, and can take a value of clocked or signalled. Also please note that if a power gate is used at the internal node, then you won't have anything on the external node, because we try to not stack more than 3 transistors between the rails.

One weird case is the example a), the strong arm latch, with the direct connection. We can cover this with the single_stage variable. In this case, all the other variables are ignored, and simply add in the cross coupled 4T latch and the internal clocked reset (in this case which are pull ups, unlike in the doublestage, where all internal resets are pulldowns.)
