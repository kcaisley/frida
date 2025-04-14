Take for example the Phantom TMX 7510. The sensor is 1280 wide, vs 800 tall, with the ADCs are along the long edge.

It has 40000 12-bit ADCs, each converting in 523 ns (1912kHz). It's rated at 25 Gpix/s
It looks like there are banks of ADCs on both sides, but thinking of them being on each once, we can calculate we have 32 ADC per pixel column.

At the base rate of 76000 frames per second, that gives ~13158ns per frame. Since we can assume that the 800 vertical pixels are being shared between 32 ADCs, therefore we have 25 pixels per ADC being read, which again works out to ~13075 per frame.

1024000×12×76000 = 933888000000, or 934 Gbps. Also, it's stated that 160 links at 5Gbps are used. Dividing the rate by 160 gives ~5.83Gbps, so this checks out.

With half the ADCS on each side, and half the IO on each side, we can assume 80 IO channels, being shared between 1280 half-height columns. This gives 16 half-height columns per IO, with 16 ADCs being connected. Therefore a 256:1 serializer would be needed, with the inputs running at ~1912 KHz * 12bit = ~22.9Mbps.

The package has 50 pins on each side, with all four pins covered, for a total of 200 pins. Therefore some of the high speed IO are clearly transferring horizontally.

Also of interest is the 18.5 µm pixel pitch. This means the active area is 15mm x 24mm. Therefore the two circuit areas, by visual inspection look to be 5mm x 24mm. If we assume only 60% of that is availabe for ADCs, and that each ADC is double the column width. That means you need to fit 2x400 pixels being read out by 2x16 ADC into and area that is 2x18.5µm * 3000µm. This gives 37x93.75 or ~ 40x100µm per ADC.

By comparison, our design spec is for something with half the area, at 20x100 μm². This took a design team at Forza a signifigant amount of work to achieve, so we are certainly in for a complicated battle.

By the comparison, the 1024x1024 µm pitch Celeritas camera peaks at 2Gpix per second