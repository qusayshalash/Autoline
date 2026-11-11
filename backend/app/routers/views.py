"""Saved views: a search with its filters and sort, kept under a name.

A view can be opened again in one click. It is private to its owner until shared, when
everyone who can read the dataset sees it in their list and can open it by its link.

Reading the dataset is all it takes: a view changes nothing in the data, and a private one
changes nothing anybody else sees.
"""

from fastapi import APIRouter, Depends
from pydantic import ValidationError

from app.auth import require_permission
from app.db import admin as admin_db
from app.db import catalog
from app.db import views as views_db
from app.errors import ApiError
from app.models.schemas import (
    SavedViewIn,
    SavedViewOut,
    SavedViewPatch,
    ViewState,
)
from app.services import clocks

router = APIRouter(prefix="/api/datasets", tags=["views"])

# per person per dataset: enough for any real use, few enough that the list stays a list
MAX_VIEWS_PER_PERSON = 100


def _dataset(dataset_id: str) -> dict:
    row = catalog.get_dataset(dataset_id)
    if row is None:
        raise ApiError(404, "dataset_not_found", "Dataset not found")
    return row


def _can_edit(user: dict) -> bool:
    return "datasets.edit" in set(user.get("permissions") or [])


def _view_out(row: dict, user: dict) -> SavedViewOut | None:
    try:
        state = ViewState.model_validate(row["state"])
    except ValidationError:
        return None
    mine = row["owner_id"] == user["id"]
    return SavedViewOut(
        id=row["id"],
        dataset_id=row["dataset_id"],
        name=row["name"],
        state=state,
        shared=bool(row["shared"]),
        owner_username=row["owner_username"] or "",
        mine=mine,
        can_delete=mine or (bool(row["shared"]) and _can_edit(user)),
        created_at=clocks.iso(row["created_at"]),
        updated_at=clocks.iso(row["updated_at"]),
    )


def _visible_view(dataset_id: str, view_id: str, user: dict) -> dict:
    """The view, if this person may see it. A private view of somebody else's is
    reported missing rather than forbidden: whether it exists is itself theirs."""
    row = views_db.get_view(view_id)
    if (
        row is None
        or row["dataset_id"] != dataset_id
        or (row["owner_id"] != user["id"] and not row["shared"])
    ):
        raise ApiError(404, "view_not_found", "This saved view does not exist or is not shared with you")
    return row


# ---- saved views ----


@router.get("/{dataset_id}/views", response_model=list[SavedViewOut])
def list_views(
    dataset_id: str, user: dict = Depends(require_permission("datasets.view"))
) -> list[SavedViewOut]:
    _dataset(dataset_id)
    out = [_view_out(r, user) for r in views_db.list_views(dataset_id, user["id"])]
    return [v for v in out if v is not None]


@router.get("/{dataset_id}/views/{view_id}", response_model=SavedViewOut)
def get_view(
    dataset_id: str, view_id: str, user: dict = Depends(require_permission("datasets.view"))
) -> SavedViewOut:
    _dataset(dataset_id)
    out = _view_out(_visible_view(dataset_id, view_id, user), user)
    if out is None:
        raise ApiError(404, "view_not_found", "This saved view does not exist or is not shared with you")
    return out


@router.post("/{dataset_id}/views", response_model=SavedViewOut, status_code=201)
def create_view(
    dataset_id: str,
    body: SavedViewIn,
    user: dict = Depends(require_permission("datasets.view")),
) -> SavedViewOut:
    row = _dataset(dataset_id)
    name = body.name.strip()
    if not name:
        raise ApiError(400, "view_name_blank", "Give the view a name")
    if views_db.count_own_views(dataset_id, user["id"]) >= MAX_VIEWS_PER_PERSON:
        raise ApiError(
            409, "too_many_views", "You already have the most saved views a file can hold - delete one first"
        )
    view_id = views_db.create_view(dataset_id, user, name, body.state.model_dump(), body.shared)
    if body.shared:
        admin_db.log_activity(
            user, "view.shared", "dataset", dataset_id, row.get("original_filename") or "",
            f"view: {name}", detail_code="view_named", name=name,
        )
    return _view_out(views_db.get_view(view_id), user)


@router.patch("/{dataset_id}/views/{view_id}", response_model=SavedViewOut)
def update_view(
    dataset_id: str,
    view_id: str,
    body: SavedViewPatch,
    user: dict = Depends(require_permission("datasets.view")),
) -> SavedViewOut:
    row = _dataset(dataset_id)
    existing = _visible_view(dataset_id, view_id, user)
    if existing["owner_id"] != user["id"]:
        raise ApiError(403, "view_not_yours", "Only the person who saved this view can change it")
    fields: dict = {}
    if body.name is not None:
        name = body.name.strip()
        if not name:
            raise ApiError(400, "view_name_blank", "Give the view a name")
        fields["name"] = name
    if body.state is not None:
        fields["state"] = body.state.model_dump()
    if body.shared is not None:
        fields["shared"] = body.shared
    views_db.update_view(view_id, **fields)
    if body.shared is not None and body.shared != bool(existing["shared"]):
        name = fields.get("name", existing["name"])
        admin_db.log_activity(
            user,
            "view.shared" if body.shared else "view.unshared",
            "dataset",
            dataset_id,
            row.get("original_filename") or "",
            f"view: {name}",
            detail_code="view_named",
            name=name,
        )
    return _view_out(views_db.get_view(view_id), user)


@router.delete("/{dataset_id}/views/{view_id}")
def delete_view(
    dataset_id: str, view_id: str, user: dict = Depends(require_permission("datasets.view"))
) -> dict:
    row = _dataset(dataset_id)
    existing = _visible_view(dataset_id, view_id, user)
    mine = existing["owner_id"] == user["id"]
    if not mine and not (existing["shared"] and _can_edit(user)):
        raise ApiError(403, "view_not_yours", "Only the person who saved this view can change it")
    views_db.delete_view(view_id)
    if existing["shared"]:
        admin_db.log_activity(
            user, "view.deleted", "dataset", dataset_id, row.get("original_filename") or "",
            f"view: {existing['name']}", detail_code="view_named", name=existing["name"],
        )
    return {"deleted": True}
