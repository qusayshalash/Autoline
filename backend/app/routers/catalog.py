"""The vehicle catalog: one car, by plate or chassis number.

Read access is enough - anyone who may look at the datasets may look a vehicle up in them.
Both endpoints are rate limited like the grid: a lookup is cheap (about 25 ms), but a
loop of them is a way to walk the whole registry one plate at a time.
"""

from fastapi import APIRouter, Depends, Query

from app.auth import rate_limited, require_permission
from app.models.schemas import VehicleLookup, VehiclePhoto
from app.services import vehicle_lookup, vehicle_photo
from app.services.rate_limit import QUERY

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
    # the vehicle's year, so the photo is of its own generation rather than the newest
    year: int | None = Query(None, ge=1950, le=2100),
) -> VehiclePhoto:
    return VehiclePhoto(**vehicle_photo.find(make, model, year))
