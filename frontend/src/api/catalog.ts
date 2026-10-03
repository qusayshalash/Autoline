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

/** A photo of the model, not of the vehicle. Every field is null when there is none. */
export interface VehiclePhoto {
  url: string | null;
  title: string | null;
  page: string | null;
  /** the generation the photo is of, "2011–2016"; null when it could not be told */
  years: string | null;
}

export async function lookupVehicle(q: string): Promise<VehicleLookup> {
  const { data } = await api.get<VehicleLookup>("/catalog/lookup", { params: { q } });
  return data;
}

export async function fetchVehiclePhoto(
  make: string,
  model: string,
  year?: string
): Promise<VehiclePhoto> {
  const y = Number(year);
  const { data } = await api.get<VehiclePhoto>("/catalog/photo", {
    params: { make, model, year: Number.isInteger(y) && y > 1950 ? y : undefined },
  });
  return data;
}
