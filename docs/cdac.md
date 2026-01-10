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


## CDAC Weight Calculation Algorithms

### Overview

The CDAC weight calculation determines the capacitance values for each bit in the capacitor array. Different strategies provide trade-offs between area, matching, and redundancy for error correction.

**Key Parameters:**
- $N$: Number of DAC bits (resolution)
- $M$: Number of physical capacitors ($M = N + N_{extra}$)
- $N_{extra}$: Number of extra capacitors for redundancy
- $W_i$: Weight of capacitor $i$ (in units of $C_u$)
- $C_u$: Unit capacitance

### Strategy 1: Radix-2 (Binary Weighted)

Classic binary weighting with no redundancy.

**Algorithm:**
```
FOR i = 0 TO N-1:
    W[i] = 2^(N-1-i)
END FOR

IF N_extra > 0:
    FOR i = N TO N+N_extra-1:
        W[i] = 1
    END FOR
END IF
```

**Mathematical Form:**
$$W_i = 2^{N-1-i} \quad \text{for } i \in [0, N-1]$$

**Properties:**
- Total capacitance: $C_{total} = (2^N - 1) \cdot C_u$
- Radix: $\beta = 2.0$ (exact)
- Redundancy: None ($N_{extra} = 0$ only)
- Calibratability: Not inherently calibratable

**Example (7-bit):**
$$W = [64, 32, 16, 8, 4, 2, 1]$$

---

### Strategy 2: Sub-Radix-2 (Normalized)

Uses radix $\beta < 2$ to provide redundancy through overlapping decision ranges.

**Algorithm:**
```
radix = 2^(N / M)
FOR i = 0 TO M-1:
    W[i] = max(1, floor(radix^(M-1-i)))
END FOR
```

**Mathematical Form:**
$$\beta = 2^{N/M}$$
$$W_i = \max(1, \lfloor \beta^{M-1-i} \rfloor) \quad \text{for } i \in [0, M-1]$$

**Properties:**
- Total capacitance: $C_{total} \approx (2^N - 1) \cdot C_u$ (slightly higher due to quantization)
- Radix: $\beta < 2.0$
- Redundancy: Overlapping ranges provide $\beta - 1$ LSB tolerance per bit
- Calibratability: Inherent due to overlapping decision ranges

**Example (9-bit, 11 caps):**
$$\beta = 2^{9/11} \approx 1.78$$
$$W = [290, 164, 93, 52, 30, 17, 9, 5, 3, 1, 1]$$

**Error Tolerance:**
$$\text{Overlap}_i = W_i - \sum_{j=i+1}^{M-1} W_j$$

---

### Strategy 3: Sub-Radix-2 (Unbounded)

Similar to normalized but uses rounding instead of flooring, allowing better radix approximation.

**Algorithm:**
```
radix = 2^(N / M)
FOR i = 0 TO M-1:
    W[i] = round(radix^(M-1-i))
END FOR
```

**Mathematical Form:**
$$W_i = \text{round}(\beta^{M-1-i}) \quad \text{where } \beta = 2^{N/M}$$

**Properties:**
- More accurate radix approximation than normalized
- Total capacitance may slightly exceed binary equivalent
- Better preserves exponential relationship between weights

---

### Strategy 4: Sub-Radix-2 with Redistribution

Redistributes a portion of the MSB into paired redundant weights.

**Algorithm:**
```
n_redist = N_extra + 2

// Base binary weights
FOR i = 0 TO N-1:
    W[i] = 2^(N-1-i)
END FOR

// Subtract from MSB
W[0] = W[0] - 2^n_redist

// Generate paired redundant weights
FOR i = n_redist-2 DOWN TO 0:
    FOR j = 0 TO 1:  // Two copies of each weight
        W_redun[k] = 2^i
        k = k + 1
    END FOR
END FOR
W_redun[k] = 1  // Final unit pair
W_redun[k+1] = 1

// Merge: offset redundant weights by 1 position
FOR i = 0 TO N-1:
    result[i] = result[i] + W[i]
END FOR
FOR i = 0 TO length(W_redun)-1:
    result[i+1] = result[i+1] + W_redun[i]
END FOR
```

**Mathematical Form:**
$$W_0 = 2^{N-1} - 2^{n_{redist}}$$
$$W_{redun} = [2^{n_{redist}-2}, 2^{n_{redist}-2}, \ldots, 2^0, 2^0, 1, 1]$$

**Properties:**
- Maintains binary total: $\sum W_i = 2^N - 1$
- Paired redundancy at specific bit positions
- Suitable for foreground calibration

**Constraint:**
$$2^{N-1} \geq 2^{n_{redist}} \quad \text{(MSB must not go negative)}$$

---

### Strategy 5: Radix-2 Repeat

Inserts duplicated capacitors at regular intervals in a binary array.

**Algorithm:**
```
// Base radix-2 array
FOR i = 0 TO N-1:
    W_base[i] = 2^(N-1-i)
END FOR

// Calculate spacing
spacing = N / N_extra

// Identify positions to duplicate
FOR k = 0 TO N_extra-1:
    pos_from_end = 1 + k * spacing
    idx = N - 1 - pos_from_end
    duplicate_positions[k] = idx
END FOR

// Build result with duplicates
j = 0
dup_idx = 0
FOR i = 0 TO N-1:
    W[j] = W_base[i]
    j = j + 1
    IF i in duplicate_positions:
        W[j] = W_base[i]  // Insert duplicate
        j = j + 1
    END IF
END FOR
```

**Mathematical Form:**
$$W_i = 2^{N-1-i} \quad \text{(base weights)}$$
$$\text{Duplicate at positions: } \{N-1-s, N-1-2s, \ldots\} \quad \text{where } s = \lfloor N/N_{extra} \rfloor$$

**Properties:**
- Redundancy concentrated at specific weights
- Maintains binary structure with localized redundancy
- Useful for targeted error correction at critical bits

---

### Coarse-Fine Partitioning

For weights above a threshold $T$ (typically 64), the implementation is straightforward. For weights $W \leq T$, three split strategies decompose the capacitance:

#### No Split
$$C_{main} = 1 \cdot C_u, \quad m = W$$

Simple array of unit capacitors.

#### Voltage Divider Split
$$W = q \cdot T + r \quad \text{where } q = \lfloor W/T \rfloor, \; r = W \mod T$$

- **Coarse part** (if $q > 0$): $C = T \cdot C_u$, $m = q$, driven by $V_{DD}$
- **Fine part** (if $r > 0$): $C = 1 \cdot C_u$, $m = 1$, driven by $V_{DD} \cdot r/T$ via resistor divider

#### Difference Capacitor Split
$$W = q \cdot T + r$$

- **Coarse part** (if $q > 0$): 
  - Main: $C_{main} = T \cdot C_u$, $m = q$
  - Diff: $C_{diff} = 1 \cdot C_u$, $m = q$
  - Effective: $(T - 1) \cdot q \cdot C_u$

- **Fine part** (if $r > 0$):
  - Main: $C_{main} = (T + 1 + r) \cdot C_u$, $m = 1$
  - Diff: $C_{diff} = (T + 1 - r) \cdot C_u$, $m = 1$
  - Effective: $2r \cdot C_u$

**Effective capacitance:**
$$C_{eff} = C_{main} - C_{diff}$$

This approach trades increased total capacitance for improved matching by using difference operation.

---

### Driver Sizing

Driver transistor width is scaled by the square root of total capacitance to maintain consistent RC time constants:

$$W_{driver} = \max\left(1, \left\lfloor \sqrt{C \cdot m} \right\rfloor\right)$$

where $C$ is the capacitance value and $m$ is the multiplier.
