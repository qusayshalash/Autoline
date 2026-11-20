import { api, type VinReading } from "./client";

export interface VehicleMatch {
  dataset_id: string;
  dataset_name: string;
  columns: string[];
  values: string[];
  vin?: VinReading | null;
}

export interface VehicleLookup {
  query: string;
  /** what the query was read as; null when it could be neither */
  kind: "plate" | "chassis" | null;
  /** the form actually searched for - the zero-padded plate, the upper-cased chassis */
  normalized: string;
  matches: VehicleMatch[];
}

export async function lookupVehicle(q: string): Promise<VehicleLookup> {
  const { data } = await api.get<VehicleLookup>("/catalog/lookup", { params: { q } });
  return data;
}

/** How many vehicles in one dataset share the found one's make and model, and engine -
 *  each with the equality filters that open exactly those rows in the grid. */
export interface SimilarCount {
  filters: { column: string; value: string }[];
  count: number;
}

export interface SimilarVehicles {
  model: SimilarCount | null;
  engine: SimilarCount | null;
}

export async function fetchSimilar(datasetId: string, q: string): Promise<SimilarVehicles> {
  const { data } = await api.get<SimilarVehicles>("/catalog/similar", {
    params: { dataset_id: datasetId, q },
  });
  return data;
}

/** The grid's address, opened on just these rows. */
export function gridPath(datasetId: string, filters: SimilarCount["filters"]): string {
  const params = new URLSearchParams();
  for (const f of filters) params.append("eq", `${f.column}=${f.value}`);
  return `/datasets/${datasetId}/explore?${params.toString()}`;
}
