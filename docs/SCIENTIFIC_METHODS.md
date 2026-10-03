# Scientific backbone and computational algorithm of EIS Gold Studio

**Software version:** EIS Gold Studio v1.13.2  
**Document release:** 4 October 2026  
**Purpose:** manuscript-ready Methods text derived from the released implementation, followed by transparent algorithms and reviewer-facing limitations.

---

## Recommended manuscript section title

**EIS Gold Studio: an auditable workflow for impedance-data standardization, equivalent-circuit inference, distributed-process screening, and potential-dependent analysis**

## 1. Manuscript-ready scientific methods

### 1.1 Software architecture and analytical scope

EIS Gold Studio (version 1.13.2) was developed in Python as a desktop environment for importing, visualizing, fitting, comparing, and exporting electrochemical impedance spectroscopy (EIS) data. The graphical layer was implemented with PySide6, whereas numerical operations were performed with NumPy, pandas, and SciPy. The analytical engine was separated into modules for data standardization, equivalent-circuit evaluation, nonlinear parameter estimation, residual and diffusion diagnostics, distribution-of-relaxation-times (DRT) inversion, Mott–Schottky analysis, paired batch comparison, and global fitting of potential-dependent EIS series. This separation was intended to keep the numerical definitions independent of the user interface and to make each reported quantity traceable to an explicit equation.

The software was designed as a hypothesis-screening and parameter-estimation platform. Equivalent circuits were therefore treated as phenomenological representations that must be justified using cell geometry, electrochemistry, residual behavior, parameter uncertainty, frequency coverage, and independent experiments. A low fitting error alone was not interpreted as proof of a unique mechanism.

### 1.2 Import, sign convention, and quality audit

ASCII text and spreadsheet files were converted to a canonical internal table containing frequency, real impedance, and imaginary impedance. Space, tab, comma, semicolon, and colon delimiters and dot/comma decimal conventions were supported. Optional magnitude, phase, time, potential, and source-index columns were retained when present.

The internal complex convention was

$$
Z(\omega)=Z'(\omega)+jZ''(\omega), \qquad \omega=2\pi f.
$$

Consequently, instrument columns explicitly labelled as $-Z''$ were multiplied by $-1$ during import. For a headerless three-column file, the common $f$, $Z'$, $-Z''$ convention was assumed only when at least 95% of finite values in the third column were non-negative; the conversion and assumption were recorded in the import audit. Frequencies were required to be positive, non-finite rows were removed, and spectra were ordered from high to low frequency. At least four valid complex points were required.

When magnitude or phase columns were supplied, they were cross-checked against values recalculated from $Z'$ and $Z''$. The software generated an audit warning when the median relative discrepancy in $|Z|$ exceeded 2% or when the median absolute phase discrepancy exceeded $2^{\circ}$. These checks identify import or sign inconsistencies; they do not establish electrochemical validity.

### 1.3 Electrical-element definitions

All circuit models were evaluated directly in the complex-frequency domain. The implemented lumped elements were

$$
Z_R=R, \qquad
Z_C=\frac{1}{j\omega C}, \qquad
Z_L=j\omega L,
$$

and the constant-phase element (CPE) was

$$
Z_{\mathrm{CPE}}=\frac{1}{Q(j\omega)^{\alpha}},
\qquad 0.20\leq\alpha\leq1.
$$

Series impedances were added, whereas parallel branches were evaluated from

$$
Z_{\parallel}=\left(\sum_b Z_b^{-1}\right)^{-1}.
$$

The semi-infinite ideal and fractional Warburg elements were, respectively,

$$
Z_W=\frac{\sigma(1-j)}{\sqrt{\omega}}
$$

and

$$
Z_{W_\beta}=\frac{A_W}{(j\omega)^{\beta}},
\qquad 0.25\leq\beta\leq0.75.
$$

Thus, $\beta=0.5$ corresponds to the ideal fractional-power form, while deviations from 0.5 describe an anomalous or distributed response without, by themselves, identifying its microscopic origin.

Finite-length diffusion was represented using

$$
x=\sqrt{j\omega\tau_D},
$$

$$
Z_{W_o}=R_W\frac{\coth(x)}{x}
$$

for an open/blocking termination, and

$$
Z_{W_s}=R_W\frac{\tanh(x)}{x}
$$

for a short/transmissive termination. At low frequency, $Z_{W_o}$ approaches a blocking, near-vertical response with a real contribution $R_W/3$, whereas $Z_{W_s}$ approaches $R_W$. Coupled reaction–diffusion behavior could also be represented with a Gerischer element,

$$
Z_G=\frac{R_G}{\sqrt{1+j\omega\tau_G}}.
$$

### 1.4 Exact transmission-line model used by the software

The software implements a **finite-length, uniform de Levie-type porous-electrode transmission line with a distributed CPE admittance**. It is not an arbitrary ladder selected by the graphical interface. The distributed admittance is

$$
Y_{\mathrm{TLM}}=Q_{\mathrm{TLM}}(j\omega)^{\alpha_T}.
$$

For a blocking or closed pore end, the impedance is

$$
\boxed{
Z_{\mathrm{TLM},o}=
\sqrt{\frac{R_{\mathrm{ion}}}{Y_{\mathrm{TLM}}}}
\coth\!\left(\sqrt{R_{\mathrm{ion}}Y_{\mathrm{TLM}}}\right)
}
$$

and for a transmissive or open-to-transfer termination it is

$$
\boxed{
Z_{\mathrm{TLM},s}=
\sqrt{\frac{R_{\mathrm{ion}}}{Y_{\mathrm{TLM}}}}
\tanh\!\left(\sqrt{R_{\mathrm{ion}}Y_{\mathrm{TLM}}}\right).
}
$$

Here, $R_{\mathrm{ion}}$ is the effective distributed ionic resistance, $Q_{\mathrm{TLM}}$ is the distributed CPE coefficient, and $\alpha_T$ is its exponent. The available topologies are $R_s+\mathrm{TLM}_o$, $R_s+(R_{ct}\parallel\mathrm{CPE})+\mathrm{TLM}_o$, and $R_s+(R_{ct}\parallel\mathrm{CPE})+\mathrm{TLM}_s$. The implementation evaluates complex $\tanh$ with an asymptotically stable form to avoid numerical overflow at large $\operatorname{Re}(x)$.

This TLM represents a normalized, uniform distributed ionic-resistance/interfacial-admittance pathway. It does **not** explicitly resolve pore-radius distributions, a separate electronic rail, spatially varying material properties, or an independently parameterized faradaic termination. Accordingly, a successful TLM fit supports distributed transport/charging as a plausible hypothesis but does not prove a pore mechanism.

### 1.5 Circuit library and user-defined topologies

Nineteen built-in circuit models were available, spanning an ohmic baseline, ideal and CPE-based Randles responses, ideal/fractional/finite Warburg diffusion, Gerischer reaction–diffusion, open and short TLMs, two distributed time constants, lead inductance, and an adsorption-type $R\parallel L$ loop. A visual composer additionally generated auditable series/parallel circuit trees using the same element equations as the built-in library. Each parallel branch was required to contain at least one element.

Circuit names in the exported results represent mathematical topology, not an automatically assigned physicochemical mechanism. For example, $R_{ct}$ was interpreted as charge-transfer resistance only when the experimental configuration justified that assignment.

### 1.6 Parameter initialization and bounded nonlinear fitting

For each spectrum, frequencies were sorted in descending order and invalid points were excluded. Data-derived starting values were estimated as follows: $R_s$ from the median real impedance of the first two to four high-frequency points; the principal arc frequency from the maximum of $-Z''$ outside the lowest-frequency quarter; an initial arc resistance from the real-axis separation between the high-frequency intercept and the post-arc valley; and

$$
C_{\mathrm{init}}\approx\frac{1}{2\pi f_{\mathrm{peak}}R_{\mathrm{arc}}}.
$$

Low-frequency points were used only to initialize diffusion parameters. For an ideal Warburg element,

$$
\sigma_{\mathrm{init}}=\operatorname{median}\left[-Z''\sqrt{\omega}\right],
$$

whereas the fractional exponent was initialized from the slope of $\log(-Z'')$ against $\log\omega$.

Positive-valued parameters were optimized in base-10 logarithmic coordinates, while dimensionless exponents were optimized linearly. This transformation enforced positivity and reduced numerical scale imbalance. Unless manually locked, parameters were estimated using bounded nonlinear least squares. The default residual weighting was modulus weighting,

$$
w_i=\frac{1}{\max(|Z_i|,\epsilon)},
$$

with optional unit weighting or proportional weighting based on $|Z_i'|+|Z_i''|$. The stacked residual supplied to the optimizer was

$$
\mathbf r(\boldsymbol\theta)=
\begin{bmatrix}
\operatorname{Re}\{[\widehat Z_i(\boldsymbol\theta)-Z_i]w_i\}_{i=1}^{N}\\
\operatorname{Im}\{[\widehat Z_i(\boldsymbol\theta)-Z_i]w_i\}_{i=1}^{N}
\end{bmatrix}.
$$

SciPy's bounded trust-region least-squares implementation was used with a soft-$L_1$ robust loss and Jacobian scaling. Five deterministic multi-start trials were used by default. Log-scaled parameters were perturbed with a normal standard deviation of 0.45 in encoded space and linear parameters with a standard deviation of 0.07; the random seed was fixed at 20260720. The solution having the smallest ordinary squared weighted residual among the completed starts was retained. An optional hybrid mode first performed a bounded differential-evolution search and then refined the result by local least squares. User-locked parameters were removed from the optimization vector and were not counted as free parameters.

### 1.7 Fit statistics, uncertainty, and identifiability screening

After optimization, the unweighted complex residual sum of squares was calculated as

$$
\mathrm{RSS}=\sum_{i=1}^{N}
\left[(\widehat Z_i'-Z_i')^2+(\widehat Z_i''-Z_i'')^2\right],
$$

and

$$
\mathrm{RMSE}=\sqrt{\frac{\mathrm{RSS}}{2N}}.
$$

For $n=2N$ real-valued residual components and $k$ free parameters, the information criteria were

$$
\mathrm{AIC}=n\ln(\mathrm{RSS}/n)+2k,
$$

$$
\mathrm{AIC_c}=\mathrm{AIC}+\frac{2k(k+1)}{n-k-1},
$$

and

$$
\mathrm{BIC}=n\ln(\mathrm{RSS}/n)+k\ln n.
$$

These values were used only for comparisons among models fitted to the same spectrum with the same residual convention. Because the final estimates may result from robust, weighted fitting whereas the information criteria use the post-fit unweighted RSS, they should be described as comparative fit criteria rather than exact likelihood evidence.

A scale-independent modulus-normalized residual statistic was calculated from

$$
q_i=\frac{(\widehat Z_i'-Z_i')^2+(\widehat Z_i''-Z_i'')^2}{|Z_i|^2},
$$

$$
\chi^2_{\mathrm{pseudo}}=\sum_i q_i,
\qquad
\chi^2_{\mathrm{pseudo,red}}=
\frac{\chi^2_{\mathrm{pseudo}}}{N-k},
$$

and

$$
\mathrm{RMS}_{\mathrm{relative}}(\%)=
100\sqrt{\frac{1}{N}\sum_i q_i}.
$$

This quantity is explicitly a **pseudo-chi-square**, because $|Z_i|$ is a normalization scale rather than an independently measured standard deviation. It must not be presented as a formal statistical $\chi^2$ unless experimental variances are supplied.

Local parameter standard errors were approximated from

$$
\operatorname{Cov}(\widehat{\boldsymbol\theta})\approx
(J^TJ)^{+}\frac{2C}{2N-k},
$$

where $J$ is the optimizer Jacobian, $C$ is the reported robust cost, and $+$ denotes the Moore–Penrose pseudoinverse. Standard errors of log-encoded parameters were transformed to physical units by the delta method. These are local linearized uncertainty estimates, not bootstrap or profile-likelihood confidence intervals.

Identifiability warnings were generated for parameters within 1% of a bound, relative standard error above 100%, pairwise parameter correlation $|r|>0.98$, Jacobian condition number above $10^{10}$, time constants more than one decade outside the measured time window, materially different solutions among near-optimal starts, or structured residuals. The residual-structure score combined lag-one autocorrelation and normalized mean bias for the real and imaginary residual sequences. A separate physical-plausibility score penalized boundary solutions, resistances far beyond the observed impedance scale, time constants far outside the acquisition window, and degenerate two-CPE branches that numerically imitated fractional diffusion.

### 1.8 Candidate-model ranking

All selected candidate circuits were fitted independently. The automatic ranking score was

$$
S_m=0.55\Delta\mathrm{AIC}_{c,m}
+0.25\Delta\mathrm{BIC}_{m}
+5S_{\mathrm{res},m}
+4S_{\mathrm{phys},m}
+U_m+2W_m+T_m,
$$

where $S_{\mathrm{res}}$ is the residual-structure score, $S_{\mathrm{phys}}$ is the physical-plausibility penalty, $U$ is the accumulated relative-uncertainty penalty, $W$ is the number of warnings, and $T$ is a small diffusion/termination tie-breaker derived from the low-frequency signature. Lower scores were ranked first. Explicit diffusion or distributed-transport models received a small preference when the measured tail was diffusion-like; open Warburg or open TLM models received an additional preference for a sufficiently vertical low-frequency branch. An inductive adsorption model was penalized when no positive-imaginary loop was observed. If a simpler circuit lay within $\Delta\mathrm{AIC_c}\leq2$ of the top-ranked model, the software warned against interpreting the additional elements.

The ranking equation is an **engineering screening heuristic**, not a posterior probability, likelihood-ratio test, or universally validated model-selection law. Final circuit selection remained a scientific decision by the analyst.

### 1.9 Low-frequency diffusion screening

The lowest-frequency subset contained

$$
N_{\mathrm{tail}}=\max\left[5,\min\left(12,\left\lfloor N/3\right\rfloor\right)\right]
$$

points. Linear regression of $-Z''$ against $Z'$ gave the Nyquist slope, coefficient of determination, and tail angle. A second regression of $\log(-Z'')$ against $\log\omega$ estimated a frequency exponent $\beta$. A bounded diffusion-strength score combined Nyquist straightness, proximity to $45^{\circ}$, proximity of $\beta$ to 0.5, and low-frequency growth. The output was classified as strong ideal-Warburg-like, strong fractional/anomalous, possible diffusion, or weak/ambiguous. This result was used only as a model-ranking aid and was never treated as proof of diffusion.

### 1.10 Exploratory DRT inversion

For exploratory separation of overlapping relaxation processes, the impedance was represented as

$$
Z(\omega)=R_{\infty}+
\int\frac{\gamma(\ln\tau)}{1+j\omega\tau}\,d\ln\tau.
$$

The relaxation grid contained 90 logarithmically spaced $\tau$ values by default, extending one decade beyond both $1/(2\pi f_{\max})$ and $1/(2\pi f_{\min})$. Real and imaginary components were inverted jointly using first-difference Tikhonov regularization,

$$
\min_{R_\infty,\boldsymbol\gamma}
\|A\mathbf x-\mathbf b\|_2^2+
\lambda\|D\boldsymbol\gamma\|_2^2,
$$

with $\lambda=10^{-2}$ by default and optional non-negativity of $\gamma$. Because the regularization parameter is not selected automatically and uncertainty is not propagated, the DRT output should be reported as exploratory; conclusions must be checked over a defensible range of $\lambda$.

### 1.11 CPE-to-capacitance conversion

An ideal fitted $C$ or $C_{dl}$ was returned directly as a capacitance candidate. For a resolved resistor directly in parallel with a CPE, the effective capacitance was estimated using the Hsu–Mansfeld peak-frequency relation,

$$
C_{\mathrm{eff}}=left(QR^{1-\alpha}\right)^{1/\alpha}.
$$

The conversion was intentionally refused for a classical faradaic branch in which $R$ and a diffusion element were in series beneath the CPE, because the same expression is not generally valid for that topology. For a user-defined circuit, automatic selection based on element names was accompanied by a process-assignment warning.

### 1.12 Potential-dependent Mott–Schottky analysis

Mott–Schottky input could be provided as direct capacitance, potential-stepped EIS, multiple bias-labelled spectra, or audited fitted capacitance from batch equivalent-circuit analysis. When capacitance was inferred at a selected frequency, the apparent series and parallel definitions were

$$
C_s=-\frac{1}{\omega Z''}
$$

and

$$
C_p=\frac{\operatorname{Im}(1/Z)}{\omega},
$$

respectively. For potential-stepped EIS, measurements were clustered within 5 mV by default and the nearest point to a common target frequency was selected; a point was rejected when its frequency differed from the target by more than 35%. At least four distinct potentials were required to construct a study, and at least three positive-capacitance points were required in the user-selected linear fitting window.

For electrode area $A$, the areal capacitance was $C_A=C/A$. Ordinary least squares was applied to either $1/C_A^2$ or $1/C^2$ against potential,

$$
y=mE+b.
$$

For the area-normalized form, the apparent carrier density was

$$
N_{\mathrm{app}}=rac{2}{q\varepsilon_r\varepsilon_0|m|},
$$

whereas the total-capacitance form included $A^2$ in the denominator. The sign of $m$ classified the response as n-type ($m>0$) or p-type ($m<0$). The x-intercept was $-b/m$, and the reported thermally corrected flat-band potential was

$$
E_{fb}=-\frac{b}{m}-\frac{k_BT}{q}.
$$

The fit reported $R^2$, RMSE, covariance-based standard errors, Student-$t$ confidence intervals, and explicit warnings for a narrow potential span, weak linearity, frequency mismatch, long extrapolation, or a slope confidence interval crossing zero. Carrier density was labelled **apparent** because the result assumes a planar depletion layer, known permittivity, and negligible Helmholtz and surface-state capacitances. The flat-band potential remained on the imported reference-electrode scale.

### 1.13 Global fitting of DC-bias EIS series

Multiple spectra acquired at different DC potentials were fitted to one user-defined circuit after sorting by potential. Every parameter could be assigned one of three modes: (i) shared, with one value for all potentials; (ii) independent, with one value per spectrum; or (iii) smooth, with one value per spectrum and a potential-order regularization penalty. Positive parameters were optimized in logarithmic coordinates. Each spectrum contributed a modulus-normalized complex residual. For a smoothly varying encoded parameter $x_p(E)$, the additional penalty was

$$
\sqrt{\lambda_s}\,\frac{\Delta^2x_p}{x_{p,\max}-x_{p,\min}},
$$

using the second difference for three or more spectra and the first difference for two spectra. The default regularization strength was $\lambda_s=0.08$. One bounded soft-$L_1$ least-squares problem then estimated all spectra simultaneously. Parameter trends and the RMSE of each spectrum were exported versus potential.

The current global-fit module does not calculate covariance, confidence intervals, or model-selection statistics for the joint solution. Smooth trends should therefore be reported as regularized estimates and tested for sensitivity to $\lambda_s$.

### 1.14 Batch, paired, and calibration analysis

Batch files could be fitted using a fixed circuit or an automatic set restricted to models containing an explicit $R_{ct}$. For paired files labelled ST$n$-A and ST$n$-B, the software reported

$$
\Delta R_{ct}=R_{ct,A}-R_{ct,B}
$$

and propagated its standard error under the assumption of independent fits. Different selected topologies for the two members of a pair triggered a warning because nominally identical parameter labels may not represent the same process.

For preliminary calibration, linear regression related the selected resistance response, normally $R_{ct}$, to concentration. With residual standard deviation $s_{y/x}$ and slope $m$, the displayed estimates were

$$
\mathrm{LOD}=\frac{3.3s_{y/x}}{|m|},
\qquad
\mathrm{LOQ}=\frac{10s_{y/x}}{|m|}.
$$

These regression-based values are preliminary. A validated analytical method should use replicate blanks or the calculation prescribed by the applicable validation protocol.

### 1.15 Reproducibility and export

The software retains the import mapping and sign audit, fitted and fixed parameters, approximate standard errors, residual spectra, optimizer settings, quality metrics, model warnings, and diagnostic outputs. Scientific exports should include the raw standardized data, fitted values, residuals, model equation, parameter bounds, weighting convention, selected frequency range, software version, and all warnings. This information is required to reproduce a fit and to distinguish numerical agreement from mechanistic interpretation.

---

## 2. Algorithm for the manuscript

### Algorithm 1. Single-spectrum EIS analysis and circuit ranking

**Input:** source file, candidate circuit set $\mathcal M$, fitting settings, optional fixed parameters.  
**Output:** standardized spectrum, ranked fits, diagnostics, and auditable exports.

1. Read the source table and identify $f$, $Z'$, and $Z''$ using audited aliases or numeric-column fallback.
2. Convert an explicitly labelled $-Z''$ column to the canonical $Z''$ sign; record every automatic assumption.
3. Remove invalid rows and non-positive frequencies, order the spectrum from high to low frequency, and cross-check supplied $|Z|$ and phase.
4. Run pre-fit screens for frequency range, duplicate frequencies, smoothness, high-frequency inductive behavior, and low-frequency diffusion-like behavior.
5. For every circuit $m\in\mathcal M$:
   1. Construct data-derived initial values for $R_s$, arc resistance, characteristic frequency, capacitance/CPE, and any diffusion parameters.
   2. Encode positive parameters as $\log_{10}\theta$; retain $\alpha$ and $\beta$ in linear coordinates.
   3. Remove locked parameters from the optimization vector and impose element-specific bounds.
   4. Optionally run differential evolution to obtain a broad initial candidate.
   5. Run the deterministic multi-start bounded robust least-squares fits.
   6. Retain the converged solution with the smallest squared weighted complex residual.
   7. Recalculate the unweighted complex residual, RMSE, pseudo-$\chi^2$, AIC, AICc, and BIC.
   8. Approximate the covariance from the Jacobian and transform standard errors to physical units.
   9. Calculate residual-structure, physical-plausibility, parameter-correlation, Jacobian-conditioning, boundary, and multi-start diagnostics.
6. Calculate the transparent composite screening score for each successful candidate and rank the models in ascending order.
7. Warn if a simpler model is within $\Delta\mathrm{AIC_c}\leq2$ of the top-ranked model.
8. Require analyst confirmation using experimental design, residuals, uncertainty, frequency coverage, and independent physical evidence.
9. Optionally perform DRT, Mott–Schottky, paired, calibration, or DC-series analyses, preserving the assumptions of each transformation.
10. Export standardized data, equations/topology, parameters, uncertainties, statistics, diagnostics, warnings, and fitted/residual spectra.

### Algorithm 2. Global DC-series fitting

**Input:** at least two EIS spectra with finite DC potentials, one fixed circuit topology, initial values, and one mode per parameter.  
**Output:** parameter trajectories and fitted spectra versus DC potential.

1. Import each spectrum, require at least four valid complex points, and sort the studies by DC potential.
2. Assign each circuit parameter as shared, independent, or smoothly varying.
3. Encode all positive parameter values logarithmically and assemble a single bounded optimization vector.
4. For each spectrum, calculate the modulus-normalized stacked real/imaginary residual.
5. For each smooth parameter, append its normalized first- or second-difference penalty.
6. Minimize the combined residual vector using bounded soft-$L_1$ nonlinear least squares.
7. Decode the physical parameters, reconstruct every impedance spectrum, and calculate per-spectrum RMSE.
8. Export each parameter versus potential and report the chosen regularization strength.
9. Repeat the analysis over plausible regularization strengths before assigning physical meaning to a trend.

---

## 3. Concise scientific backbone for an abstract or software paper

> EIS Gold Studio is an auditable electrochemical-impedance analysis platform that integrates standardized data import, explicit complex-domain equivalent-circuit equations, bounded multi-start robust optimization, information-criterion comparison, residual and identifiability diagnostics, distributed-transport screening, exploratory DRT inversion, potential-dependent Mott–Schottky analysis, and global multi-bias fitting. Positive circuit parameters are estimated in logarithmic coordinates from simultaneously fitted real and imaginary impedance components. Model ranking combines AICc/BIC with transparent penalties for residual structure, weak identifiability, implausible boundary solutions, and unsupported topology; the resulting score is treated as a screening heuristic rather than mechanistic proof. The implemented porous-electrode element is a finite-length de Levie-type transmission line comprising distributed ionic resistance and distributed CPE admittance, with either blocking or transmissive termination. All transformations, sign corrections, fit settings, residuals, warnings, and parameter estimates are retained for reproducible export.

---

## 4. Claims that are scientifically safe

The manuscript may state that the software:

- fits both real and imaginary impedance simultaneously;
- uses bounded, deterministic multi-start robust nonlinear least squares;
- implements 19 named circuits plus user-defined series/parallel topologies;
- implements explicit ideal, fractional, finite-length, Gerischer, and de Levie-type distributed elements;
- reports AICc/BIC, residual structure, local uncertainty, parameter correlation, and identifiability warnings;
- supports exploratory DRT, cautious CPE-to-capacitance conversion, Mott–Schottky analysis, paired/batch comparisons, and regularized global DC-series fitting;
- treats automated model selection and low-frequency classification as hypotheses requiring scientific confirmation.

The manuscript should **not** state that the software:

- uniquely identifies an electrochemical mechanism from one EIS spectrum;
- currently performs a formal Boukamp/Schönleber Lin–Kronig validation;
- reports a formal statistical chi-square in the absence of pointwise experimental variances;
- proves pore transport merely because a TLM fits well;
- provides rigorous global-fit confidence intervals or automatically optimized DRT regularization;
- converts every CPE into a physically meaningful capacitance.

---

## 5. Scientific assessment and priorities before submission

### Scientific strengths

1. Element equations and circuit topology are explicit and traceable.
2. Real and imaginary components are fitted together with positivity-preserving parameter encoding.
3. Deterministic multi-start fitting reduces dependence on one initial guess.
4. Model comparison considers parsimony, residual structure, uncertainty, and physical plausibility instead of RMSE alone.
5. TLM, finite diffusion, DRT, Mott–Schottky, and DC-series methods contain appropriate cautionary labels in the code.
6. Import sign handling and optional-column cross-checks provide a useful audit trail.

### Highest-priority scientific upgrades

1. Add a validated Lin–Kronig implementation and expose residual acceptance criteria.
2. Add profile-likelihood or bootstrap confidence intervals, especially for TLM, finite-diffusion, and multi-time-constant models.
3. Add regularization-path or cross-validation support for DRT rather than relying on one default $\lambda$.
4. Add covariance/uncertainty and model comparison to the global DC-series fitter.
5. Allow replicate-derived pointwise variance weighting so a formal likelihood and statistical $\chi^2$ can be reported.
6. Create benchmark datasets with known parameters for every element, including both TLM terminations and mixed circuits.
7. Report environment metadata and a cryptographic hash of the input data/configuration in scientific exports.

### Release verification requirement

The equations and algorithms in this document are traceable to the v1.13.2 source files listed below. A scientific release must additionally include a clean continuous-integration test run and archived benchmark outputs. Historical test claims in the changelog do not replace validation of the exact published commit.

---

## 6. Primary references to cite

1. de Levie, R. *On porous electrodes in electrolyte solutions: I. Capacitance effects.* **Electrochimica Acta** 8 (1963) 751–780. https://doi.org/10.1016/0013-4686(63)80042-0
2. Hsu, C. H.; Mansfeld, F. *Technical Note: Concerning the Conversion of the Constant Phase Element Parameter $Y_0$ into a Capacitance.* **Corrosion** 57 (2001) 747–748. https://doi.org/10.5006/1.3280607
3. Schönleber, M.; Klotz, D.; Ivers-Tiffée, E. *A Method for Improving the Robustness of linear Kramers–Kronig Validity Tests.* **Electrochimica Acta** 131 (2014) 20–27. https://doi.org/10.1016/j.electacta.2014.01.034
4. Saccoccio, M.; Wan, T. H.; Chen, C.; Ciucci, F. *Optimal Regularization in Distribution of Relaxation Times applied to Electrochemical Impedance Spectroscopy: Ridge and Lasso Regression Methods—A Theoretical and Experimental Study.* **Electrochimica Acta** 147 (2014) 470–482. https://doi.org/10.1016/j.electacta.2014.09.058
5. Gelderman, K.; Lee, L.; Donne, S. W. *Flat-Band Potential of a Semiconductor: Using the Mott–Schottky Equation.* **Journal of Chemical Education** 84 (2007) 685. https://doi.org/10.1021/ed084p685
6. Virtanen, P. *et al.* *SciPy 1.0: fundamental algorithms for scientific computing in Python.* **Nature Methods** 17 (2020) 261–272. https://doi.org/10.1038/s41592-019-0686-2
7. Sivula, K. *Mott–Schottky Analysis of Photoelectrodes: Sanity Checks Are Needed.* **ACS Energy Letters** 6 (2021) 2549–2551. https://doi.org/10.1021/acsenergylett.1c01245

---

## 7. Source-to-method traceability

| Scientific function | Primary implementation |
|---|---|
| Element equations, 19 built-in circuits, custom tree evaluation | `eis_studio/models.py` |
| Nonlinear fitting, statistics, ranking, capacitance conversion, calibration | `eis_studio/fitting.py` |
| Consistency screen, diffusion signature, DRT | `eis_studio/diagnostics.py` |
| Import, sign convention, delimiter/decimal detection, audit | `eis_studio/io_utils.py` |
| Mott–Schottky extraction and regression | `eis_studio/mott_schottky.py` |
| Global potential-series fitting | `eis_studio/dc_series_lab.py` |
| Paired ST A/B analysis | `eis_studio/paired_batch.py` |
| Scientific caution and user workflow | `README.md`, `CHI_SQUARE_METHOD.md` |

