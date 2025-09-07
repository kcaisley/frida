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

## CDAC Construction Principles

For individual capacitor weights

- Defining each bit weights as integers simplifies cap implementation; improves matching
- And defining each bit weight as sum of binary scaled values keeps DEC to just adders
- Finally, keeping sum total to binary scaled total prevents overflow

## SAR Modeling Status

- Threshold noise and variation, reference noise, settling error, capacitor mismatch supported
- Arbitrary CDAC weights, with support for "extended range bits"
- Monotonic and bidirectional-single-side switching supported (CRS, CAS, MCS to be added)
- Analyses for static and dynamic performance analyses ($ENOB @ f_{s}$)
- Single test case requires 20 seconds
- Compatibility with T-Spice, AFS, and Spectre simulator (30hr run, 4hr with Spectre)

## Error Tolerance Strategies

Sub-radix 2 steps

- Creates overlapping search voltages
- In $D_{out}$ procesed as $W_i \times B_i$
- Can also satisfy calibratability requirements

Extended search steps

- In $D_{out}$ procesed as $W_i \times (B_i-0.5)$
- Decreases input amplitude swing to $V_{ref} \times \frac{C}{d}$
- Introduced by CC Liu 2010, where they were additional cap

## Device and Reference Noise Correction

- In most common case, only small LSBs errors will occur from thermal noise.
- Can be corrected by single post-bits, or more comparator power

$$\sigma_n^2 \leq LSB^2 / 2 \times 12$$

## Settling Error Correction

Most pronounced in MSBs, recovery determined by remaining caps:

$$\textrm{Error tolerance @} B_i = \frac{\sum_{i+1}^{M}B_j - B_i} {\sum_{i}^{M}B_j} \times 100 \%$$

## Mismatch Static Error & Calibratability

- Redundancy can absorb static error, but what about mismatch?
- 1-bit comparator = inherintely linear, so CDAC dominates
- Assuming monotonic switching, without cap-reuse like CRS [Tsai 2015]

$$\sigma_{INL_{max}} \approx \frac{1}{2}(\sigma_{C_{unit}})\sqrt{2^N}$$

Visual from both A. Hsu 2013 and W. Liu 2010

## Mismatch Static Error & Calibratability

Lower radixes create more overlap tolerance to prevent missing levels

## Mismatch Static Error & Calibratability

Radix $\beta$ and min. steps vs unit cap mismatch $\sigma_{C_{unit}}$ (A. Hsu 2013)

