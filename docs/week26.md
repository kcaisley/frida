- I can user the following layers:

- M8-M9 power
- M7 sheilding
- M


- Always bottom plate switch
- Bottom plate sampling might be useful above 12-bit 
- Basic NMOS sampling good for low resolution


Cap layout
- Zhaokai 2025 uses bottom inside, top outside, with veritcal crossbars to increase cap density (pg 92)
- Tianyang 2020 uses top plate inside (M4 and M5), with bottom plate creating a bottom plane, side walls, and top plane creating a full box around
    - The row is 1u x 25um, but the unit cap cap only uses 5um of this (two of 10 boxes)
    - plates are 120nm apart, horizontall on same metal layer
- P. Harpe 2018 uses bottom inside, top plate outside. (M4-5 are ground shield, M6-7 are actual caps)
    - plates are 130nm apart, 
- C. Wulff 2017: M1 bottom plate routing, M2 shielding, M3-M4 tied-together bottom plate finger, M4 top plate wrapping around
    - 32 unit caps organized in one group, meaning 5 LSBs fit in one group.
    - Then the MSB use multiples of this, with bit5 in particular uses a half-grounded group.