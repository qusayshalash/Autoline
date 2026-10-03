"""The vehicle catalog: one car, by plate or chassis number.

Read access is enough - anyone who may look at the datasets may look a vehicle up in them.
Both endpoints are rate limited like the grid: a lookup is cheap (about 25 ms), but a
loop of them is a way to walk the whole registry one plate at a time.
"""

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import FileResponse

from app.auth import rate_limited, require_permission
from app.db import admin as admin_db
from app.errors import ApiError
from app.models.schemas import VehicleLookup, VehiclePhoto, VehiclePhotoInfo
from app.services import vehicle_lookup, vehicle_photo, vehicle_photos
from app.services.rate_limit import PHOTO, QUERY

router = APIRouter(prefix="/api/catalog", tags=["catalog"])


@router.get(
    "/lookup",
    response_model=VehicleLookup,
    dependencies=[Depends(require_permission("datasets.view")), Depends(rate_limited(QUERY))],
)
def lookup(q: str = Query("", max_length=64)) -> VehicleLookup:
    return VehicleLookup(**vehicle_lookup.lookup(q))


@router.get(
    "/photo",
    response_model=VehiclePhoto,
    dependencies=[Depends(require_permission("datasets.view")), Depends(rate_limited(QUERY))],
)
def photo(
    make: str = Query("", max_length=60),
    model: str = Query("", max_length=60),
) -> VehiclePhoto:
    return VehiclePhoto(**vehicle_photo.find(make, model))


# ---- a real photo of one vehicle ------------------------------------------------------
#
# Adding or removing one needs the upload permission - editors and administrators - since
# it adds content without overwriting anything the registry said. Seeing one needs only
# read access, like everything else in the catalog. The plate in the path is checked to be
# eight digits before it is used for anything, including building a file path.


def _plate(plate: str) -> str:
    if not vehicle_photos.valid_plate(plate):
        raise ApiError(400, "photo_bad_plate", "Not a plate number")
    return plate


def _label(plate: str) -> str:
    # the activity log shows the plate as it is printed, not as it is stored
    d = plate[1:] if plate.startswith("0") else plate
    return f"{d[:2]}-{d[2:5]}-{d[5:]}" if len(d) == 7 else f"{d[:3]}-{d[3:5]}-{d[5:]}"


@router.post("/vehicles/{plate}/photo", response_model=VehiclePhotoInfo,
             dependencies=[Depends(rate_limited(PHOTO))])
async def upload_photo(
    plate: str,
    file: UploadFile = File(...),
    actor: dict = Depends(require_permission("datasets.upload")),
) -> VehiclePhotoInfo:
    plate = _plate(plate)
    # the gate in front has already bounded this at MAX_PHOTO_BYTES, counted as it arrived
    data = await file.read()
    replaced = vehicle_photos.get(plate) is not None
    try:
        info = vehicle_photos.save(plate, data, str(actor.get("username") or ""))
    except vehicle_photos.PhotoProblem as exc:
        raise ApiError(422, exc.code, str(exc)) from exc
    admin_db.log_activity(
        actor,
        "vehicle.photo_replaced" if replaced else "vehicle.photo_added",
        "vehicle",
        plate,
        _label(plate),
        f"{info.get('width')}x{info.get('height')}",
    )
    return VehiclePhotoInfo(**info)


@router.get("/vehicles/{plate}/photo",
            dependencies=[Depends(require_permission("datasets.view"))])
def get_photo(plate: str) -> FileResponse:
    path = vehicle_photos.file_for(_plate(plate))
    if path is None:
        raise ApiError(404, "photo_not_found", "This vehicle has no photo")
    return FileResponse(
        path,
        media_type="image/jpeg",
        headers={
            # always the bytes we wrote, never sniffed into something else
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": "inline",
            # the address carries the photo's id, so a long cache cannot show a replaced
            # photo; private, because it sits behind a sign-in
            "Cache-Control": "private, max-age=604800",
        },
    )


@router.delete("/vehicles/{plate}/photo")
def delete_photo(
    plate: str, actor: dict = Depends(require_permission("datasets.upload"))
) -> dict:
    plate = _plate(plate)
    if not vehicle_photos.remove(plate):
        raise ApiError(404, "photo_not_found", "This vehicle has no photo")
    admin_db.log_activity(actor, "vehicle.photo_removed", "vehicle", plate, _label(plate), "")
    return {"deleted": plate}
