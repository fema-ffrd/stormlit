/* This procedure will concatenate all of the atac items stored in partioned tables _items_*
so that a single query can be run for all items.

This is convenience creates a table that will be stale any time there are updates made
to the stac collections, and therefore should be run any time updates are made. The function call
`insert_from_dynamic_partitions()` will create this update (notice lines 10-13) by deleting the
existing table. This is a patch, a better more permanent solution should be identified.
*/

DROP SCHEMA IF EXISTS flat_stac CASCADE;
CREATE SCHEMA flat_stac;
CREATE TABLE flat_stac.stac_items AS
TABLE pgstac._items_7 WITH NO DATA;
--
CREATE OR REPLACE PROCEDURE insert_from_dynamic_partitions()
LANGUAGE plpgsql AS $$
DECLARE
    partition_record RECORD;
BEGIN

    EXECUTE 'TRUNCATE TABLE flat_stac.stac_items';

    FOR partition_record IN
        SELECT DISTINCT '_items_' || key AS partition_name
        FROM pgstac.collections
    LOOP
        EXECUTE format('INSERT INTO flat_stac.stac_items SELECT * FROM pgstac.%I', partition_record.partition_name);
    END LOOP;
END;
$$;

CALL insert_from_dynamic_partitions()
