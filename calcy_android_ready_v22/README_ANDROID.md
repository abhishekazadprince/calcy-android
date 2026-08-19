# Calcy Android V12

V12 is a corrective/quality-preserving continuation of V11.

## Important fixes

- Restored the missing `Trajectory3DWidget` import/class so the application starts.
- Restored the proven 3D camera orbit/zoom interaction while removing gesture instructions from the visible 3D information line.
- Planar two-state systems now start face-on and use an orthographic projection, so SHM phase-space circles are not artificially flattened by perspective.
- Genuine 3-state systems retain the oblique perspective renderer.
- Two Body and Ballistic presets use their physical `(x,y,0)` projection in 3D.
- The dense whitish-blue sphere remains only the current-state locator; changing its size never changes the numerical solution.
- Added a HELP button with an in-app scientific user manual plus TXT/PDF download.
- Preserved Custom ODE as the primary symbolic entry point.
- Preserved Graph modes, Table TXT/PDF export, numerical Analysis, dynamic 3D, trail, axes, speed and sphere-size controls.

## Scientific interpretation

For SHM written as `y1'=y2`, `y2'=-k1*k1*y1`, the 3D phase display is `(y1,y2,0)`. This is phase space, not literal physical x-y-z space. The one-dimensional oscillation is the projection onto `y1=x`. For `k1=1`, the phase orbit is circular for the normalized initial condition; for other frequency/scaling choices it is generally elliptical.

## V17 Unicode + solve-field robustness fix

The Help manual uses two bundled Unicode font families instead of forcing one
font to render every script:

- `NotoSansDevanagari` for Hindi/Devanagari prose.
- `DejaVu Sans` for equations, Greek letters, subscripts and mathematical operators.

This prevents tofu/box glyphs such as `y₁`, `ω`, `∞`, `→`, `∂`, `√`, `≤` and `≥`
from appearing in the Hindi section. The same separation is used when exporting
the manual to PDF. TXT remains UTF-8.


### V17 changes
- Mixed Hindi/equation manual lines use per-script Kivy font runs.
- Devanagari uses Noto Sans Devanagari; mathematics uses DejaVu Sans.
- Empty numeric TextInput values are repaired to safe defaults before solving.
- x0, x1, initial step and tolerance are validated before entering the numerical core.
- Numerical/3D/graph architecture is unchanged.
