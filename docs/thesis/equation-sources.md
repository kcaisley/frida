# Equation sources

Where each numbered equation of the thesis comes from: the cited source, its printed page (the book's
or the journal's own page numbers, as the citations in the text give them) and the source's own
equation number, so that each can be checked against the source. "Own" marks an expression of this
work, derived from the cited ones. The citations render as `[n, p. N]`; the IEEE style has no
equation locator, so equation numbers are kept here.

## Notation

- $N$ bits; $V_\mathrm{FS}$ the differential full-scale span; $\mathrm{LSB} = V_\mathrm{FS}/2^N$; an
  ideal differential array switched between ground and $V_\mathrm{ref}$ has $V_\mathrm{FS} = 2V_\mathrm{ref}$.
- $C$ the capacitance per side; differential sampled noise $2kT/C$; $\sigma_\mathrm{q} = \mathrm{LSB}/\sqrt{12}$.
- $N_\mathrm{DAC}$ the DAC's bits, $N - 1$ with top-plate sampling; $M$ switched weights $w_0 \dots w_{M-1}$
  in LSB, $M + 1$ decisions.
- $A_C$ a single capacitor's matching coefficient in %·√fF (a pair's is $\sqrt{2}$ times larger);
  $A_{V_\mathrm{TH}}$ the threshold's; $A$ alone is area.
- Label subscripts upright ($V_\mathrm{TH}$, $C_\mathrm{P}$, $t_\mathrm{d}$), index subscripts italic ($w_k$).

## Chapter 1

| Equation | Source | Page | Source eq. |
|:--|:--|--:|:--|
| eq-pileup | zambon2021 (Knoll's paralyzable model) | 1 | — |
| eq-integrating | own | | |

## Chapter 2

| Equation | Source | Page | Source eq. |
|:--|:--|--:|:--|
| eq-quantization | pelgrom2022; razavi2025 | 433; 239 | (9.5)–(9.6); (12.6) |
| eq-snr-ideal | pelgrom2022; razavi2025 | 436; 240 | (9.10); (12.10) |
| eq-enob | pelgrom2022; razavi2025 | 439; 248 | (9.17); (12.18) |
| eq-dnl-inl | razavi2025 | 242, 244 | (12.11), (12.12) |
| eq-walden | pelgrom2022 (inverted Walden) | 461 | (9.34) |
| eq-schreier | pelgrom2022; murmann_survey | 459 | — |
| eq-thermal-bound | pelgrom2022 | 458 | (9.32) |

## Chapter 3

| Equation | Source | Page | Source eq. |
|:--|:--|--:|:--|
| eq-ron | razavi2025; pelgrom2022 | 32; 390 | (3.36), (3.38); (8.7) |
| eq-ron-boot | razavi2025 (own combination) | 45, 50 | (3.16), (3.70) |
| eq-tracking | razavi2025 (own combination) | 30, 55 | (3.28), (3.86) |
| eq-hd3 | razavi2025 | 34 | (3.41) |
| eq-jitter | pelgrom2022; razavi2025 | 360; 56 | (7.37); (3.90) |
| eq-settle | razavi2025; pelgrom2022 | 54; 390 | (3.82)–(3.83); (8.6) |
| eq-pedestal | pelgrom2022 | 384 | (8.1)–(8.2) |
| eq-speed-precision | razavi2025 | 38 | (3.50) |
| eq-ktc | razavi2025; pelgrom2022 | 39; 350 | (3.51)–(3.54); (7.27) |
| eq-ktc-samp | razavi2025; pelgrom2022 | 41; 355 | —; (7.32) |
| eq-strongarm-integration | razavi2025 | 116 | (6.53)–(6.55) |
| eq-dynamic-bias | bindra2018 | 1906 | (8) |
| eq-strongarm-noise | razavi2025 (razavi2015 has twice the first term) | 116 | (6.60) (razavi2015 p. 15, (15)) |
| eq-comp-scaling | tang2020 | 1016 | (18)–(19) |
| eq-comp-fom | tang2020; energy razavi2025 | 1016; 97 | (19), (20) |
| eq-regeneration | razavi2025; bankman2019 | 109; 89 | (6.37); — |
| eq-metastability | razavi2025 | 112 | (6.45) |
| eq-avt | pelgrom2022; razavi2025 | 311; 107 | (6.33); (6.28) |
| eq-offset | razavi2025; pelgrom2022 | 93; 617 | (5.39); (12.11) |
| eq-cmin-noise, eq-enob-ktc | razavi2025 | 316 | (15.14)–(15.16) |
| eq-pelgrom | tripathi2014; pelgrom2022 | 2241; 299 | (6); (6.30) |
| eq-midcode | tripathi2014thesis | 28 | (2.8) |
| eq-inl-sigma | razavi2025 | 217 | (11.19) |
| eq-cmin-matching | pelgrom2022 (check: Ex. 16.1) | 768 | — |
| eq-redundancy | ogawa2009 | 67 | (3)–(4) |
| eq-radix | chang2013 | 69 | (3.9) |
| eq-margin | ogawa2009 (last term written as $w_{M-1}$) | 67 | (5) |
| eq-calibratable | own, after chang2013 | 71 | (3.11)–(3.13) |
| eq-switching | mccreary1975; ginsburg2005; pelgrom2022 | 372; 185; 753 | —; (3), (7), (9); (16.5) |
| eq-switching-energy | lin2015 | 71 | (1), (3), (4) |
| eq-driver | own, after pelgrom2022; razavi2025 | 764; 54 | (16.10); (3.82) |
| eq-full-scale | razavi2025; harpe2019 | 218; 638 | (11.21)–(11.22); (4) |
| eq-noise-budget | pelgrom2022; razavi2025 | 439; 321 | (9.16); (15.20) |
| eq-enob-budget | own, from pelgrom2022 | 439 | (9.16)–(9.17) |
| eq-energy | own | | |

## Chapters 5 and 6

| Equation | Source | Page | Source eq. |
|:--|:--|--:|:--|
| eq-code-enob | own, from eq-quantization | | |
| eq-alias | pelgrom2022 | 322 | (7.11) |
| eq-ab-step | own | | |
| eq-dcal | own, after chang2013 | 107 | (4.18)–(4.19) |
| eq-cost, eq-cost-optimum | own | | |

Pages of early-access copies (bindra2018, tang2020, lin2015) are the issue's: the early-access page
plus the article's first page less one.
