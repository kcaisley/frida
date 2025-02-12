.subckt dac16_radix in<0> in<1> in<2> in<3> in<4> in<5> 
+ in<6> in<7> in<8> in<9> in<10> in<11> in<12> in<13> 
+ in<14> in<15> out radix=1.8

*20230310 bart & ahmed, used for non-binary dac

eout out gnd vol='
V(in<15>)/pow(radix, 0)+
V(in<14>)/pow(radix, 1)+
V(in<13>)/pow(radix, 2)+
V(in<12>)/pow(radix, 3)+
V(in<11>)/pow(radix, 4)+
V(in<10>)/pow(radix, 5)+
V(in<9>)/pow(radix, 6)+
V(in<8>)/pow(radix, 7)+ 
V(in<7>)/pow(radix, 8)+
V(in<6>)/pow(radix, 9)+
V(in<5>)/pow(radix, 10)+
V(in<4>)/pow(radix, 11)+
V(in<3>)/pow(radix, 12)+
V(in<2>)/pow(radix, 13)+
V(in<1>)/pow(radix, 14)+
V(in<0>)/pow(radix, 15)'


.ends