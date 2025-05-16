CREATE MATERIALIZED VIEW flat_stac.nid_nld_elements AS
WITH asset_details AS (
    SELECT
        stac_items.id AS model_id,
        assets.key AS asset_key,
        jsonb_array_elements_text(assets.value->'HEC-RAS:ref_points') AS element_name
    FROM
        flat_stac.stac_items stac_items,
        jsonb_each(stac_items.content->'assets') AS assets
    UNION ALL
    SELECT
        stac_items.id AS model_id,
        assets.key AS asset_key,
        jsonb_array_elements_text(assets.value->'HEC-RAS:connections') AS element_name
    FROM
        flat_stac.stac_items stac_items,
        jsonb_each(stac_items.content->'assets') AS assets
)
SELECT
    model_id,
    asset_key,
    element_name,
    CASE
        WHEN LOWER(element_name) LIKE 'nld%' THEN 'levee'
        WHEN LOWER(element_name) LIKE 'nid%' THEN 'dam'
        ELSE NULL
    END AS element_type
FROM
    asset_details
WHERE
    asset_key LIKE '%.g%' AND
    asset_key NOT LIKE '%.hdf' AND
    asset_key NOT LIKE '%.hdf_thumbnail' AND
    LOWER(element_name) ~ '^(nid|nld)';

