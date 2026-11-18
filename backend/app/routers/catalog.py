"""The vehicle catalog: one car, by plate or chassis number.

Read access is enough - anyone who may look at the datasets may look a vehicle up in them.
The lookup is rate limited like the grid: a lookup is cheap (about 25 ms), but a
loop of them is a way to walk the whole registry one plate at a time.
"""

from fastapi import APIRouter, Depends, Query

from app.auth import rate_limited, require_permission
from app.models.schemas import VehicleLookup
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

