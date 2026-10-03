# Normalized chi-square method

EIS Gold Studio v1.6.0 reports a scale-independent, Z-modulus-normalized **pseudo chi-square** for each fitted spectrum.

For measured impedance `Z_i` and fitted impedance `Zhat_i`, the normalized contribution at frequency point `i` is

```text
q_i = ((Re(Zhat_i - Z_i))^2 + (Im(Zhat_i - Z_i))^2) / |Z_i|^2
```

The software reports:

```text
pseudo_chi2 = sum(q_i)
reduced_pseudo_chi2 = pseudo_chi2 / (N - k)
relative_residual_RMS_percent = 100 * sqrt(pseudo_chi2 / N)
```

where:

- `N` is the number of complex frequency points used in the fit;
- `k` is the number of free fitted parameters; locked parameters are not counted;
- `N - k` is the displayed chi-square degrees of freedom.

A very small numerical floor is applied only if a measured impedance modulus is zero. The metric is calculated after fitting from ordinary squared residuals, independently of the selected robust loss.

## Interpretation

The metric is dimensionless and is unchanged when the same spectrum is expressed in ohms, kilo-ohms, or mega-ohms. For a uniform complex relative residual of approximately 1%, the unreduced mean normalized error is approximately `1e-4`; the reduced value is close to this when `N` is much larger than `k`.

This is an EIS **pseudo chi-square**, not a formal statistical chi-square, because `|Z_i|` is used as a normalization scale rather than a measured standard deviation. Exact agreement with another program requires the same data points, circuit, parameter constraints, residual sign, weighting convention, and degrees-of-freedom convention.

## Legacy value

The previous implementation calculated

```text
sum(|Zhat_i - Z_i|^2) / (2N - k)
```

which has units of ohm squared and changes with the impedance scale. It is retained in reports as `Legacy raw reduced variance / ohm^2` for traceability, but it is no longer presented as the main reduced chi-square.
