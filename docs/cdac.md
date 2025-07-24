SAR ADC is built out of multiple blocks: switch, comparator, references (some designs just use power rails), sequencer/SAR logic (interdependant in async designs) and CDAC
We focus on CDAC, since it is the limited factor for 10-12bit precision in a compact, low power design

# Background
- Show previous ADC designs
- previous designs have been sized to to mismatch
- if we could size to due to sampling noise instead, we'd end up with a smaller CDAC, with reduced power consumption at fixed speed, or potentially faster speed at same power

# CDAC assumptions
- 12-bit, 1.2V supply, 10MHz operation, 
- plot of quantization noise vs resolution
- top side sampling, bottom plate switching
- fringe capacitors, 

# CDAC sampling noise
- plot of sampling noise vs Ctot, for 0.9, 1.2, and 1.8 supply for given 0.x? ENOB degredation of X ENOB design?

# Problem: CDAC mismatch and area are in opposition
- mismatch % of unit per capacitance, for fringe caps of 1-2-3 layers, in 180nm vs 65nm vs 28nm
- binary weighted array expected 4sigma (0.999936) mismatch, for different size arrays, and given
- also can try a monte carlo simulation
- DNL errors essentially worsen quantization noise, and there is an inflection point beyond which calibration isn't possible.
- given math for which

# Strategy 1: Calibration
- of limited effective in binary weighted design, as condition for calibratbility is dependent on mismatch in the thing we're trying to calibrate
- Condition is ______, and in binary design it's 'a short leash" metaphorically

# Strategy 2: CDAC redundancy
- switching caps over a larger number of M:N cycles (Q: doesn't improve linearity alone, but just allows calibration?)
    - This I can answer with 
- Bonus: it also can correct decision errors from comparator/reference noise, which allows us to run faster and/or use a less precision comparator (for earlier decisions)
- essentially trading time budget for improve accuracy and precision
- Plot: N:M expansion (can be expressed as average radix) needed to meet the condition of calibratability
- Note: specific redundancy weights more/less practical

# Strategy 3: CDAC coarse-fine, without making the array much bigger, can we improve the unit device matching
- ways to implemented LSB caps without increasingly worst matching
- inversely, breaking fixed relationship between total area and matching
    - matching of unit device is noise more complicated
- still have to respect required sampling capacitance (some omit more than others? RDAC and unit-legth maintain, bridge cap omits)

# Resulting layouts
- with Strat 1 and Strat 2, we size for sampling noise, and <0.? 'likely' worst case DNL.
- Top side vs bottom side sampling and switching, switching and parasitics, implications for linearity and signal switch
- Graphic: showing unit length cap array and unit cap array, showing
- show layout, including dummy caps

# Strategy 4: switching schemes (can improve linearity, with CRS/VCM techniques, but I won't explore)
- some switching improve linearity, but we won't do them
- other switching reduces power, which we will do
- plots of conventional vs monotonic vs BSS sequence
- plots of power consumption

# How much can calibratability improve?
- foreground better than background, offchip better than on chip, digital vs analog
- only good as input test source, masked by comparator non-linearity and offset and/or non-linearity near rails?
- can I simulate calibratability from my
