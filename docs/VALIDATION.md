# Validation and scientific acceptance checklist

## Automated verification

Run the complete regression suite in a clean environment:

```bash
python -m pip install -e ".[test]"
python -m pytest
```

The GitHub Actions workflow repeats this test suite on supported Python versions with Qt in off-screen mode. A release should not be published unless every required workflow is green.

## Numerical benchmark expectations

For each impedance element and composite circuit, maintain synthetic tests that verify:

1. recovery of known parameters from noise-free spectra;
2. stable behavior in low- and high-frequency limits;
3. correct open/short termination behavior for finite diffusion and TLM elements;
4. equivalent results after unit-preserving rescaling;
5. deterministic results for the fixed multi-start seed;
6. refusal or warning for unsupported scientific transformations.

## Experimental-data checks

Before interpreting a fitted spectrum:

- verify the sign convention and imported column mapping;
- inspect frequency ordering, duplicate points, magnitude/phase consistency, and perturbation amplitude;
- use formal Lin-KK validation outside the current application when publication-grade stationarity/causality validation is required;
- compare fitted curves and real/imaginary residuals over the complete frequency range;
- inspect bound proximity, uncertainty, correlation, Jacobian conditioning, and multi-start stability;
- confirm that every named parameter corresponds to the same physical process across compared samples;
- treat DRT peaks, diffusion scores, TLM fits, and automated topology suggestions as hypotheses.

## Known methodological limits in v1.13.2

- The consistency screen is not a complete Boukamp/Schönleber Lin-KK test.
- The displayed modulus-normalized chi-square is a pseudo-chi-square unless experimental variances are supplied.
- Model ranking is a documented engineering heuristic, not a posterior model probability.
- Jacobian-derived standard errors are local approximations.
- DRT regularization is user-selected and requires a sensitivity analysis.
- Global DC-series fitting does not yet report covariance or confidence intervals.
- A successful TLM fit does not uniquely prove porous transport.
