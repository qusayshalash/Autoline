/**
 * Features that are built but on hold.
 *
 * The vehicle catalog and the record card are to be opened together, later. Their pages,
 * styles and API stay in place and keep their tests; these switches only close the way
 * in, so opening them is a change here rather than a rebuild.
 */

/** The record card (/datasets/:id/record), reached from a row number in the grid. */
export const RECORD_CARD_ENABLED = false;

/**
 * Synchronising the vehicle file with the government registry on data.gov.il
 * (Settings -> Government registry). Built and tested against the full registry; held
 * back until it is switched on deliberately. The marks it leaves (a record the registry
 * no longer lists) still show wherever data carries them.
 */
export const REGISTRY_SYNC_ENABLED = false;
