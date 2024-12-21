.subckt dac16_radix in<0> in<1> in<2> in<3> in<4> in<5> 
+ in<6> in<7> in<8> in<9> in<10> in<11> in<12> in<13> 
+ in<14> in<15> out radix=1.8

ecomp<0> compout<0> gnd vol='table(V(in<0>), 0.5, 0, 0.6, 1)'
ecomp<1> compout<1> gnd vol='table(V(in<1>), 0.5, 0, 0.6, 1)'
ecomp<2> compout<2> gnd vol='table(V(in<2>), 0.5, 0, 0.6, 1)'
ecomp<3> compout<3> gnd vol='table(V(in<3>), 0.5, 0, 0.6, 1)'
ecomp<4> compout<4> gnd vol='table(v(in<4>), 0.5, 0, 0.6, 1)'
ecomp<5> compout<5> gnd vol='table(v(in<5>), 0.5, 0, 0.6, 1)'
ecomp<6> compout<6> gnd vol='table(v(in<6>), 0.5, 0, 0.6, 1)'
ecomp<7> compout<7> gnd vol='table(v(in<7>), 0.5, 0, 0.6, 1)'
ecomp<8> compout<8> gnd vol='table(v(in<8>), 0.5, 0, 0.6, 1)'
ecomp<9> compout<9> gnd vol='table(v(in<9>), 0.5, 0, 0.6, 1)'
ecomp<10> compout<10> gnd vol='table(v(in<10>), 0.5, 0, 0.6, 1)'
ecomp<11> compout<11> gnd vol='table(v(in<11>), 0.5, 0, 0.6, 1)'
ecomp<12> compout<12> gnd vol='table(v(in<12>), 0.5, 0, 0.6, 1)'
ecomp<13> compout<13> gnd vol='table(v(in<13>), 0.5, 0, 0.6, 1)'
ecomp<14> compout<14> gnd vol='table(v(in<14>), 0.5, 0, 0.6, 1)'
ecomp<15> compout<15> gnd vol='table(v(in<15>), 0.5, 0, 0.6, 1)'

eout out gnd vol='V(compout<7>)/pow(radix, 0)+V(compout<6>)/pow(radix, 1)+V(compout<5>)/pow(radix, 2)+V(compout<4>)/pow(radix, 3)+
+ V(compout<3>)/pow(radix, 4)+V(compout<2>)/pow(radix, 5)+V(compout<1>)/pow(radix, 6)+V(compout<0>)/pow(radix, 7)'

*eout out gnd vol='V(compout<15>)/pow(radix, 0)+V(compout<14>)/pow(radix, 1)+V(compout<13>)/pow(radix, 2)+V(compout<12>)/pow(radix, 3)+
*+ V(compout<11>)/pow(radix, 4)+V(compout<10>)/pow(radix, 5)+V(compout<9>)/pow(radix, 6)+V(compout<8>)/pow(radix, 7)+ 
*+ V(compout<7>)/pow(radix, 8)+V(compout<6>)/pow(radix, 9)+V(compout<5>)/pow(radix, 10)+V(compout<4>)/pow(radix, 11)+
*+ V(compout<3>)/pow(radix, 12)+V(compout<2>)/pow(radix, 13)+V(compout<1>)/pow(radix, 14)+V(compout<0>)/pow(radix, 15)'

*20230310 bart & ahmed, used for non-binary dac

.ends



