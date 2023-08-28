Pixel sensor FOM:

focus on charge based sensor readout. Must ignore different input sensors, as ADCs foms typically do?
REduce down to individual pixek, but specify area + power per
Factor out monolitichi/hybrid specific parameters
Single-shot pulse signal: SNR isn't useful, as signal+noise is measured in energy, not power?
ADC FOMs factor out dynamic range by making to a part of the the distoritaion (via SNDR), do I have this luxury? ADCs and assume a sinusoidal input, but I don't have that?

In a single pulse system, can the accuracy of the energy measurement be made arbitrarily accurate by stretching the pulse out over a longer period of time, or larger period of amplitude?

No, I don’t believe so, because even if the input was ideally noise free, there is no such thing as noise free amplification. In any case, post amplification the signal to noise ratio of the signal fed to the quantizer, now full-scale.