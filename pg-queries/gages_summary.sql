CREATE MATERIALIZED VIEW flat_stac.gages_summary AS
WITH property_elements AS (
    SELECT 
        id AS gage_id,
        datetime as start_datetime,
        end_datetime,
        geometry,
        stac_items.content->'properties'->>'station_nm' AS station_nm
    FROM
        flat_stac.stac_items
    WHERE
        collection = 'trinity-gages'
)
SELECT gage_id, station_nm, start_datetime, end_datetime, geometry
FROM property_elements;