import { api } from "./client";

export interface VehicleMatch {
  dataset_id: string;
  dataset_name: string;
  columns: string[];
  values: string[];
  /** a real photo of this vehicle, when somebody has uploaded one */
  photo?: VehiclePhotoInfo | null;
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
}

export async function lookupVehicle(q: string): Promise<VehicleLookup> {
  const { data } = await api.get<VehicleLookup>("/catalog/lookup", { params: { q } });
  return data;
}

export async function fetchVehiclePhoto(make: string, model: string): Promise<VehiclePhoto> {
  const { data } = await api.get<VehiclePhoto>("/catalog/photo", { params: { make, model } });
  return data;
}

/** A real photo somebody uploaded of this vehicle. */
export interface VehiclePhotoInfo {
  plate: string;
  photo_id: string;
  bytes: number;
  width: number;
  height: number;
  uploaded_by: string;
  uploaded_at: string;
}

/** Where the browser loads a vehicle's real photo from. The id is part of the address,
 *  so a replaced photo is a new URL and no cache can keep showing the old one. */
export function vehiclePhotoUrl(plate: string, photoId: string): string {
  return `${api.defaults.baseURL}/catalog/vehicles/${encodeURIComponent(plate)}/photo?v=${encodeURIComponent(photoId)}`;
}

export async function uploadVehiclePhoto(
  plate: string,
  file: File,
  onProgress?: (pct: number) => void
): Promise<VehiclePhotoInfo> {
  const form = new FormData();
  form.append("file", file);
  const { data } = await api.post<VehiclePhotoInfo>(
    `/catalog/vehicles/${encodeURIComponent(plate)}/photo`,
    form,
    {
      headers: { "Content-Type": "multipart/form-data" },
      onUploadProgress: (evt) => {
        if (onProgress && evt.total) onProgress(Math.round((evt.loaded / evt.total) * 100));
      },
    }
  );
  return data;
}

export async function deleteVehiclePhoto(plate: string): Promise<void> {
  await api.delete(`/catalog/vehicles/${encodeURIComponent(plate)}/photo`);
}
