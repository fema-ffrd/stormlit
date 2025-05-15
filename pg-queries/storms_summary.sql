CREATE MATERIALIZED VIEW flat_stac.storms_summary AS
select 
	stac_items.id,
	stac_items.datetime as start_datetime,
	stac_items.end_datetime,
	stac_items.content->'properties'->>'storm_type' AS storm_type,
	(stac_items.content->'properties'->'tropical_storm'->0->>'name') AS tropical_storm_name,
    stac_items.content->'properties'->'aorc:statistics'->>'max' AS max_precip,
    stac_items.content->'properties'->'aorc:statistics'->>'min' AS min_precip,
    stac_items.content->'properties'->'aorc:statistics'->>'mean' AS mean_precip,
    stac_items.geometry
	
from flat_stac.stac_items as stac_items 

where collection = '72hr-events';