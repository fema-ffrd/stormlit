CREATE MATERIALIZED VIEW flat_stac.gages_by_model_id AS
    WITH asset_details AS (
        SELECT
            stac_items.id as model_id,
            jsonb_array_elements_text(assets.value->'HEC-RAS:ref_lines') AS ref_line,
            assets.key AS asset_key
        FROM
            flat_stac.stac_items stac_items,
            jsonb_each(stac_items.content->'assets') AS assets
    )
    SELECT
        model_id,
        asset_key,
        ref_line,
        split_part(ref_line, '_', 3) AS gage_id
    FROM
        asset_details
    WHERE
        asset_key LIKE '%.g%' AND
        asset_key NOT LIKE '%.hdf' AND
        asset_key NOT LIKE '%.hdf_thumbnail' AND
        ref_line LIKE 'gage%';