# Existing Cover Vision Audit — 2026-07-31

**Scope:** 54 canonical covers under `/home/ganomix/Books` (52 currently published, 1 publishable but not currently listed, and 1 intentionally read-only project cover).
**Tool:** Hermes `vision_analyze` on every exact canonical PNG; nine contact sheets were also inspected for cross-library comparison.
**Rubric:** focal-subject/head/face occlusion; title and byline readability; safe margins; rendering, anatomy, malformed/pseudo-text artifacts; professional composition; thumbnail function.

## Result

- Initial pass: 46 accepted; 8 rejected.
- Repairs completed: 8.
- Post-repair exact-image reinspection: 8 accepted.
- **Final state: all 54 existing canonical covers PASS.**
- Hash-bound source receipts: 53 (`cover/vision-audit.json`).
- Read-only central receipt: 1 (`audit-index.json`, `no-common-body`).

## Initial failures and repairs

| Cover | Initial defect | Correction |
|---|---|---|
| `a-marriage-of-seven-ghosts` | Opaque header cut through both characters’ heads. | Replaced with a fade ending above the heads; preserved title and byline. |
| `eight-counts-after-dark` | Hard title panel clipped the man’s crown and crowded the woman’s hair. | Rebuilt title treatment with a shallow fade and protected head zone. |
| `redshift-rendezvous` | Hard title panel obscured both characters’ crowns. | Rebuilt title treatment with a shallow fade and protected head zone. |
| `the-midwife-of-the-drowned-moon` | Header hid the midwife’s entire head. | Compressed title stack and faded the veil before the figure begins. |
| `a-planet-made-of-forecasts` | Raw outlined typography and weak edge-safe hierarchy. | Professionally re-typeset title/byline with gradients and safe margins. |
| `the-city-that-learned-to-refuse` | Raw outlined typography over busy art. | Professionally re-typeset title/byline in negative space. |
| `the-migration-of-burning-ships` | Raw outlined typography and weak title integration. | Professionally re-typeset title/byline with safe margins. |
| `the-slowlight-accord` | Title approached trim edges; weak hierarchy and redundant label. | Rebalanced title onto two lines and simplified byline treatment. |

## Hash-bound PASS receipts

| Cover | Final SHA-256 |
|---|---|
| `a-country-of-dancing-stone` | `7fa8865f918a9a8b6b8644ef143c83047eb4aef90241f07986e7191c15538423` |
| `a-marriage-of-seven-ghosts` | `6e2ba1fa5de0132841af321337a47c9994c18b3a70cf963894d7920dfa1bcfe5` |
| `a-planet-made-of-forecasts` | `a18ee0472958670572ec37cffcb613aa2529c3a70f031f38157ac8f1242a53d8` |
| `cinder-nine-the-last-gun` | `6b6f24d890d9bcb4045c104a1cc442648b7851fa3961931639237d08afc06a81` |
| `congruence-lattice` | `8aff23768bf04028c1120f7d8a0c50905a5c15daf08a32748fedcb91388d25b5` |
| `eight-counts-after-dark` | `4aded8f88f07e8fc18109477a6a26a2b179502e0c3067a5fb5175d0926ff076c` |
| `martian-compact` | `02dd686050f4f765a16fb63997883a03c789909963ef52460cbc9f6c9a1c9f0a` |
| `rain-check-after-midnight` | `d2e8adaedf644dfb45cfb064f5b4551503f6348d945423fe325c0c4922332f64` |
| `redshift-rendezvous` | `b04948030cb4ebe6638241729897f52f315322adbba89001cfb1eba76f1c7749` |
| `tessellated-sky` | `b3434edd30b7121ab47022a556843c5089279a85b3ac244a26fdaa0462d3db1b` |
| `the-anchors-wake` | `ef2b43aac4d8625c3a093bff260a79e23a4ddbacb636cf10c7ff544c97bae46f` |
| `the-axiom-of-void` | `8d910704c5c2b3a0a869350e1738e722f00727f9a57854176ad953de047e9d1c` |
| `the-calibration-of-gaps` | `f14bcbe5908fec7ca51d4c38739ec09e79c534eff292b92066a87b2a695e1dc9` |
| `the-cartography-of-silence` | `21e3c22d81ef5cf329aa99cea9a429f44c086a3fa64ea8407ae8185f7b5e4f17` |
| `the-census-of-static` | `5e9692a02019737dc502943df40083648eb03376c11831cb27a22d4ac7b13777` |
| `the-choir-at-aphelion` | `b5a9df4ae26f49494739d3a5997030ba83655e484a7c68e8eb1effc6a0e58593` |
| `the-city-that-learned-to-refuse` | `ef99c86e6ae9a15e6c3cec386eb6e98a43b6b7f82635bb4a58c2e3bddb26b6cc` |
| `the-conservatory-of-broken-seasons` | `c4d909712b9ab1836691d97af4d1caf3a60de1f2ea9933d2f80c574dbdfdcbe1` |
| `the-court-of-borrowed-voices` | `85dc4b3f88a22b085a82d3ab1ec1b5b83c0190bd9c3c4188d15f5199c211a351` |
| `the-custody-of-silence` | `5f2517737de2a5ab701542547c48a2e3af8c8c110f069be5275301e6131f2b45` |
| `the-embassy-of-unfinished-minds` | `b212a17a26726f19dfded7ffbe196e5cf4c4d02687f73cdb3550d19193fc9db7` |
| `the-feast-of-a-hundred-fires` | `30132b26f623adf89ac3edbcc93807538f0f3421e78b48d38162ba98271d1e87` |
| `the-fleet-beyond-the-burning-line` | `d514cf61c3f4ca52034bdda0a850e8d4185fb5d27afb92f9d7d6cd7c9e272971` |
| `the-foreclosure-of-summer` | `d9992d120375187181ede541944f9850b3bbc3a85d1f77d11ca9d78a444c219a` |
| `the-futures-we-summoned` | `d5f71835a51c283913c177bf56194f38fd3f9a974aa6dd45257e4c50f090aaa5` |
| `the-glass-monument` | `15bad197b8f92342b4567a3fe89c35a311e34c2defd8d568de8cc0606bad9e5e` |
| `the-gravity-we-owe` | `f0b0b4df8f3e2a2d7cd3909bd1cdb7b66a46ae519b2e5e227e0301c5e8005725` |
| `the-hollow-light` | `c56443bbfbf8544b9b27c9abdff2fda62aa255e71c208505eddfeef70353e155` |
| `the-inertial-compact` | `c2b9c4eb6edfff17245ddeb1f44f30058618c711c34d8f1679ae61f6637b7f88` |
| `the-inheritance-of-rain` | `7cdeccb668605e1dda88e71b4aba72b1eebd0f74c78670b6fc9fdae81e989dbc` |
| `the-language-of-things` | `3410327cbc379b8f4bdea10f9248bdcdbce0606299bff5b49f09241657fc79db` |
| `the-last-daylight` | `9dcb12321d5aeadc892e1cecd2a41fd75cb1fce5f512b0fe6e095d0912e5c166` |
| `the-mercy-of-parallel-suns` | `177be6e289a559bb1f97c0e37df8347cc1235a7adea5a6ec56a3e7ad78328e89` |
| `the-midwife-of-the-drowned-moon` | `b97afb213aff61bc4a4fa4cb52d078ae32496290275d7b34447df8b0e5c9f6e5` |
| `the-migration-of-burning-ships` | `490e80c8065a4873112a77f85b5efdacd1873743d1c170ec1ab81b0544c74632` |
| `the-ministry-of-unfallen-stars` | `ec7ee7c7d4bfbe5fe5fe774d1ebddde3f812c3df2ca74a444bb7d716f1e3525f` |
| `the-museum-of-abandoned-routes` | `bc368ea8e5cf5c945b82da4c0d9f8b5048e7762261e06b0302fe762aebd19de4` |
| `the-orchard-of-unchosen-years` | `e41b95bd8690b97572d2899159f258e6b4a717a7e0f288d75d16cb45d43d89b9` |
| `the-palace-that-ate-the-city` | `3a9f53c9f6122017c267991832233d7d8df353b39ccda76a986e11cf6784a050` |
| `the-parallax-testament` | `b66c7e7d6824b50c30febda16cfd3ddb1ea81d8928f2f36265edbed45e047610` |
| `the-parliament-of-vapor` | `31743f57588d8b147b2132ef15acd42dc8be8a56968815bd76bb2c5eab458d50` |
| `the-quiet-beacon` | `57659493a9c5211f2860da43fd71a494ee52542c4ae401d92405826d2ce58ff5` |
| `the-quiet-cartographers` | `a22b38e6605f6bdd3bd638d3988b973f2d22e802a6e613570990e6e728a4090b` |
| `the-republic-of-borrowed-gravity` | `1de366578ffc225b9ecc2536edc0d253e6f07cd718d3e62169d7b37ad31ded3e` |
| `the-severance-compact` | `e6ff05eadb5aa7b2edc3a3a2567d7037415a0da68a323008993226a066ca39cc` |
| `the-shepherds-of-empty-space` | `e4c6c55ff353624aa39d00d50469db4b130f65782b72d1112d0be0f236078f7a` |
| `the-silence-after-tomorrow` | `b3423c41c9a1f04e8f91919ab001d95fd210ef5ffac899a6dcf2dd08cd66ba58` |
| `the-slowlight-accord` | `594a4c52f1a85d751d65d9aae78e242c6da70bc510e2cc28ba6e15968bbe2cc4` |
| `the-threshold-of-reflection` | `a1bbb0cd434810eb5bef615c7a48d7121b073ff3ff603352f595968c4f5fc9ae` |
| `the-tides-between-minutes` | `e95aacd13b19cc8c75f86c02667d1ff47932a15fc851b0a8b21911e8d3d29a5a` |
| `the-tithing-of-light` | `3940dfc40ad587d76cea4acb8092c508566346768575519459a55fc7838a2cc6` |
| `the-weather-we-condemned` | `9f9aff92e219404127ac338c2d4bc26fc75610b1588aabb6382f105fb24479a7` |
| `tidewright` | `ff20b7d44c40c61c1af9df45784ee0d0dde368a1062c0595aba742680edf7454` |
| `no-common-body` (read-only central receipt) | `955cabfa791104a204c9e6e3b236af767b02bb06258665907882b91f6fd7aa7f` |

Regenerating any publishable cover changes its SHA-256 and invalidates its adjacent receipt. The site generator and autonomous publisher now refuse publication until the new exact image is inspected with `vision_analyze` and receives a complete PASS receipt.
