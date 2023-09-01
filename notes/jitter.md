'Understanding and Characterizing Timing Jitter' - Primer by Tektronix

* Jitter is short term variation w/ frequencies above 10 Hz, other it is called "wander"
* Must be characterized w/ statistics (mean, standard deviation $\sigma$, and confidence interval)
* High pass filter is useful for physical measurement, to cancel "wander"
* This can be a PLL, which is "nice" because it mimics a real system
* Ideal sinusoid is ideal reference, most often (with same freq. and $\phi$), found via min $\Sigma(error)^2$

$$
A*\sin(\omega_c*t+\phi_c)
$$

where $\omega_c$ and $\phi_c$ are constants chosen to minimize timer error of positions.

## Sampling

Samples in the measurement of jitter can be acquired in three way:

1. Periodic Jitter $J_p$ : Just a histogram of signal periods of a persistent period, measured often in persistence mode (trigger on one edge/peak of waveform, and then measure 'width' on the subsequent edge/peak)

3. Cycle-to-Cycle $J_{c2c}$: First order difference of period jitter, which show dynamics from cycle-to-cycle, for a PLL, etc

$$
J_{c2c}=J_{P_{n+1}}-J_{P_{n}}
$$

3. Time-Interval Error (TIE): uses deviation from ideal reference. Difficult to observe directly with oscilloscope in experimental setup, but is good as it reveals cumulative effect of jitter

$$
TIE_n = \sum\limits_{0}^{n}(J_{p_{n}}-t_{ideal_{n}})
$$

where $n$ is the cumulative edge number, in time. The more cycles go by, the further we will likely find ourselves from the ideal

## Statistics

Mean of the distribution is the reciprocal of the frequency of the signal.

Next, regardless of which method you use to measure timing error, the statistical PDF can either be characterized by it's standard deviation (RMS), or by a more stringent metric tied to a BER. For example, 68% percent of distribution is within one standard deviation, but a BER of 0.32 would be unacceptable, so

$$
J_{pp} = α * Jitter_{rms}
$$
The reason for this peak-to-peak concept is that Gaussian random processes technically have an unbounded peak-to-peak value - one theoretically just needs to take enough samples.

|BER|α|
|---|---|
|10-3|6.180|
|10-4|7.438|
|10-5|8.530|
|10-6|9.507|
|10-7|10.399|
|10-8|11.224|
|10-9|11.996|
|10-10|12.723|
|10-11|13.412|
|10-12|14.069|


## Random vs Determinisitc

The convolution of random data with a deterministic waveform jitter, will create a non-gaussian PDF. For example, in a system with different rise and fall times, the PDF will be Bimodal:

![](../../images/Pasted%20image%2020230615132026.png)

It's instead convolved with a sinusoidal waveform, then you will have a normal area in the middle, with sharp rising gaussian components on the edges.