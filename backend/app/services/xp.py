"""XP rewards data quality and scientific contribution, not the number of organisms (or specimens collected)."""
from sqlalchemy.orm import Session

from ..models import User, XPEvent

XP_RULES = {
    "explore": 10,           # ran an exploration / started a mission
    "observation": 10,       # documented observation (requires photo OR detailed notes, see award_observation)
    "new_locality": 20,      # first BIOQUEST record in a 0.1° cell
    "rare_species": 50,      # target with few known records
    "validation": 100,       # identification verified by others (e.g. iNaturalist research grade)
    "scientific_finding": 250,  # discovery reviewed by an expert
    "well_documented": 15,   # photo + habitat + microhabitat + coordinates with accuracy
}


def award(db: Session, user: User, kind: str, ref: str = "") -> int:
    pts = XP_RULES[kind]
    db.add(XPEvent(user_id=user.id, kind=kind, points=pts, ref=ref))
    user.xp += pts
    return pts
