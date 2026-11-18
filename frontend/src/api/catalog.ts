import { api } from "./client";

export interface VehicleMatch {
  dataset_id: string;
  dataset_name: string;
  columns: string[];
  values: string[];
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
