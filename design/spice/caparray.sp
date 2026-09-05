
.SUBCKT caparray cap_topplate cap_shieldplate cap_botplate_main[15] cap_botplate_main[14] cap_botplate_main[13] cap_botplate_main[12] cap_botplate_main[11] cap_botplate_main[10] cap_botplate_main[9] cap_botplate_main[8] cap_botplate_main[7] cap_botplate_main[6] cap_botplate_main[5] cap_botplate_main[4] cap_botplate_main[3] cap_botplate_main[2] cap_botplate_main[1] cap_botplate_main[0] cap_botplate_diff[15] cap_botplate_diff[14] cap_botplate_diff[13] cap_botplate_diff[12] cap_botplate_diff[11] cap_botplate_diff[10] cap_botplate_diff[9] cap_botplate_diff[8] cap_botplate_diff[7] cap_botplate_diff[6] cap_botplate_diff[5] cap_botplate_diff[4] cap_botplate_diff[3] cap_botplate_diff[2] cap_botplate_diff[1] cap_botplate_diff[0]

* C0-first conversion-stage order
* Weights C0..C15: [768, 512, 320, 192, 96, 64, 32, 24, 12, 10, 5, 4, 4, 2, 1, 1]

* Main and Diff capacitors based on exact weight calculations
* Weight 768: 768/64 = 12, so 12*0.4*(65+64) = 619.2f main, 12*0.4*(65-64) = 4.8f diff
Cmain0 cap_topplate cap_botplate_main[0] 619.2f
Cdiff0 cap_topplate cap_botplate_diff[0] 4.8f

* Weight 512: 512/64 = 8, so 8*0.4*(65+64) = 412.8f main, 8*0.4*(65-64) = 3.2f diff
Cmain1 cap_topplate cap_botplate_main[1] 412.8f
Cdiff1 cap_topplate cap_botplate_diff[1] 3.2f

* Weight 320: 320/64 = 5, so 5*0.4*(65+64) = 258f main, 5*0.4*(65-64) = 2f diff
Cmain2 cap_topplate cap_botplate_main[2] 258f
Cdiff2 cap_topplate cap_botplate_diff[2] 2f

* Weight 192: 192/64 = 3, so 3*0.4*(65+64) = 154.8f main, 3*0.4*(65-64) = 1.2f diff
Cmain3 cap_topplate cap_botplate_main[3] 154.8f
Cdiff3 cap_topplate cap_botplate_diff[3] 1.2f

* Weight 96: 64+32, so 0.4*(65+64)+0.4*(65+32) = 90.4f main, 0.4*(65-64)+0.4*(65-32) = 13.6f diff
Cmain4 cap_topplate cap_botplate_main[4] 90.4f
Cdiff4 cap_topplate cap_botplate_diff[4] 13.6f

* Weight 64: Single 64 section, 0.4*(65+64) = 51.6f main, 0.4*(65-64) = 0.4f diff
Cmain5 cap_topplate cap_botplate_main[5] 51.6f
Cdiff5 cap_topplate cap_botplate_diff[5] 0.4f

* Weight 32: 0.4*(65+32) = 38.8f main, 0.4*(65-32) = 13.2f diff
Cmain6 cap_topplate cap_botplate_main[6] 38.8f
Cdiff6 cap_topplate cap_botplate_diff[6] 13.2f

* Weight 24: 0.4*(65+24) = 35.6f main, 0.4*(65-24) = 16.4f diff
Cmain7 cap_topplate cap_botplate_main[7] 35.6f
Cdiff7 cap_topplate cap_botplate_diff[7] 16.4f

* Weight 12: 0.4*(65+12) = 30.8f main, 0.4*(65-12) = 21.2f diff
Cmain8 cap_topplate cap_botplate_main[8] 30.8f
Cdiff8 cap_topplate cap_botplate_diff[8] 21.2f

* Weight 10: 0.4*(65+10) = 30f main, 0.4*(65-10) = 22f diff
Cmain9 cap_topplate cap_botplate_main[9] 30f
Cdiff9 cap_topplate cap_botplate_diff[9] 22f

* Weight 5: 0.4*(65+5) = 28f main, 0.4*(65-5) = 24f diff
Cmain10 cap_topplate cap_botplate_main[10] 28f
Cdiff10 cap_topplate cap_botplate_diff[10] 24f

* Weight 4: 0.4*(65+4) = 27.6f main, 0.4*(65-4) = 24.4f diff
Cmain11 cap_topplate cap_botplate_main[11] 27.6f
Cdiff11 cap_topplate cap_botplate_diff[11] 24.4f

* Weight 4: Same as above
Cmain12 cap_topplate cap_botplate_main[12] 27.6f
Cdiff12 cap_topplate cap_botplate_diff[12] 24.4f

* Weight 2: 0.4*(65+2) = 26.8f main, 0.4*(65-2) = 25.2f diff
Cmain13 cap_topplate cap_botplate_main[13] 26.8f
Cdiff13 cap_topplate cap_botplate_diff[13] 25.2f

* Weight 1: 0.4*(65+1) = 26.4f main, 0.4*(65-1) = 25.6f diff
Cmain14 cap_topplate cap_botplate_main[14] 26.4f
Cdiff14 cap_topplate cap_botplate_diff[14] 25.6f

* Weight 1: Same as above
Cmain15 cap_topplate cap_botplate_main[15] 26.4f
Cdiff15 cap_topplate cap_botplate_diff[15] 25.6f

.ENDS caparray
