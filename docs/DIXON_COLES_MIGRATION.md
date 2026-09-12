# Dixon–Coles migration note

## Šta je urađeno

- Dixon–Coles model je prenet iz legacy `h2h` repoa u V2 kao quant baseline.
- Matematička logika `fit()` je proverena direktnim poređenjem sa legacy implementacijom.
- Legacy baseline je vezan za commit `9b2337b8432546420945f32586b7a4b84355589b`.
- NumPy i SciPy su pinovani na verzije korišćene u legacy baseline-u: `numpy==2.3.5`, `scipy==1.17.0`.
- Dodat je golden-master regression test za deterministički synthetic dataset.
- Reprodukovane vrednosti baseline-a su zapisane u `tests/quant/test_dixon_coles_golden_master.py`.

## Verifikacija

- Targeted Dixon–Coles test: PASS
- Ruff: PASS
- Full pytest: `7 passed`
- Promene su commitovane i pushovane na `main` u `ca7c1a4` (`test: lock reproducible Dixon-Coles baseline`).

## Bitna napomena

Prvobitne očekivane golden-master vrednosti nisu bile reprodukovane iz stvarnog legacy koda. Nisu korišćene za promenu matematike modela; umesto toga baseline je ponovo izračunat direktno iz legacy implementacije u pinovanom environmentu.

## Sledeće

Ne menjati Dixon–Coles matematiku bez novog dokaza/regression testa. Nastaviti prema stvarnom roadmap-u repoa, bez dodatnog refaktorisanja van scope-a.
