-- Separate immutable training provenance from the prediction target scope.
-- Existing V1 artifacts remain valid; V2 artifacts carry an explicit target scope.

ALTER TABLE dixon_coles_model_versions
    DROP CONSTRAINT dixon_coles_model_versions_artifact_schema_version_check;

ALTER TABLE dixon_coles_model_versions
    ADD CONSTRAINT dixon_coles_model_versions_artifact_schema_version_check
    CHECK (artifact_schema_version IN (1, 2));
