"""The vehicle catalog: one car, by plate or chassis number.

Read access is enough - anyone who may look at the datasets may look a vehicle up in them.
Both endpoints are rate limited like the grid: a lookup is cheap (about 25 ms), but a
loop of them is a way to walk the whole registry one plate at a time.
"""

from fastapi import APIRouter, Depends, Query

from app.auth import rate_limited, require_permission
from app.errors import ApiError
from app.models.schemas import SimilarVehicles, VehicleLookup
from app.services import vehicle_lookup
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
    "/similar",
    response_model=SimilarVehicles,
    dependencies=[Depends(require_permission("datasets.view")), Depends(rate_limited(QUERY))],
)
def similar(
    dataset_id: str = Query(..., max_length=64),
    q: str = Query("", max_length=64),
) -> SimilarVehicles:
    """How many vehicles in this dataset share the found one's make and model, and engine."""
    try:
        return SimilarVehicles(**vehicle_lookup.similar(dataset_id, q))
    except LookupError:
        raise ApiError(404, "dataset_not_found", "Dataset not found")
