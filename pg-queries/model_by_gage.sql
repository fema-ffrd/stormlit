CREATE MATERIALIZED VIEW flat_stac.models_by_gage AS
SELECT
	gages_by_model.model_id,
	gages_by_model.gage_id,
	gages_by_model.asset_key,
	gages_by_model.ref_line,
	gages_summary.station_nm,
	gages_summary.start_datetime,
	gages_summary.end_datetime,
	gages_summary.geometry

FROM flat_stac.gages_by_model_id as gages_by_model
JOIN flat_stac.gages_summary as gages_summary ON gages_by_model.gage_id = gages_summary.gage_id;