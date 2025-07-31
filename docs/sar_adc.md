- The trade off between performance (noise, linearity, speed) and costs (power, area) in SAR ADCs is tricky, because each block has a difference relationship between these. For example large CDACs have worse speed, but large comparators and sampling switches can typically improve the speed.
- The quantization noise, and 3 thermal noises T+H, DAC, comparator add linearly (assuming noise is expressed in power), since there is no amplification in the circuit. Not all ADCs are this way.
- Typically at high resolutions comparator noise is the trickest to reduce, on a fixed power budget
- Sampling switch non-linearity sets a speed x resolution frontier
- digital is linearity with N, analog power is exponential with N (due to mismatch/noise)
    - So @ high resolution, analog comp or DAC dominates
    - but @ low resolution analog really scales down, so digital dominates, limited to the minimum values for the analog blocks.

## SAR ADC Limiting Factors (10-12 bit ADCs)

| Factor | Limiting Block |
|--------|----------------|
| Noise | Comparator, DAC |
| Linearity | DAC, T&H |
| Speed | Delay of blocks, T&H |
| Area | DAC |
| Power | Comparator |

*Note: Within each category, blocks are listed in order of importance. Also analysis is simplified for 10-12 bit ADCs.*

- Clock boosting and bootstrapping are two alternative to transmission gates. Clock boosting can drive too high though, and so bootstrapping is better (and more linear)
- Capacitive coupling and leakage across sampling switch are mostly an issue with ADC with dynamic input signals (which we won't have)
    - one interesting thing to note, is that with shrinking nodes both leakage and capacitive coupling (smaller D/S spacing!) get worse
- The DAC noise is actually composed of the reference noise plus the dac reference noise!
- Both input buffers and reference buffers depend on C_tot, so making Ctot smaller reduces the performance required of these buffers

