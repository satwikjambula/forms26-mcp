# Roadmap

Current release: 0.1.0 alpha. The existing implementation inspects Forms XML and produces reviewable blueprints and shells. The priorities below are proposed work, not implemented features or delivery commitments.

1. **Validate real Forms2XML variants:** collect authorized, synthetic reproductions and test against exported attributes, property IDs, default/inherited values and module types.
2. **Complete migration inputs:** add safe PLL-to-PLD source ingestion and separate Reports XML parsing; preserve file hashes and source references.
3. **Resolve dependencies:** attached libraries, object-library inheritance, database synonyms, schema-qualified and quoted identifiers.
4. **Track review state:** persistent annotations for applicability, incomplete work, decisions, owner and verification evidence, invalidated when source hashes change.
5. **Enrich metadata:** alerts, parameters, canvases/windows, item-level validations, LOV dependencies and master/detail rules.
6. **Prove a vertical slice:** implement one real shared PL/SQL service, one APEX page and one authenticated ORDS endpoint in a disposable Oracle 26ai development environment.
7. **Generate supported artifacts:** target a verified APEX release and its supported authoring/import workflow, with compilation/import checks and behavior tests.
8. **Calibrate estimation:** measure completed modules and account separately for integration work, UAT, rollout and training.

The [Oracle guide coverage map](docs/oracle-migration-baseline.md) records the historical migration workflow and current project gaps.
