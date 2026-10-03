# EIS Gold Studio v1.13.2

## Release focus

Version 1.13.2 completes the responsive live-circuit laboratory by moving the live Nyquist/Bode monitor into the right-side Plot tab. This preserves measured-data overlay, RMSE feedback, direct fitting, and frequency-sensitive element highlighting while keeping the schematic canvas unobstructed.

## Scientific capabilities included

- simultaneous complex-domain fitting of real and imaginary impedance;
- 19 built-in equivalent circuits and a validated custom series/parallel composer;
- ideal, fractional, finite-length, Gerischer, and de Levie-type TLM elements;
- bounded log-parameterized multi-start robust least squares and optional hybrid global/local optimization;
- AICc/BIC comparison, residual-structure analysis, local uncertainty, correlation, and identifiability warnings;
- exploratory Tikhonov DRT;
- Mott-Schottky analysis with explicit assumptions and confidence intervals;
- paired ST A/B analysis and preliminary calibration;
- global fitting of DC-bias series with shared, independent, or smoothly varying parameters;
- auditable data import, sign conversion, tabular/graphical export, and publication schematic export.

## Important interpretation limits

- Automated circuit ranking is a screening heuristic, not mechanistic proof.
- The consistency screen is not a formal Lin-KK implementation.
- The modulus-normalized statistic is a pseudo-chi-square unless pointwise experimental variances are supplied.
- DRT regularization requires sensitivity testing.
- A successful TLM fit does not uniquely establish a porous-electrode mechanism.

See `CHANGELOG.md`, `docs/SCIENTIFIC_METHODS.md`, and `docs/VALIDATION.md` for full details.
